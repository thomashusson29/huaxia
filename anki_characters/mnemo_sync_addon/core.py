from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from html import escape, unescape
import posixpath
import re
import unicodedata
from typing import Iterable, Sequence
from urllib.parse import unquote, urlsplit


AUTO_START = "<!-- HUAXIA_MNEMO_AUTO_START -->"
AUTO_END = "<!-- HUAXIA_MNEMO_AUTO_END -->"
IMPORT_START = "<!-- HUAXIA_MNEMO_IMPORT_START -->"
IMPORT_END = "<!-- HUAXIA_MNEMO_IMPORT_END -->"
COMPONENT_TAG_PREFIX = "chinois::caracteres::composant::"
MNEMONIC_TAG_PREFIX = "chinois::mnemonique::"
VALID_LINK_TYPES = {"caractere", "mot", "composant"}

_AUTO_BLOCK_RE = re.compile(
    re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END),
    flags=re.DOTALL,
)
_KNOWN_MARKERS_RE = re.compile(
    "|".join(
        re.escape(marker)
        for marker in (AUTO_START, AUTO_END, IMPORT_START, IMPORT_END)
    )
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_IMG_SRC_RE = re.compile(
    r"<img\b[^>]*\bsrc\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s>]+))",
    flags=re.IGNORECASE,
)
_CLOZE_OR_SOUND_RE = re.compile(
    r"\{\{c(?P<cloze>\d+)::|\[sound:(?P<sound>[^\]]+)\]",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class MnemonicEntry:
    mnemonic_id: str
    link_type: str
    key: str
    content: str
    description: str = ""
    source: str = ""


@dataclass(frozen=True)
class RenderResult:
    html: str
    included_ids: tuple[str, ...]
    skipped_ids: tuple[str, ...]


def enhanced_cloze_audio_counts(
    content: str,
    cloze_number: int,
) -> tuple[Counter[str], Counter[str]]:
    """Return all Content audio and the subset related to one Cloze card.

    A sound is associated with the closest preceding Cloze. Sounds appearing
    before the first Cloze are treated as global and remain available on every
    card.
    """
    all_audio: Counter[str] = Counter()
    selected_audio: Counter[str] = Counter()
    current_cloze: int | None = None

    for match in _CLOZE_OR_SOUND_RE.finditer(content or ""):
        cloze = match.group("cloze")
        if cloze is not None:
            current_cloze = int(cloze)
            continue

        filename = (match.group("sound") or "").strip()
        if not filename:
            continue
        all_audio[filename] += 1
        if current_cloze is None or current_cloze == cloze_number:
            selected_audio[filename] += 1

    return all_audio, selected_audio


def is_cjk_character(character: str) -> bool:
    if len(character) != 1:
        return False
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x2EBEF
        or 0x30000 <= codepoint <= 0x323AF
    )


def visible_text(value: str) -> str:
    without_tags = _HTML_TAG_RE.sub("", value or "")
    return unicodedata.normalize("NFKC", unescape(without_tags))


def extract_cjk(value: str) -> tuple[str, ...]:
    return tuple(character for character in visible_text(value) if is_cjk_character(character))


def unique_cjk(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(extract_cjk(value)))


def normalize_key(value: str) -> str:
    return "".join(extract_cjk(value))


def validate_entry(entry: MnemonicEntry) -> None:
    if not entry.mnemonic_id.strip():
        raise ValueError("La mnémotechnique doit posséder un identifiant.")
    if entry.link_type not in VALID_LINK_TYPES:
        raise ValueError("Le type de lien doit être caractère, mot ou composant.")

    normalized = normalize_key(entry.key)
    if not normalized or normalized != entry.key:
        raise ValueError("La clé doit contenir uniquement des caractères chinois.")
    if not entry.content.strip():
        raise ValueError("Une image mnémotechnique est obligatoire.")


def library_tag(link_type: str, key: str) -> str:
    normalized_type = (link_type or "").strip()
    if normalized_type not in VALID_LINK_TYPES:
        raise ValueError("Le type de lien doit être caractère, mot ou composant.")
    normalized_key = normalize_key(key)
    if not normalized_key or normalized_key != key:
        raise ValueError("La clé doit contenir uniquement des caractères chinois.")
    return (
        f"{MNEMONIC_TAG_PREFIX}type::{normalized_type}"
        f"::cle::{normalized_key}"
    )


def note_matches(
    entry: MnemonicEntry,
    hanzi: str,
    traditional: str,
    tags: Sequence[str],
    note_id: int | None = None,
) -> bool:
    validate_entry(entry)
    if note_id is not None and entry.mnemonic_id == f"chineasy-{note_id}":
        return False
    normalized_fields = (normalize_key(hanzi), normalize_key(traditional))

    if entry.link_type == "caractere":
        return any(entry.key in value for value in normalized_fields if value)
    if entry.link_type == "mot":
        return any(entry.key in value for value in normalized_fields if value)
    return f"{COMPONENT_TAG_PREFIX}{entry.key}" in set(tags)


def strip_auto_block(value: str) -> str:
    return _AUTO_BLOCK_RE.sub("", value or "").strip()


def source_content(value: str) -> str:
    return _KNOWN_MARKERS_RE.sub("", strip_auto_block(value)).strip()


def image_sources(value: str) -> tuple[str, ...]:
    sources: list[str] = []
    for match in _IMG_SRC_RE.finditer(value or ""):
        source = next((group for group in match.groups() if group), "")
        if source:
            sources.append(unescape(source).strip())
    return tuple(sources)


def media_filename_from_src(source: str) -> str:
    value = (source or "").strip()
    if not value:
        return ""

    parsed = urlsplit(value)
    if parsed.scheme.lower() in {"data", "blob"}:
        return ""
    path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0]
    filename = unquote(posixpath.basename(path))
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        return ""
    return filename


def _content_fingerprint(value: str) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    return sha256(compact.encode("utf-8")).hexdigest()


def render_mnemo_auto(
    existing_value: str,
    entries: Iterable[MnemonicEntry],
) -> RenderResult:
    manual = strip_auto_block(existing_value)
    manual_sources = set(image_sources(manual))
    seen_sources = set(manual_sources)
    seen_fingerprints = {_content_fingerprint(manual)} if manual else set()
    seen_ids: set[str] = set()
    included: list[str] = []
    skipped: list[str] = []
    sections: list[str] = []

    for entry in entries:
        validate_entry(entry)
        content = source_content(entry.content)
        sources = set(image_sources(content))
        fingerprint = _content_fingerprint(content)

        duplicate = (
            entry.mnemonic_id in seen_ids
            or bool(sources & seen_sources)
            or fingerprint in seen_fingerprints
        )
        if duplicate:
            skipped.append(entry.mnemonic_id)
            continue

        seen_ids.add(entry.mnemonic_id)
        seen_sources.update(sources)
        seen_fingerprints.add(fingerprint)
        included.append(entry.mnemonic_id)

        description = ""
        if entry.description.strip():
            description = (
                '<div class="huaxia-mnemo-description">'
                f"{escape(entry.description.strip())}"
                "</div>"
            )
        sections.append(
            '<section class="huaxia-mnemo-item" '
            f'data-mnemo-id="{escape(entry.mnemonic_id, quote=True)}" '
            f'data-mnemo-type="{escape(entry.link_type, quote=True)}" '
            f'data-mnemo-key="{escape(entry.key, quote=True)}">'
            f'<div class="huaxia-mnemo-content">{content}</div>'
            f"{description}"
            "</section>"
        )

    if not sections:
        return RenderResult(
            html=manual,
            included_ids=tuple(included),
            skipped_ids=tuple(skipped),
        )

    auto_block = (
        f"{AUTO_START}\n"
        '<div class="huaxia-mnemo-auto">\n'
        + "\n".join(sections)
        + "\n</div>\n"
        f"{AUTO_END}"
    )
    combined = f"{manual}\n{auto_block}".strip() if manual else auto_block
    return RenderResult(
        html=combined,
        included_ids=tuple(included),
        skipped_ids=tuple(skipped),
    )
