"""Canonical tag schema shared by the Huaxia Chinese tools.

The module deliberately has no Anki dependency.  Importers, migration tools,
and Obsidian exporters can therefore use the exact same normalization rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
import unicodedata
from typing import Iterable, Sequence


ROOT_TAG = "chinois"
HANZI_TAG_PREFIX = f"{ROOT_TAG}::caracteres::hanzi::"
PINYIN_TAG_PREFIX = f"{ROOT_TAG}::caracteres::pinyin::"
COMPONENT_TAG_PREFIX = f"{ROOT_TAG}::caracteres::composant::"
SOURCE_TAG_PREFIX = f"{ROOT_TAG}::source::"
YOYO_SOURCE_TAG_PREFIX = f"{SOURCE_TAG_PREFIX}yoyochinese"
MNEMONIC_TAG_PREFIX = f"{ROOT_TAG}::mnemonique::"
AUDIO_SOURCE_TAG_PREFIX = f"{ROOT_TAG}::audio::source::"

TECHNICAL_TAG_PREFIXES = ("_mdanki::", "_mdanki_replaced::")
VALID_MNEMONIC_LINK_TYPES = {"caractere", "mot", "composant"}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PINYIN_TOKEN_RE = re.compile(
    r"[A-Za-z"
    r"üÜ"
    r"āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ"
    r"ĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙǕǗǙǛ"
    r"ńňǹŃŇǸḿḾêÊ]+[1-5]?"
)
_LEGACY_STRUCTURAL_RE = re.compile(
    r"^(?:"
    r"(?:course|level|unit|lesson)::.+"
    r"|(?:unit|lesson|lecon)\d+"
    r"|IC1\.1_L\d+(?:_(?:\d+|Z))?"
    r"|beginner_conversation(?:::.+)?"
    r")$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class YoyoCoursePath:
    course: str
    level: int | str
    unit: int | str
    lesson: int | str


@dataclass(frozen=True)
class TagContext:
    hanzi: str = ""
    traditional: str = ""
    pinyin: str = ""
    source: str = ""
    course_paths: tuple[YoyoCoursePath, ...] = ()
    explicit_components: tuple[str, ...] = ()
    mnemonic_link_type: str = ""
    mnemonic_key: str = ""
    audio_source: str = ""
    fallback_pinyin: tuple[str, ...] = ()


@dataclass(frozen=True)
class TagUpdatePlan:
    add: tuple[str, ...]
    remove: tuple[str, ...]
    final: tuple[str, ...]
    preserved: tuple[str, ...]


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
    without_tags = _HTML_TAG_RE.sub(" ", value or "")
    return unicodedata.normalize("NFKC", unescape(without_tags))


def unique_cjk(*values: str) -> tuple[str, ...]:
    characters: list[str] = []
    seen: set[str] = set()
    for value in values:
        for character in visible_text(value):
            if is_cjk_character(character) and character not in seen:
                characters.append(character)
                seen.add(character)
    return tuple(characters)


def slugify(value: str, fallback: str = "") -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")
    return slug or fallback


_TONE_MARKS = {
    "a": "āáǎà",
    "e": "ēéěè",
    "i": "īíǐì",
    "o": "ōóǒò",
    "u": "ūúǔù",
    "ü": "ǖǘǚǜ",
    "n": "ńńňǹ",
    "m": "ḿḿḿḿ",
}


def _tone_number_to_mark(value: str) -> str:
    if not value or value[-1] not in "12345":
        return value
    tone = int(value[-1])
    base = value[:-1]
    if tone == 5 or not base:
        return base

    lowered = base.lower()
    if "a" in lowered:
        index = lowered.index("a")
    elif "e" in lowered:
        index = lowered.index("e")
    elif "ou" in lowered:
        index = lowered.index("o")
    else:
        vowel_indexes = [
            index for index, char in enumerate(lowered) if char in "aeiouünm"
        ]
        if not vowel_indexes:
            return base
        index = vowel_indexes[-1]

    vowel = lowered[index]
    marked = _TONE_MARKS[vowel][tone - 1]
    return base[:index] + marked + base[index + 1 :]


def normalize_pinyin_syllable(value: str) -> str:
    normalized = unicodedata.normalize("NFC", (value or "").strip().lower())
    normalized = normalized.replace("u:", "ü").replace("v", "ü")
    normalized = re.sub(r"[^a-züāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹḿê1-5]", "", normalized)
    return unicodedata.normalize("NFC", _tone_number_to_mark(normalized))


def pinyin_tokens(value: str) -> tuple[str, ...]:
    """Retourne les éléments de pinyin dans l'ordre, doublons compris."""
    normalized_source = unicodedata.normalize(
        "NFC",
        visible_text(value).replace("u:", "ü").replace("U:", "Ü"),
    )
    normalized_source = normalized_source.translate(
        str.maketrans(
            {
                "ɡ": "g",
                "õ": "ō",
                "Õ": "Ō",
            }
        )
    )
    normalized_source = re.sub(
        r"\(\s*r\s*\)",
        " er2",
        normalized_source,
        flags=re.IGNORECASE,
    )
    result: list[str] = []
    for raw in _PINYIN_TOKEN_RE.findall(normalized_source):
        syllable = normalize_pinyin_syllable(raw)
        if syllable:
            result.append(syllable)
    return tuple(result)


def pinyin_syllables(value: str) -> tuple[str, ...]:
    """Retourne les syllabes distinctes utilisées comme valeurs de tags."""
    return tuple(dict.fromkeys(pinyin_tokens(value)))


def anki_to_obsidian_tag(tag: str) -> str:
    return (tag or "").strip().replace("::", "/")


def obsidian_to_anki_tag(tag: str) -> str:
    value = (tag or "").strip().lstrip("#")
    value = re.sub(r"\s+", "_", value)
    return value.replace("/", "::")


def _padded_number(value: int | str, width: int, label: str) -> str:
    text = str(value).strip()
    if not text.isdigit():
        raise ValueError(f"{label} doit être numérique : {value!r}")
    return f"{int(text):0{width}d}"


def yoyo_course_tag(path: YoyoCoursePath) -> str:
    course = slugify(path.course, "cours_inconnu")
    level = _padded_number(path.level, 2, "Le niveau")
    unit = _padded_number(path.unit, 3, "L’unité")
    lesson = _padded_number(path.lesson, 2, "La leçon")
    return (
        f"{YOYO_SOURCE_TAG_PREFIX}::cours::{course}"
        f"::niveau::{level}::unite::{unit}::lecon::{lesson}"
    )


def source_tag(source: str) -> str:
    aliases = {
        "yoyo": "yoyochinese",
        "yoyo_chinese": "yoyochinese",
        "yoyochinese": "yoyochinese",
        "chineasy": "chineasy",
        "integrated": "integrated_chinese",
        "integrated_chinese": "integrated_chinese",
        "lechinoisfacile": "le_chinois_facile",
        "le_chinois_facile": "le_chinois_facile",
    }
    raw = (source or "").strip().lower()
    normalized = aliases.get(raw, slugify(raw))
    return f"{SOURCE_TAG_PREFIX}{normalized}" if normalized else ""


def mnemonic_tag(link_type: str, key: str) -> str:
    normalized_type = (link_type or "").strip().lower()
    if normalized_type not in VALID_MNEMONIC_LINK_TYPES:
        raise ValueError("Le type mnémotechnique doit être caractère, mot ou composant.")
    normalized_key = re.sub(r"\s+", "", unicodedata.normalize("NFKC", key or ""))
    normalized_key = normalized_key.replace("::", "_")
    if not normalized_key:
        raise ValueError("La clé mnémotechnique ne peut pas être vide.")
    return (
        f"{MNEMONIC_TAG_PREFIX}type::{normalized_type}"
        f"::cle::{normalized_key}"
    )


def component_tag(key: str) -> str:
    normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", key or ""))
    normalized = normalized.replace("::", "_")
    if not normalized:
        raise ValueError("La clé de composant ne peut pas être vide.")
    return f"{COMPONENT_TAG_PREFIX}{normalized}"


def audio_source_tag(provider: str) -> str:
    aliases = {
        "edgetts": "edge_tts",
        "edge-tts": "edge_tts",
        "edge_tts": "edge_tts",
        "gtts": "gtts",
        "youdao": "youdao",
        "baidu": "baidu",
    }
    normalized = aliases.get((provider or "").strip().lower(), slugify(provider))
    return f"{AUDIO_SOURCE_TAG_PREFIX}{normalized}" if normalized else ""


def build_managed_tags(context: TagContext) -> tuple[str, ...]:
    tags: set[str] = set()
    for character in unique_cjk(context.hanzi, context.traditional):
        tags.add(f"{HANZI_TAG_PREFIX}{character}")

    syllables = pinyin_syllables(context.pinyin)
    if not syllables:
        syllables = tuple(
            normalized
            for value in context.fallback_pinyin
            if (normalized := normalize_pinyin_syllable(value))
        )
    for syllable in syllables:
        tags.add(f"{PINYIN_TAG_PREFIX}{syllable}")

    if context.course_paths:
        tags.update(yoyo_course_tag(path) for path in context.course_paths)
    elif context.source:
        tag = source_tag(context.source)
        if tag:
            tags.add(tag)

    for component in context.explicit_components:
        tags.add(component_tag(component))

    if context.mnemonic_link_type or context.mnemonic_key:
        tags.add(mnemonic_tag(context.mnemonic_link_type, context.mnemonic_key))

    if context.audio_source:
        tag = audio_source_tag(context.audio_source)
        if tag:
            tags.add(tag)

    return tuple(sorted(tags))


def is_technical_tag(tag: str) -> bool:
    return any((tag or "").startswith(prefix) for prefix in TECHNICAL_TAG_PREFIXES)


def is_legacy_managed_tag(
    tag: str,
    *,
    legacy_flat_values: Iterable[str] = (),
) -> bool:
    value = (tag or "").strip()
    if not value or is_technical_tag(value):
        return False
    if value in {
        "chineasy",
        "lechinoisfacile",
        "yoyochinese",
        "yoyo_chinese",
        "audio_auto",
        "chinois::mnemotechnique",
    }:
        return True
    if value.startswith(("audio_source::", "huaxia::mnemo::composant::")):
        return True
    if _LEGACY_STRUCTURAL_RE.fullmatch(value):
        return True
    if len(value) == 1 and is_cjk_character(value):
        return True
    normalized_legacy = {
        normalized
        for raw in legacy_flat_values
        if (normalized := normalize_pinyin_syllable(raw))
    }
    return normalize_pinyin_syllable(value) in normalized_legacy


def plan_tag_update(
    existing_tags: Sequence[str],
    desired_tags: Iterable[str],
    *,
    owned_prefixes: Sequence[str] = (),
    cleanup_legacy: bool = False,
    legacy_flat_values: Iterable[str] = (),
) -> TagUpdatePlan:
    existing = {tag.strip() for tag in existing_tags if tag and tag.strip()}
    desired = {tag.strip() for tag in desired_tags if tag and tag.strip()}

    remove: set[str] = set()
    for tag in existing:
        if is_technical_tag(tag):
            continue
        # Dans Anki, retirer le parent ``chinois`` retire aussi tous ses
        # descendants hiérarchiques. On le conserve donc toujours : il est
        # inoffensif et ne peut pas être nettoyé sans détruire les nouveaux
        # tags qui viennent d'être ajoutés.
        if tag == ROOT_TAG:
            continue
        if any(tag.startswith(prefix) for prefix in owned_prefixes) and tag not in desired:
            remove.add(tag)
            continue
        if cleanup_legacy and is_legacy_managed_tag(
            tag,
            legacy_flat_values=legacy_flat_values,
        ):
            remove.add(tag)

    add = desired - existing
    final = (existing - remove) | desired
    preserved = (existing - remove) - desired
    return TagUpdatePlan(
        add=tuple(sorted(add)),
        remove=tuple(sorted(remove)),
        final=tuple(sorted(final)),
        preserved=tuple(sorted(preserved)),
    )
