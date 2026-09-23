#!/usr/bin/env python3
"""Classe les tags Anki sous chinois, internat ou statistiques.

L'aperçu est le mode par défaut. L'application exige ``--apply`` et un jeton
de confirmation explicite. Les tags techniques Markdown-to-Anki ne sont
jamais modifiés.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from update_anki_tags import (
    AnkiConnectError,
    _batched,
    _read_notes,
    get_active_ankiconnect_url,
    invoke_ankiconnect,
)


CHINESE_ROOT = "chinois"
MEDICAL_ROOT = "internat"
STATISTICS_ROOT = "statistiques"
TECHNICAL_PREFIXES = ("_mdanki::", "_mdanki_replaced::")
TARGET_QUERY = '-deck:"chinois"'
CONFIRMATION = "CLASSER_TAGS_COLLECTION"
DEFAULT_REPORT = Path("/tmp/huaxia_collection_tag_roots.json")
DEFAULT_BACKUP_DIR = Path.home() / "Documents" / "AnkiBackups" / "Huaxia"
BACKUP_DECKS = ("internat", "M2biostatistiques", "Culture", "journal")


@dataclass(frozen=True)
class RootTagRecord:
    note_id: int
    category: str
    label: str
    add: tuple[str, ...]
    remove: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RootTagReport:
    generated_at: str
    query: str
    notes_scanned: int
    notes_changed: int
    tags_added: int
    tags_removed: int
    warnings: int
    records: tuple[RootTagRecord, ...]


def is_technical_tag(tag: str) -> bool:
    return tag.startswith(TECHNICAL_PREFIXES)


def is_rooted(tag: str, root: str) -> bool:
    return tag == root or tag.startswith(f"{root}::")


def _visible_tags(note: Mapping[str, Any]) -> set[str]:
    return {
        str(tag).strip()
        for tag in note.get("tags", ())
        if str(tag).strip() and not is_technical_tag(str(tag).strip())
    }


def _label(note: Mapping[str, Any]) -> str:
    fields = note.get("fields", {})
    for name in ("Hanzi", "Mandarin", "Front", "Question", "Text", "Content"):
        value = fields.get(name, {})
        text = value.get("value", "") if isinstance(value, Mapping) else value
        if text:
            return re.sub(r"\s+", " ", str(text)).strip()[:100]
    return str(note.get("modelName", "note"))


def plan_note_tags(
    tags: Iterable[str],
    *,
    category: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Retourne les ajouts et retraits sans toucher aux tags déjà bien rangés."""
    existing = {str(tag).strip() for tag in tags if str(tag).strip()}
    add: set[str] = set()
    remove: set[str] = set()
    for tag in existing:
        if is_technical_tag(tag) or is_rooted(tag, CHINESE_ROOT):
            continue
        if is_rooted(tag, category):
            continue
        add.add(f"{category}::{tag}")
        remove.add(tag)
    return tuple(sorted(add - existing)), tuple(sorted(remove))


def build_report(
    notes: Sequence[Mapping[str, Any]],
    *,
    statistics_note_ids: Iterable[int],
    medical_deck_note_ids: Iterable[int],
    query: str = TARGET_QUERY,
) -> RootTagReport:
    statistics_ids = {int(note_id) for note_id in statistics_note_ids}
    medical_ids = {int(note_id) for note_id in medical_deck_note_ids}
    medical_vocabulary: set[str] = set()
    for note in notes:
        if int(note.get("noteId", 0)) in medical_ids:
            medical_vocabulary.update(_visible_tags(note))

    records: list[RootTagRecord] = []
    for note in notes:
        note_id = int(note.get("noteId", 0))
        visible_tags = _visible_tags(note)
        warnings: list[str] = []
        category = ""
        if note_id in statistics_ids and note_id in medical_ids:
            warnings.append(
                "Note présente dans les périmètres internat et statistiques : aucun tag déplacé."
            )
        elif note_id in statistics_ids:
            category = STATISTICS_ROOT
        elif note_id in medical_ids or bool(visible_tags & medical_vocabulary):
            category = MEDICAL_ROOT
        elif visible_tags:
            warnings.append(
                "Tags hors chinois non reconnus comme médicaux ou statistiques : conservation."
            )

        add: tuple[str, ...] = ()
        remove: tuple[str, ...] = ()
        if category:
            add, remove = plan_note_tags(note.get("tags", ()), category=category)
        if add or remove or warnings:
            records.append(
                RootTagRecord(
                    note_id=note_id,
                    category=category,
                    label=_label(note),
                    add=add,
                    remove=remove,
                    warnings=tuple(warnings),
                )
            )

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return RootTagReport(
        generated_at=now,
        query=query,
        notes_scanned=len(notes),
        notes_changed=sum(bool(record.add or record.remove) for record in records),
        tags_added=sum(len(record.add) for record in records),
        tags_removed=sum(len(record.remove) for record in records),
        warnings=sum(len(record.warnings) for record in records),
        records=tuple(records),
    )


def prepare_live_report(url: str, *, batch_size: int = 500) -> RootTagReport:
    target_ids = invoke_ankiconnect("findNotes", url=url, query=TARGET_QUERY) or []
    statistics_ids = invoke_ankiconnect(
        "findNotes", url=url, query='deck:"M2biostatistiques"'
    ) or []
    medical_ids = invoke_ankiconnect(
        "findNotes", url=url, query='deck:"internat"'
    ) or []
    notes = _read_notes(url, target_ids, batch_size=batch_size)
    return build_report(
        notes,
        statistics_note_ids=statistics_ids,
        medical_deck_note_ids=medical_ids,
    )


def write_report(report: RootTagReport, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def backup_impacted_decks(url: str, destination_dir: Path) -> tuple[Path, ...]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backups: list[Path] = []
    for deck in BACKUP_DECKS:
        note_ids = invoke_ankiconnect(
            "findNotes", url=url, query=f'deck:"{deck}"'
        ) or []
        if not note_ids:
            continue
        filename = re.sub(r"[^a-z0-9]+", "-", deck.lower()).strip("-")
        destination = destination_dir / f"{filename}-avant-tags-{stamp}.apkg"
        invoke_ankiconnect(
            "exportPackage",
            url=url,
            timeout=1_800,
            deck=deck,
            path=str(destination),
            includeSched=True,
        )
        if not destination.is_file() or destination.stat().st_size == 0:
            raise AnkiConnectError(f"La sauvegarde APKG du paquet {deck} a échoué.")
        backups.append(destination)
    return tuple(backups)


def apply_report(url: str, report: RootTagReport, *, batch_size: int = 500) -> None:
    removals: dict[str, list[int]] = defaultdict(list)
    additions: dict[str, list[int]] = defaultdict(list)
    for record in report.records:
        for tag in record.remove:
            removals[tag].append(record.note_id)
        for tag in record.add:
            additions[tag].append(record.note_id)

    # Les anciens parents sont retirés avant la création des nouvelles branches.
    for tag, note_ids in sorted(removals.items()):
        for batch in _batched(note_ids, batch_size):
            invoke_ankiconnect("removeTags", url=url, notes=batch, tags=tag)
    for tag, note_ids in sorted(additions.items()):
        for batch in _batched(note_ids, batch_size):
            invoke_ankiconnect("addTags", url=url, notes=batch, tags=tag)


def print_summary(report: RootTagReport, destination: Path) -> None:
    print("=== Classement des racines de tags Anki ===")
    print(f"Notes examinées : {report.notes_scanned}")
    print(f"Notes à modifier : {report.notes_changed}")
    print(f"Tags à ajouter : {report.tags_added}")
    print(f"Tags à retirer : {report.tags_removed}")
    print(f"Avertissements : {report.warnings}")
    print(f"Rapport complet : {destination}")
    for record in report.records[:20]:
        print(
            f"- {record.note_id} [{record.category or 'conservé'}] {record.label!r} : "
            f"+{len(record.add)} / -{len(record.remove)}"
        )
        for warning in record.warnings:
            print(f"  ! {warning}")
    if len(report.records) > 20:
        print(f"… {len(report.records) - 20} autre(s) entrée(s) dans le rapport JSON.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--batch-size", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size doit être supérieur à zéro.")
    if args.apply and args.confirm != CONFIRMATION:
        raise SystemExit(f"Application refusée : utilisez --confirm {CONFIRMATION}.")
    url = get_active_ankiconnect_url()
    if not url:
        raise SystemExit("AnkiConnect est indisponible.")
    report = prepare_live_report(url, batch_size=args.batch_size)
    write_report(report, args.report)
    print_summary(report, args.report.resolve())
    if not args.apply:
        print("Aucune note Anki n'a été modifiée.")
        return 0
    if report.warnings:
        raise SystemExit("Application refusée : le rapport contient des avertissements.")
    backups = backup_impacted_decks(url, args.backup_dir)
    for backup in backups:
        print(f"Sauvegarde créée : {backup}")
    apply_report(url, report, batch_size=args.batch_size)
    print(
        f"Application terminée : {report.tags_added} ajout(s), "
        f"{report.tags_removed} retrait(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
