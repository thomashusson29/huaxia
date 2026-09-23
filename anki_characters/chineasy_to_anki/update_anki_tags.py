#!/usr/bin/env python3
"""Preview or apply the Huaxia hierarchical-tag migration.

Preview is the default.  Applying changes requires both ``--apply`` and an
explicit confirmation token.  Legacy cleanup is a separate second phase.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Iterable, Mapping
import urllib.request


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parents[1]
SRC_DIR = SCRIPT_DIR / "src"
for import_path in (REPOSITORY_ROOT, SRC_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from character_tagger import (  # noqa: E402
    legacy_flat_pinyin_values,
    pinyin_is_plausible,
    resolve_contextual_pinyin,
)
from huaxia_tags import (  # noqa: E402
    AUDIO_SOURCE_TAG_PREFIX,
    HANZI_TAG_PREFIX,
    MNEMONIC_TAG_PREFIX,
    PINYIN_TAG_PREFIX,
    SOURCE_TAG_PREFIX,
    YOYO_SOURCE_TAG_PREFIX,
    TagContext,
    TagUpdatePlan,
    YoyoCoursePath,
    build_managed_tags,
    is_cjk_character,
    is_legacy_managed_tag,
    mnemonic_tag,
    plan_tag_update,
    source_tag,
    slugify,
    unique_cjk,
    visible_text,
    yoyo_course_tag,
)


ANKI_CONNECT_PORTS = (8766, 8765)
TARGET_QUERY = 'deck:"chinois"'
RECENT_QUERY = f"{TARGET_QUERY} added:1"
CONFIRM_ADD = "AJOUTER_TAGS_CHINOIS"
CONFIRM_CLEANUP = "NETTOYER_TAGS_CHINOIS"
DEFAULT_REPORT = (
    Path(tempfile.gettempdir()) / "huaxia_tag_migration_report.json"
)
DEFAULT_BACKUP_DIR = Path.home() / "Documents" / "AnkiBackups" / "Huaxia"
SOURCE_DECKS = (
    ("chineasy", "chinois::chineasy_characters"),
    ("integrated_chinese", "chinois::Integrated Chinese Level 1 Part 1 (Simplified)"),
    ("le_chinois_facile", "chinois::le_chinois_facile"),
    ("yoyochinese", "chinois::ychinese"),
    ("yoyochinese", "chinois::yoyo_chinese"),
    ("yoyochinese", "chinois::yoyochinese"),
)

_YOYO_PATH_RE = re.compile(
    re.escape(YOYO_SOURCE_TAG_PREFIX)
    + r"::cours::(?P<course>[^:]+)"
    + r"::niveau::(?P<level>\d{2})"
    + r"::unite::(?P<unit>\d{3})"
    + r"::lecon::(?P<lesson>\d{2})$"
)
_INTEGRATED_RE = re.compile(
    r"^IC1\.1_L(?P<lesson>\d+)(?:_(?P<section>\d+|Z))?$",
    flags=re.IGNORECASE,
)
_NUMBERED_LESSON_RE = re.compile(r"^lecon(?P<lesson>\d+)$", re.IGNORECASE)
_LEGACY_YOYO_DIMENSION_RE = re.compile(
    r"^(?P<dimension>course|level|unit|lesson)::(?P<value>.+)$",
    re.IGNORECASE,
)
_LEGACY_YOYO_COMPACT_RE = re.compile(
    r"^(?P<dimension>unit|lesson)(?P<value>\d+)$",
    re.IGNORECASE,
)
REVIEW_YOYO_PREFIX = "chinois::a_verifier::yoyochinese::"
CONTENT_TAGS = {
    "caracteres": "caracteres",
    "traits-fondamentaux": "traits_fondamentaux",
    "complement": "complement",
    "variantes": "variantes",
}
DISCARD_ARTIFACT_TAGS = {"“", "”", "…", "’", "\u200b"}


@dataclass(frozen=True)
class MigrationRecord:
    note_id: int
    model: str
    label: str
    add: tuple[str, ...]
    remove: tuple[str, ...]
    preserved_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class MigrationReport:
    generated_at: str
    mode: str
    cleanup_legacy: bool
    query: str
    notes_scanned: int
    notes_changed: int
    tags_added: int
    tags_removed: int
    warnings: int
    records: tuple[MigrationRecord, ...]


class AnkiConnectError(RuntimeError):
    pass


def get_active_ankiconnect_url() -> str:
    for port in ANKI_CONNECT_PORTS:
        url = f"http://127.0.0.1:{port}"
        try:
            payload = json.dumps({"action": "version", "version": 6}).encode()
            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("result") is not None:
                return url
        except Exception:
            continue
    return ""


def invoke_ankiconnect(
    action: str,
    *,
    url: str,
    timeout: int = 30,
    max_retries: int = 5,
    **params: Any,
) -> Any:
    payload = json.dumps(
        {"action": action, "version": 6, "params": params},
        ensure_ascii=False,
    ).encode("utf-8")
    for attempt in range(max_retries):
        try:
            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("error"):
                raise AnkiConnectError(str(result["error"]))
            return result.get("result")
        except Exception as error:
            if attempt == max_retries - 1:
                if isinstance(error, AnkiConnectError):
                    raise
                raise AnkiConnectError(f"AnkiConnect ({action}) : {error}") from error
            time.sleep(0.5)
    raise AssertionError("Boucle AnkiConnect terminée sans résultat.")


def _field(note: dict[str, Any], name: str) -> str:
    return str(
        note.get("fields", {}).get(name, {}).get("value", "") or ""
    ).strip()


def _cjk_only(*values: str) -> str:
    return "".join(
        character
        for value in values
        for character in visible_text(value)
        if is_cjk_character(character)
    )


def _source_for_note(note: dict[str, Any], source_override: str = "") -> str:
    if source_override:
        return source_override
    tags = {str(tag) for tag in note.get("tags", [])}
    model = str(note.get("modelName") or "")
    if model == "Huaxia Mnémotechnique v1":
        return ""
    if (
        _field(note, "YoyoId")
        or "yoyo_chinese" in tags
        or "yoyochinese" in tags
        or any(tag.startswith(("course::", YOYO_SOURCE_TAG_PREFIX)) for tag in tags)
    ):
        return "yoyochinese"
    if "chineasy" in tags:
        return "chineasy"
    if model in {"Chinesische Vokabeln+", "Sätze+"} or any(
        _INTEGRATED_RE.fullmatch(tag) for tag in tags
    ):
        return "integrated_chinese"
    if "lechinoisfacile" in tags:
        return "le_chinois_facile"
    if any(tag.startswith("beginner_conversation") for tag in tags):
        return "yoyochinese"
    return ""


def _note_text_fields(note: dict[str, Any]) -> tuple[str, str, str]:
    hanzi = _field(note, "Hanzi") or _field(note, "Mandarin")
    traditional = _field(note, "Traditional")
    pinyin = _field(note, "Pinyin")
    if not hanzi:
        hanzi = " ".join(
            value
            for field_name in ("Content", "Recto", "Verso", "Extra", "Note")
            if (value := _field(note, field_name))
        )
    return hanzi, traditional, pinyin


def _explicit_components(tags: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for tag in tags:
        if tag.startswith("chinois::caracteres::composant::"):
            result.append(tag.rsplit("::", 1)[-1])
        elif tag.startswith("huaxia::mnemo::composant::"):
            result.append(tag.rsplit("::", 1)[-1])
    return tuple(dict.fromkeys(result))


def _audio_source(tags: Iterable[str]) -> str:
    for tag in tags:
        if tag.startswith(AUDIO_SOURCE_TAG_PREFIX):
            return tag.removeprefix(AUDIO_SOURCE_TAG_PREFIX)
        if tag.startswith("audio_source::"):
            return tag.split("::", 1)[1]
    return ""


def _canonical_yoyo_tags(tags: Iterable[str]) -> set[str]:
    return {
        tag
        for tag in tags
        if _YOYO_PATH_RE.fullmatch(tag)
    }


def _legacy_yoyo_path(
    tags: Iterable[str],
) -> tuple[str | None, tuple[str, ...]]:
    values = tuple(tags)
    course = {
        tag.removeprefix("course::")
        for tag in values
        if tag.startswith("course::")
    }
    level = {
        tag.removeprefix("level::")
        for tag in values
        if tag.startswith("level::")
    }
    unit = {
        tag.removeprefix("unit::")
        for tag in values
        if tag.startswith("unit::")
    }
    lesson = {
        tag.removeprefix("lesson::")
        for tag in values
        if tag.startswith("lesson::")
    }
    dimensions = (course, level, unit, lesson)
    if all(len(dimension) == 1 for dimension in dimensions):
        path = YoyoCoursePath(
            course=next(iter(course)),
            level=next(iter(level)),
            unit=next(iter(unit)),
            lesson=next(iter(lesson)),
        )
        return yoyo_course_tag(path), ()

    structural = [
        tag
        for tag in values
        if tag.startswith(("course::", "level::", "unit::", "lesson::"))
        or re.fullmatch(r"(?:unit|lesson)\d+", tag)
        or tag.startswith("beginner_conversation")
    ]
    review_tags = [
        tag for tag in values if tag.startswith(REVIEW_YOYO_PREFIX)
    ]
    if structural or review_tags:
        return (
            None,
            (
                "Relation Yoyo incomplète ou ambiguë : les anciens tags de "
                "cours sont conservés et aucun croisement n’est deviné.",
            ),
        )
    return None, ()


def _review_yoyo_tag(tag: str) -> str:
    match = _LEGACY_YOYO_DIMENSION_RE.fullmatch(tag)
    if match:
        dimension = match.group("dimension").lower()
        value = match.group("value")
        branch = {
            "course": "cours",
            "level": "niveau",
            "unit": "unite",
            "lesson": "lecon",
        }[dimension]
        if dimension == "unit" and value.isdigit():
            normalized = f"{int(value):03d}"
        elif dimension in {"level", "lesson"} and value.isdigit():
            normalized = f"{int(value):02d}"
        else:
            normalized = slugify(value, "inconnu")
        return f"{REVIEW_YOYO_PREFIX}{branch}::{normalized}"

    match = _LEGACY_YOYO_COMPACT_RE.fullmatch(tag)
    if match:
        dimension = match.group("dimension").lower()
        value = int(match.group("value"))
        branch = "unite" if dimension == "unit" else "lecon"
        width = 3 if dimension == "unit" else 2
        return f"{REVIEW_YOYO_PREFIX}{branch}::{value:0{width}d}"

    if tag.startswith("beginner_conversation"):
        normalized = slugify(tag.replace("::", "_"), "inconnu")
        return f"{REVIEW_YOYO_PREFIX}ancien::{normalized}"
    return ""


def _is_cjk_radical(tag: str) -> bool:
    return len(tag) == 1 and 0x2E80 <= ord(tag) <= 0x2EFF


def _leftover_cleanup(
    existing_tags: Iterable[str],
    *,
    legacy_flat_values: Iterable[str],
) -> tuple[set[str], set[str]]:
    """Classe ou retire les derniers tags plats automatiques connus."""
    add: set[str] = set()
    remove: set[str] = set()
    existing = set(existing_tags)
    for tag in existing:
        if not tag or tag == "chinois" or tag.startswith(("chinois::", "_mdanki")):
            continue

        review_tag = _review_yoyo_tag(tag)
        if review_tag:
            add.add(review_tag)
            remove.add(tag)
            continue
        if tag == "vocabulary":
            add.add("chinois::type::vocabulaire")
            remove.add(tag)
            continue
        if tag == "sentence":
            add.add("chinois::type::phrase")
            remove.add(tag)
            continue
        if tag in CONTENT_TAGS:
            add.add(f"chinois::contenu::{CONTENT_TAGS[tag]}")
            remove.add(tag)
            continue
        if tag in DISCARD_ARTIFACT_TAGS or _is_cjk_radical(tag):
            remove.add(tag)
            continue
        # Ancienne correction tonale erronée observée sur 猫. Ne la retire que
        # lorsque la prononciation canonique correspondante est déjà présente.
        if tag == "máo" and f"{PINYIN_TAG_PREFIX}māo" in existing:
            remove.add(tag)
            continue
        if _INTEGRATED_RE.fullmatch(tag):
            remove.add(tag)
            continue
        if is_legacy_managed_tag(
            tag,
            legacy_flat_values=legacy_flat_values,
        ):
            remove.add(tag)
    return add, remove


def _merge_leftover_cleanup(
    update: TagUpdatePlan,
    *,
    existing_tags: Iterable[str],
    desired_tags: Iterable[str],
    legacy_flat_values: Iterable[str],
) -> TagUpdatePlan:
    existing = set(existing_tags)
    desired = set(desired_tags)
    add, remove = _leftover_cleanup(
        existing,
        legacy_flat_values=legacy_flat_values,
    )
    final = set(update.final)
    final.difference_update(remove)
    final.update(add)
    return TagUpdatePlan(
        add=tuple(sorted(final - existing)),
        remove=tuple(sorted(existing - final)),
        final=tuple(sorted(final)),
        preserved=tuple(sorted(final - desired - add)),
    )


def _integrated_source_tags(tags: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for tag in tags:
        if tag.startswith(
            "chinois::source::integrated_chinese::niveau::"
        ):
            result.add(tag)
            continue
        match = _INTEGRATED_RE.fullmatch(tag)
        if not match:
            continue
        value = (
            "chinois::source::integrated_chinese"
            "::niveau::01::partie::01"
            f"::lecon::{int(match.group('lesson')):02d}"
        )
        section = match.group("section")
        if section:
            normalized = f"{int(section):02d}" if section.isdigit() else "z"
            value += f"::section::{normalized}"
        result.add(value)
    return result


def _chinois_facile_source_tags(tags: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for tag in tags:
        if tag.startswith("chinois::source::le_chinois_facile::lecon::"):
            result.add(tag)
            continue
        match = _NUMBERED_LESSON_RE.fullmatch(tag)
        if match:
            result.add(
                "chinois::source::le_chinois_facile"
                f"::lecon::{int(match.group('lesson')):02d}"
            )
    return result


def _desired_tags(
    note: dict[str, Any],
    *,
    source_override: str = "",
) -> tuple[set[str], tuple[str, ...], tuple[str, ...]]:
    tags = tuple(str(tag) for tag in note.get("tags", []))
    source = _source_for_note(note, source_override)
    hanzi, traditional, pinyin = _note_text_fields(note)
    cjk_text = _cjk_only(hanzi, traditional)
    primary_cjk = _cjk_only(hanzi) or _cjk_only(traditional)
    warnings: list[str] = []

    if note.get("modelName") == "Huaxia Mnémotechnique v1":
        desired: set[str] = set()
        link_type = _field(note, "TypeLien")
        key = "".join(unique_cjk(_field(note, "Cle")))
        try:
            desired.add(mnemonic_tag(link_type, key))
        except ValueError as error:
            warnings.append(f"Bibliothèque mnémotechnique invalide : {error}")
        return desired, tuple(warnings), ()

    resolved_pinyin, plausible_pinyin = resolve_contextual_pinyin(
        primary_cjk,
        pinyin,
    )
    supplied_pinyin = " ".join(resolved_pinyin) if pinyin and plausible_pinyin else ""
    if pinyin and primary_cjk and not plausible_pinyin:
        warnings.append(
            "Pinyin du champ incohérent avec les Hanzi : utilisation du "
            "repli contextuel pypinyin."
        )
    fallback_pinyin = (
        resolved_pinyin
        if primary_cjk and not supplied_pinyin
        else ()
    )
    context = TagContext(
        hanzi=hanzi,
        traditional=traditional,
        pinyin=supplied_pinyin,
        source=source,
        explicit_components=_explicit_components(tags),
        audio_source=_audio_source(tags),
        fallback_pinyin=fallback_pinyin,
    )
    desired = set(build_managed_tags(context))
    ambiguous_legacy: tuple[str, ...] = ()

    if source == "yoyochinese":
        canonical = _canonical_yoyo_tags(tags)
        legacy_path, ambiguous_legacy = _legacy_yoyo_path(tags)
        desired.discard(source_tag("yoyochinese"))
        if canonical:
            desired.update(canonical)
        elif legacy_path:
            desired.add(legacy_path)
        else:
            desired.add(source_tag("yoyochinese"))
        warnings.extend(ambiguous_legacy)
    elif source == "integrated_chinese":
        detailed = _integrated_source_tags(tags)
        if detailed:
            desired.discard(source_tag(source))
            desired.update(detailed)
    elif source == "le_chinois_facile":
        detailed = _chinois_facile_source_tags(tags)
        if detailed:
            desired.discard(source_tag(source))
            desired.update(detailed)

    legacy_values = tuple(legacy_flat_pinyin_values(cjk_text, pinyin))
    return desired, tuple(warnings), legacy_values


def _label_for_note(note: dict[str, Any]) -> str:
    for field_name in ("Hanzi", "Mandarin", "Cle", "Content", "Recto"):
        value = visible_text(_field(note, field_name)).strip()
        if value:
            return value[:80]
    return str(note.get("noteId"))


def build_report(
    notes: Iterable[dict[str, Any]],
    *,
    cleanup_legacy: bool,
    source_by_note_id: Mapping[int, str] | None = None,
    query: str = TARGET_QUERY,
) -> MigrationReport:
    records: list[MigrationRecord] = []
    scanned = 0
    for note in notes:
        scanned += 1
        note_id = int(note["noteId"])
        desired, warnings, legacy_values = _desired_tags(
            note,
            source_override=(source_by_note_id or {}).get(note_id, ""),
        )
        existing = [str(tag) for tag in note.get("tags", [])]
        # An ambiguous source path is deliberately left in additive mode even
        # during cleanup; this preserves information until it can be resolved.
        safe_cleanup = cleanup_legacy and not warnings
        update = plan_tag_update(
            existing,
            desired,
            owned_prefixes=(
                (
                    HANZI_TAG_PREFIX,
                    PINYIN_TAG_PREFIX,
                    SOURCE_TAG_PREFIX,
                    AUDIO_SOURCE_TAG_PREFIX,
                    MNEMONIC_TAG_PREFIX,
                )
                if safe_cleanup
                else ()
            ),
            cleanup_legacy=safe_cleanup,
            legacy_flat_values=legacy_values,
        )
        if cleanup_legacy:
            update = _merge_leftover_cleanup(
                update,
                existing_tags=existing,
                desired_tags=desired,
                legacy_flat_values=legacy_values,
            )
        if update.add or update.remove or warnings:
            records.append(
                MigrationRecord(
                    note_id=note_id,
                    model=str(note.get("modelName") or ""),
                    label=_label_for_note(note),
                    add=update.add,
                    remove=update.remove,
                    preserved_count=len(update.preserved),
                    warnings=warnings,
                )
            )

    return MigrationReport(
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        mode="cleanup" if cleanup_legacy else "addition",
        cleanup_legacy=cleanup_legacy,
        query=query,
        notes_scanned=scanned,
        notes_changed=sum(bool(record.add or record.remove) for record in records),
        tags_added=sum(len(record.add) for record in records),
        tags_removed=sum(len(record.remove) for record in records),
        warnings=sum(len(record.warnings) for record in records),
        records=tuple(records),
    )


def _read_notes(
    url: str,
    note_ids: list[int],
    *,
    batch_size: int,
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for start in range(0, len(note_ids), batch_size):
        notes.extend(
            invoke_ankiconnect(
                "notesInfo",
                url=url,
                notes=note_ids[start : start + batch_size],
            )
            or []
        )
    return notes


def _source_map_from_decks(url: str) -> dict[int, str]:
    result: dict[int, str] = {}
    for source, deck_name in SOURCE_DECKS:
        note_ids = invoke_ankiconnect(
            "findNotes",
            url=url,
            query=f'deck:"{deck_name}"',
        ) or []
        for note_id in note_ids:
            result[int(note_id)] = source
    return result


def _write_report(report: MigrationReport, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def backup_chinese_deck(url: str, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = destination_dir / f"chinois-avant-tags-{stamp}.apkg"
    invoke_ankiconnect(
        "exportPackage",
        url=url,
        timeout=1_800,
        deck="chinois",
        path=str(destination),
        includeSched=True,
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise AnkiConnectError("La sauvegarde APKG du paquet chinois a échoué.")
    return destination


def prepare_live_report(
    url: str,
    *,
    query: str = TARGET_QUERY,
    note_ids: Iterable[int] = (),
    cleanup_legacy: bool = False,
    batch_size: int = 500,
) -> MigrationReport:
    """Construit un rapport depuis AnkiConnect sans modifier la collection."""
    selected_note_ids = list(dict.fromkeys(int(note_id) for note_id in note_ids))
    if not selected_note_ids:
        selected_note_ids = invoke_ankiconnect(
            "findNotes",
            url=url,
            query=query,
        ) or []
    notes = _read_notes(url, selected_note_ids, batch_size=batch_size)
    source_by_note_id = _source_map_from_decks(url)
    return build_report(
        notes,
        cleanup_legacy=cleanup_legacy,
        source_by_note_id=source_by_note_id,
        query=query,
    )


def _batched(values: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def apply_report(
    url: str,
    report: MigrationReport,
    *,
    batch_size: int,
) -> None:
    removals: dict[str, list[int]] = defaultdict(list)
    additions: dict[str, list[int]] = defaultdict(list)
    for record in report.records:
        for tag in record.remove:
            removals[tag].append(record.note_id)
        for tag in record.add:
            additions[tag].append(record.note_id)

    for tag, note_ids in sorted(removals.items()):
        for batch in _batched(note_ids, batch_size):
            invoke_ankiconnect(
                "removeTags",
                url=url,
                notes=batch,
                tags=tag,
            )
    for tag, note_ids in sorted(additions.items()):
        for batch in _batched(note_ids, batch_size):
            invoke_ankiconnect(
                "addTags",
                url=url,
                notes=batch,
                tags=tag,
            )


def _print_summary(report: MigrationReport, report_path: Path) -> None:
    print("=== Migration hiérarchique Huaxia ===")
    print(f"Mode : aperçu {report.mode}")
    print(f"Notes examinées : {report.notes_scanned}")
    print(f"Notes à modifier : {report.notes_changed}")
    print(f"Tags à ajouter : {report.tags_added}")
    print(f"Tags à retirer : {report.tags_removed}")
    print(f"Avertissements : {report.warnings}")
    print(f"Rapport complet : {report_path}")
    for record in report.records[:25]:
        print(
            f"- {record.note_id} [{record.model}] {record.label!r} : "
            f"+{len(record.add)} / -{len(record.remove)}"
        )
        for warning in record.warnings:
            print(f"  ! {warning}")
    if len(report.records) > 25:
        print(f"… {len(report.records) - 25} autre(s) entrée(s) dans le rapport JSON.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prévisualise la migration des tags du paquet chinois. "
            "Aucune écriture n’a lieu sans --apply."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Applique exactement les différences présentes dans le rapport.",
    )
    parser.add_argument(
        "--cleanup-legacy",
        action="store_true",
        help="Prépare la seconde phase qui retire les anciens tags automatiques.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=(
            f"Jeton requis avec --apply : {CONFIRM_ADD} pour l’ajout, "
            f"{CONFIRM_CLEANUP} pour le nettoyage."
        ),
    )
    parser.add_argument(
        "--note-id",
        type=int,
        action="append",
        default=[],
        help="Limite l’aperçu ou l’application à une note; option répétable.",
    )
    parser.add_argument(
        "--added-days",
        type=int,
        help=(
            "Limite aux cartes ajoutées depuis N jours dans le paquet chinois "
            "(par exemple --added-days 1 produit deck:\"chinois\" added:1)."
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help=f"Rapport JSON (défaut : {DEFAULT_REPORT}).",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"Dossier des sauvegardes APKG (défaut : {DEFAULT_BACKUP_DIR}).",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.batch_size < 1:
        raise SystemExit("--batch-size doit être supérieur à zéro.")
    if args.added_days is not None and args.added_days < 1:
        raise SystemExit("--added-days doit être supérieur à zéro.")
    if args.note_id and args.added_days is not None:
        raise SystemExit("--note-id et --added-days ne peuvent pas être combinés.")
    expected_confirmation = CONFIRM_CLEANUP if args.cleanup_legacy else CONFIRM_ADD
    if args.apply and args.confirm != expected_confirmation:
        raise SystemExit(
            f"Application refusée : utilisez --confirm {expected_confirmation}."
        )

    url = get_active_ankiconnect_url()
    if not url:
        raise SystemExit("AnkiConnect est inaccessible sur les ports 8766 et 8765.")

    query = (
        f"{TARGET_QUERY} added:{args.added_days}"
        if args.added_days is not None
        else TARGET_QUERY
    )
    report = prepare_live_report(
        url,
        query=query,
        note_ids=args.note_id,
        cleanup_legacy=args.cleanup_legacy,
        batch_size=args.batch_size,
    )
    report_path = args.report.expanduser().resolve()
    _write_report(report, report_path)
    _print_summary(report, report_path)

    if not args.apply:
        print("Aucune note Anki n’a été modifiée.")
        return 0
    if not report.notes_changed:
        print("Aucun changement à appliquer.")
        return 0

    backup_path = backup_chinese_deck(
        url,
        args.backup_dir.expanduser().resolve(),
    )
    print(f"Sauvegarde créée : {backup_path}")
    apply_report(url, report, batch_size=args.batch_size)
    print(
        f"Application terminée : {report.tags_added} ajout(s), "
        f"{report.tags_removed} retrait(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
