#!/usr/bin/env python3
"""Fill silent Mandarin notes in Anki without replacing existing sounds."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from huaxia_tags import audio_source_tag  # noqa: E402

try:
    from .anki_connect import AnkiConnectClient, AnkiConnectError
    from .audio_fallback import generate_fallback_audio
except ImportError:  # Script execution from the yoyochinese directory.
    from anki_connect import AnkiConnectClient, AnkiConnectError
    from audio_fallback import generate_fallback_audio


DEFAULT_DECK = "chinois"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "generated_anki_audio"
AUDIO_FIELDS = ("Audio", "Sound", "Son", "Pronunciation")
TEXT_FIELDS = (
    "Hanzi",
    "Mandarin",
    "Simplified",
    "Chinese",
    "Expression",
    "Sentence",
    "Text",
)
SOUND_RE = re.compile(r"\[sound:[^\]]+\]", re.IGNORECASE)
HTML_RE = re.compile(r"<[^>]+>")
CHINESE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@dataclass(frozen=True)
class AudioCandidate:
    note_id: int
    model_name: str
    text: str
    text_field: str
    audio_field: str


def _field_name(fields: dict[str, Any], candidates: Iterable[str]) -> str | None:
    by_lower = {name.casefold(): name for name in fields}
    for candidate in candidates:
        actual = by_lower.get(candidate.casefold())
        if actual:
            return actual
    return None


def _plain_text(value: str) -> str:
    value = html.unescape(value or "")
    value = SOUND_RE.sub("", value)
    value = HTML_RE.sub("", value)
    value = re.sub(r"{{c\d+::(.*?)(?:::[^}]*)?}}", r"\1", value)
    return " ".join(value.split()).strip()


def discover_candidates(
    client: AnkiConnectClient,
    *,
    deck_name: str = DEFAULT_DECK,
) -> tuple[list[AudioCandidate], dict[str, int]]:
    """Return silent notes with an Audio field and usable Mandarin text."""
    safe_deck = deck_name.replace('"', "")
    note_ids = client.invoke("findNotes", query=f'deck:"{safe_deck}"') or []
    candidates: list[AudioCandidate] = []
    stats = {
        "notes_scanned": len(note_ids),
        "already_has_sound": 0,
        "no_audio_field": 0,
        "audio_field_nonempty": 0,
        "no_chinese_text": 0,
        "candidates": 0,
    }
    for start in range(0, len(note_ids), 500):
        notes = client.invoke("notesInfo", notes=note_ids[start : start + 500]) or []
        for note in notes:
            fields = note.get("fields", {})
            values = [str(meta.get("value") or "") for meta in fields.values()]
            if any(SOUND_RE.search(value) for value in values):
                stats["already_has_sound"] += 1
                continue
            audio_field = _field_name(fields, AUDIO_FIELDS)
            if audio_field is None:
                stats["no_audio_field"] += 1
                continue
            if _plain_text(str(fields[audio_field].get("value") or "")):
                stats["audio_field_nonempty"] += 1
                continue
            text_field = _field_name(fields, TEXT_FIELDS)
            text = (
                _plain_text(str(fields[text_field].get("value") or ""))
                if text_field
                else ""
            )
            if not text or not CHINESE_RE.search(text):
                stats["no_chinese_text"] += 1
                continue
            candidates.append(
                AudioCandidate(
                    note_id=int(note["noteId"]),
                    model_name=str(note.get("modelName") or ""),
                    text=text,
                    text_field=text_field,
                    audio_field=audio_field,
                )
            )
    candidates.sort(key=lambda candidate: candidate.note_id)
    stats["candidates"] = len(candidates)
    return candidates, stats


def audio_filename(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
    return f"anki_zh_{digest}.mp3"


def fill_candidates(
    client: AnkiConnectClient,
    candidates: Iterable[AudioCandidate],
    output_dir: Path,
    *,
    generator: Callable[[str, str | Path], str | None] = generate_fallback_audio,
) -> list[dict[str, Any]]:
    """Generate, store and attach one audio file to every candidate note."""
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_media = set(client.invoke("getMediaFilesNames", pattern="anki_zh_*.mp3") or [])
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        filename = audio_filename(candidate.text)
        output_path = output_dir / filename
        provider = "anki_media"
        status = "updated"
        try:
            if filename not in existing_media:
                if output_path.is_file() and output_path.stat().st_size >= 1_000:
                    provider = "existing_file"
                else:
                    provider = generator(candidate.text, output_path) or ""
                    if not provider:
                        raise RuntimeError("aucun fournisseur audio disponible")
                stored_name = client.invoke(
                    "storeMediaFile",
                    filename=filename,
                    path=str(output_path.resolve()),
                )
                if stored_name != filename:
                    raise RuntimeError("AnkiConnect n’a pas confirmé le fichier média")
                existing_media.add(filename)
            client.invoke(
                "updateNoteFields",
                note={
                    "id": candidate.note_id,
                    "fields": {candidate.audio_field: f"[sound:{filename}]"},
                },
            )
            client.invoke(
                "addTags",
                notes=[candidate.note_id],
                tags=audio_source_tag(provider),
            )
        except (AnkiConnectError, OSError, RuntimeError) as exc:
            status = "error"
            results.append(
                {
                    **asdict(candidate),
                    "status": status,
                    "filename": filename,
                    "provider": provider or None,
                    "error": str(exc),
                }
            )
            continue
        results.append(
            {
                **asdict(candidate),
                "status": status,
                "filename": filename,
                "provider": provider,
            }
        )
    return results


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ajouter automatiquement un son aux notes chinoises muettes sans "
            "remplacer les sons existants. L’aperçu est le mode par défaut."
        )
    )
    parser.add_argument("--deck", default=DEFAULT_DECK, help="deck racine à analyser")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="dossier conservant les MP3 générés",
    )
    parser.add_argument("--limit", type=int, help="limiter le nombre de notes traitées")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="générer les sons et modifier Anki (sinon aperçu seulement)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit is not None and args.limit < 1:
        print("Erreur: --limit doit être supérieur à zéro.", file=sys.stderr)
        return 2
    client = AnkiConnectClient.find(timeout=5)
    if client is None:
        print("Erreur: ouvrez Anki avec AnkiConnect avant de lancer ce script.", file=sys.stderr)
        return 2
    try:
        candidates, stats = discover_candidates(client, deck_name=args.deck)
        selected = candidates[: args.limit] if args.limit else candidates
        print(
            f"{stats['notes_scanned']} note(s) analysée(s), "
            f"{len(candidates)} note(s) chinoise(s) muette(s)."
        )
        for candidate in selected:
            print(
                f"- {candidate.text} — {candidate.model_name} "
                f"(note {candidate.note_id})"
            )
        if not args.apply:
            print("Aperçu seulement. Relancez avec --apply pour modifier Anki.")
            return 0

        results = fill_candidates(client, selected, args.output_dir.resolve())
        verified, final_stats = discover_candidates(client, deck_name=args.deck)
        errors = [result for result in results if result["status"] == "error"]
        report = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "deck": args.deck,
            "output_dir": str(args.output_dir.resolve()),
            "before": stats,
            "selected_count": len(selected),
            "updated_count": len(results) - len(errors),
            "error_count": len(errors),
            "remaining_candidates": len(verified),
            "after": final_stats,
            "results": results,
        }
        report_path = args.output_dir.resolve() / "last_run.json"
        write_report(report_path, report)
        print(
            f"Terminé: {report['updated_count']} mise(s) à jour, "
            f"{report['error_count']} erreur(s), "
            f"{report['remaining_candidates']} note(s) muette(s) restante(s)."
        )
        print(f"Rapport: {report_path}")
        return 1 if errors else 0
    except (AnkiConnectError, OSError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
