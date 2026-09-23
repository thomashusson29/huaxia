#!/usr/bin/env python3
"""Create one Yoyo Chinese Anki package per course.

The exporter deliberately stays separate from the crawler.  It receives
completed lesson plans, merges cards that share the same Yoyo id, preserves
all lesson tags, and embeds the original normal/slow audio files.
"""

from __future__ import annotations

import ast
import hashlib
import html
import os
from pathlib import Path
from typing import Any, Iterable


MODEL_NAME = "Yoyo Chinese Model v2"
MODEL_ID = 2060721001
FIELD_NAMES = [
    "Hanzi",
    "Traditional",
    "Pinyin",
    "Anglais",
    "Explication",
    "ImageMnemo",
    "Audio",
    "AudioLent",
    "YoyoId",
    "Source",
]


class AnkiExportError(RuntimeError):
    pass


def ensure_genanki_available() -> None:
    try:
        import genanki  # noqa: F401
    except ModuleNotFoundError as exc:
        raise AnkiExportError(
            "Le module genanki est requis pour créer les paquets .apkg. "
            "Lancez « Lancer le téléchargeur.command », ou installez "
            "yoyochinese/requirements.txt."
        ) from exc


def _stable_id(namespace: str, value: str) -> int:
    digest = hashlib.sha256(f"{namespace}\0{value}".encode("utf-8")).digest()
    return 1_000_000_000 + int.from_bytes(digest[:4], "big") % 1_000_000_000


def _existing_model_templates() -> dict[str, str]:
    """Read the already-used Anki layout without importing its dependencies."""
    source = (
        Path(__file__).resolve().parent.parent
        / "anki_characters"
        / "chineasy_to_anki"
        / "src"
        / "anki_exporter.py"
    )
    if not source.is_file():
        return {}
    wanted = {"MODEL_CSS", "CARD1_FRONT", "CARD1_BACK", "CARD2_FRONT", "CARD2_BACK"}
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}
    values: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in wanted:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
        if isinstance(value, str):
            values[target.id] = value
    return values if wanted.issubset(values) else {}


_FALLBACK_CSS = """
.card { font-family: -apple-system, sans-serif; text-align: center; padding: 20px; }
.hanzi { font-size: 82px; color: #e11d48; margin: 18px 0; }
.traditional { font-size: 34px; color: #64748b; }
.pinyin { font-size: 30px; color: #0284c7; margin: 12px; }
.english { font-size: 24px; color: #16a34a; margin: 12px; }
.story { color: #64748b; line-height: 1.5; margin-top: 18px; }
.slow-audio { margin: 12px; font-size: 14px; color: #64748b; }
"""

_FALLBACK_CARD1_FRONT = '<div class="card"><div class="hanzi">{{Hanzi}}</div></div>'
_FALLBACK_CARD1_BACK = """
<div class="card">
  <div class="hanzi">{{Hanzi}}</div>
  {{#Traditional}}<div class="traditional">{{Traditional}}</div>{{/Traditional}}
  <div class="pinyin">{{Pinyin}} <span class="audio-container">{{Audio}}</span></div>
  {{#AudioLent}}<div class="slow-audio">Audio lent : {{AudioLent}}</div>{{/AudioLent}}
  <div class="english">{{Anglais}}</div>
  <div class="story">{{Explication}}</div>
</div>
"""
_FALLBACK_CARD2_FRONT = """
<div class="card">
  <div class="audio-container">{{Audio}}</div>
  <div>{{type:Pinyin}}</div>
</div>
"""
_FALLBACK_CARD2_BACK = _FALLBACK_CARD1_BACK


def model_layout() -> tuple[str, str, str, str, str]:
    existing = _existing_model_templates()
    if existing:
        card1_back = _augment_back(existing["CARD1_BACK"])
        card2_back = _augment_back(existing["CARD2_BACK"])
        return (
            existing["MODEL_CSS"] + "\n" + _FALLBACK_CSS,
            existing["CARD1_FRONT"],
            card1_back,
            existing["CARD2_FRONT"],
            card2_back,
        )
    return (
        _FALLBACK_CSS,
        _FALLBACK_CARD1_FRONT,
        _FALLBACK_CARD1_BACK,
        _FALLBACK_CARD2_FRONT,
        _FALLBACK_CARD2_BACK,
    )


def _augment_back(template: str) -> str:
    if "{{Traditional}}" not in template:
        marker = '<div class="pinyin">'
        traditional = (
            '{{#Traditional}}<div class="traditional">{{Traditional}}</div>'
            "{{/Traditional}}\n    "
        )
        template = template.replace(marker, traditional + marker, 1)
    if "{{AudioLent}}" not in template:
        marker = "{{#Explication}}"
        slow = (
            '{{#AudioLent}}<div class="slow-audio">Audio lent : '
            "{{AudioLent}}</div>{{/AudioLent}}\n    "
        )
        template = template.replace(marker, slow + marker, 1)
    return template


def _asset_paths(card: Any) -> tuple[str, str]:
    normal = ""
    slow = ""
    for asset in getattr(card, "assets", []):
        if asset.kind == "flashcard_audio_normal":
            normal = asset.path
        elif asset.kind == "flashcard_audio_slow":
            slow = asset.path
    return normal, slow


def collect_course_cards(plans: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """Merge identical Yoyo cards while accumulating their lesson tags."""
    courses: dict[str, dict[str, Any]] = {}
    for plan in plans:
        if not getattr(plan, "flashcards", None):
            continue
        course_key = plan.course or plan.course_title
        course = courses.setdefault(
            course_key,
            {
                "course_title": plan.course_title,
                "course_slug": plan.course,
                "cards": {},
            },
        )
        for card in plan.flashcards:
            normal_path, slow_path = _asset_paths(card)
            card_key = card.flashcard_id or f"{plan.lesson_id}:{card.code}:{card.index_number}"
            record = course["cards"].get(card_key)
            lesson_label = f"{plan.code} — {plan.title}"
            if record is None:
                record = {
                    "id": card_key,
                    "code": card.code,
                    "index_number": card.index_number,
                    "simplified": card.simplified,
                    "traditional": card.traditional,
                    "pinyin": card.pinyin,
                    "english": card.english,
                    "normal_path": normal_path,
                    "slow_path": slow_path,
                    "tags": set(card.tags),
                    "lessons": {lesson_label},
                    "sources": {plan.lesson_url},
                }
                course["cards"][card_key] = record
            else:
                record["tags"].update(card.tags)
                record["lessons"].add(lesson_label)
                record["sources"].add(plan.lesson_url)
                if not record["normal_path"]:
                    record["normal_path"] = normal_path
                if not record["slow_path"]:
                    record["slow_path"] = slow_path
    return courses


def collect_all_cards(plans: Iterable[Any]) -> list[dict[str, Any]]:
    """Return a single stable card list suitable for the AnkiConnect bulk deck."""
    merged: dict[str, dict[str, Any]] = {}
    for course in collect_course_cards(plans).values():
        for card_id, card in course["cards"].items():
            existing = merged.get(card_id)
            if existing is None:
                merged[card_id] = card
                continue
            existing["tags"].update(card["tags"])
            existing["lessons"].update(card["lessons"])
            existing["sources"].update(card["sources"])
            if not existing["normal_path"]:
                existing["normal_path"] = card["normal_path"]
            if not existing["slow_path"]:
                existing["slow_path"] = card["slow_path"]
    return sorted(
        merged.values(),
        key=lambda item: (item["code"], item["index_number"], item["id"]),
    )


def note_fields(card: dict[str, Any], normal_tag: str, slow_tag: str) -> dict[str, str]:
    traditional = card["traditional"]
    if traditional == card["simplified"]:
        traditional = ""
    lessons = sorted(card["lessons"])
    sources = sorted(card["sources"])
    explanation = "Leçon(s) : " + "; ".join(lessons)
    values = [
        html.escape(card["simplified"]),
        html.escape(traditional),
        html.escape(card["pinyin"]),
        html.escape(card["english"]),
        html.escape(explanation),
        "",
        normal_tag,
        slow_tag,
        html.escape(card["id"]),
        "<br>".join(html.escape(source) for source in sources),
    ]
    return dict(zip(FIELD_NAMES, values, strict=True))


def _sound_tag(path_value: str, media: dict[str, str]) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_file() or path.stat().st_size == 0:
        return ""
    filename = path.name
    previous = media.get(filename)
    if previous and Path(previous).resolve() != path.resolve():
        raise AnkiExportError(f"Deux sons Anki portent le même nom: {filename}")
    media[filename] = str(path.resolve())
    return f"[sound:{filename}]"


def export_course_packages(
    plans: Iterable[Any],
    output_root: Path,
    *,
    selection: bool = False,
) -> list[dict[str, Any]]:
    """Write one APKG per course and return manifest-friendly results."""
    ensure_genanki_available()
    import genanki

    css, card1_front, card1_back, card2_front, card2_back = model_layout()
    model = genanki.Model(
        MODEL_ID,
        MODEL_NAME,
        fields=[{"name": name} for name in FIELD_NAMES],
        templates=[
            {"name": "1. Reconnaissance Visuelle", "qfmt": card1_front, "afmt": card1_back},
            {"name": "2. Écoute Audio & Écriture", "qfmt": card2_front, "afmt": card2_back},
        ],
        css=css,
    )

    results: list[dict[str, Any]] = []
    for course in collect_course_cards(plans).values():
        course_title = course["course_title"]
        deck_name = f"chinois::yoyo_chinese::{course_title}"
        deck = genanki.Deck(_stable_id("deck", course["course_slug"]), deck_name)
        media: dict[str, str] = {}
        ordered_cards = sorted(
            course["cards"].values(),
            key=lambda item: (item["code"], item["index_number"], item["id"]),
        )
        for card in ordered_cards:
            normal_tag = _sound_tag(card["normal_path"], media)
            slow_tag = _sound_tag(card["slow_path"], media)
            fields = note_fields(card, normal_tag, slow_tag)
            note = genanki.Note(
                model=model,
                guid=genanki.guid_for("yoyochinese", card["id"]),
                fields=[fields[name] for name in FIELD_NAMES],
                tags=sorted(card["tags"]),
            )
            deck.add_note(note)

        course_folder = (
            output_root
            / "Courses"
            / _safe_component(course_title, course["course_slug"])
            / "Anki"
        )
        course_folder.mkdir(parents=True, exist_ok=True)
        suffix = " - sélection" if selection else ""
        destination = course_folder / f"{_safe_component(course_title, 'Yoyo Chinese')}{suffix}.apkg"
        temporary = destination.with_name(destination.name + ".tmp")
        package = genanki.Package(deck)
        package.media_files = list(media.values())
        package.write_to_file(str(temporary))
        os.replace(temporary, destination)
        results.append(
            {
                "course": course["course_slug"],
                "course_title": course_title,
                "deck_name": deck_name,
                "path": str(destination),
                "card_count": len(ordered_cards),
                "media_count": len(media),
                "selection": selection,
            }
        )
    return results


def _safe_component(value: str, fallback: str) -> str:
    cleaned = "".join("-" if char in '\\/:*?\"<>|' else char for char in value).strip(" .-")
    return (cleaned or fallback)[:120]
