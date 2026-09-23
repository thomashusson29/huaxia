"""
Module de tagging automatique des caractères chinois, radicaux et pinyins pour Anki.
Génère une interdépendance complète des tags entre mots composés, caractères et composants.
"""

from pathlib import Path
import sys
import unicodedata
from typing import List, Set, Dict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from huaxia_tags import (  # noqa: E402
    AUDIO_SOURCE_TAG_PREFIX,
    HANZI_TAG_PREFIX,
    PINYIN_TAG_PREFIX,
    SOURCE_TAG_PREFIX,
    TagContext,
    YoyoCoursePath,
    build_managed_tags,
    is_legacy_managed_tag,
    normalize_pinyin_syllable,
    pinyin_syllables,
    pinyin_tokens,
    plan_tag_update,
)

# Essai d'import de pypinyin si disponible
try:
    import pypinyin
    HAS_PYPINYIN = True
except ImportError:
    HAS_PYPINYIN = False

# Dictionnaire de décomposition récursive des caractères complexes en leurs composants / radicaux clés
CHARACTER_COMPONENTS: Dict[str, List[str]] = {
    # Machines et technologies
    "机": ["木", "几"],
    "电": ["日", "乚"],
    "影": ["日", "京", "彡"],
    "话": ["讠", "舌"],
    "脑": ["月", "凶"],
    "飞": ["飞"],
    "升": ["丿", "十"],
    
    # Relations et pronoms
    "你": ["亻", "尔"],
    "我": ["手", "戈"],
    "他": ["亻", "乜"],
    "她": ["女", "乜"],
    "爱": ["爫", "冖", "友"],
    "好": ["女", "子"],
    
    # Éléments de la nature Chineasy / Yoyo
    "明": ["日", "月"],
    "休": ["人", "木"],
    "林": ["木", "木"],
    "森": ["木", "木", "木"],
    "炎": ["火", "火"],
    "焱": ["火", "火", "火"],
    "晶": ["日", "日", "日"],
    "淼": ["水", "水", "水"],
    "众": ["人", "人", "人"],
    "从": ["人", "人"],
    "本": ["木", "一"],
    "体": ["亻", "本"],
    "男": ["田", "力"],
    "妇": ["女", "彐"],
    "爸": ["父", "巴"],
    "妈": ["女", "马"],
    
    # Caractères courants avec composants
    "看": ["手", "目"],
    "听": ["口", "斤"],
    "说": ["讠", "兑"],
    "读": ["讠", "卖"],
    "写": ["冖", "与"],
    "学": ["⺌", "冖", "子"],
    "校": ["木", "交"],
    "家": ["宀", "豕"],
    "国": ["囗", "玉"],
    "中": ["口", "丨"],
    "文": ["文"],
    "字": ["宀", "子"],
    "语": ["讠", "吾"],
    
    # Verbes et actions
    "吃": ["口", "乞"],
    "喝": ["口", "曷"],
    "做": ["亻", "故"],
    "去": ["土", "厶"],
    "来": ["木", "米"],
    "想": ["相", "心"],
    "要": ["西", "女"],
    "给": ["纟", "合"],
    "买": ["乛", "头"],
    "卖": ["十", "买"],
    "付": ["亻", "寸"],
    "押": ["扌", "甲"],
    "租": ["禾", "且"],
    "房": ["户", "方"],
    "维": ["纟", "攸"],
    "修": ["亻", "攸"],
    "约": ["纟", "勺"],
}

# Mapping de pinyin secours pour radicaux/composants courants au cas où pypinyin ne les a pas
PINYIN_FALLBACK: Dict[str, str] = {
    "木": "mù",
    "几": "jī",
    "手": "shǒu",
    "扌": "shǒu",
    "日": "rì",
    "月": "yuè",
    "火": "huǒ",
    "水": "shuǐ",
    "氵": "shuǐ",
    "人": "rén",
    "亻": "rén",
    "女": "nǚ",
    "子": "zǐ",
    "口": "kǒu",
    "讠": "yán",
    "言": "yán",
    "宀": "mián",
    "纟": "sī",
    "土": "tǔ",
    "山": "shān",
    "目": "mù",
    "禾": "hé",
    "心": "xīn",
    "戈": "gē",
}

def is_cjk_char(ch: str) -> bool:
    """Vérifie si un caractère est un CJK Unified Ideograph."""
    return '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf' or '\u20000' <= ch <= '\u2a6df'

def get_char_pinyin(ch: str) -> str:
    """Retourne le pinyin accentué pour un caractère donné."""
    if ch in PINYIN_FALLBACK:
        return PINYIN_FALLBACK[ch]
    if HAS_PYPINYIN:
        py_list = pypinyin.pinyin(ch, style=pypinyin.Style.TONE)
        if py_list and py_list[0] and py_list[0][0]:
            res = py_list[0][0].strip()
            if res and not res.isdigit():
                return res
    return ""

def get_components_recursive(ch: str, visited: Set[str] = None) -> List[str]:
    """Retourne l'ancienne décomposition, uniquement pour nettoyer les tags v0."""
    if visited is None:
        visited = set()
    if ch in visited:
        return []
    visited.add(ch)
    
    components = []
    sub = CHARACTER_COMPONENTS.get(ch, [])
    for sub_ch in sub:
        components.append(sub_ch)
        components.extend(get_components_recursive(sub_ch, visited))
    return components

def get_contextual_pinyin(hanzi: str) -> List[str]:
    """Calcule le pinyin sur la séquence entière afin de respecter le contexte."""
    if not hanzi or not HAS_PYPINYIN:
        return []
    values = pypinyin.lazy_pinyin(hanzi, style=pypinyin.Style.TONE)
    return [
        normalized
        for value in values
        if (normalized := normalize_pinyin_syllable(value))
    ]


def _pinyin_base(value: str) -> str:
    normalized = unicodedata.normalize(
        "NFD",
        normalize_pinyin_syllable(value),
    )
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def resolve_contextual_pinyin(
    hanzi: str,
    pinyin: str,
) -> tuple[tuple[str, ...], bool]:
    """Découpe et valide le pinyin fourni, avec repli contextuel.

    Le booléen indique si le champ fourni était cohérent. Un pinyin concaténé
    comme ``xiǎojiě`` est accepté, mais renvoyé sous forme de syllabes.
    """
    tokens = tuple(pinyin_tokens(pinyin))
    characters = tuple(character for character in hanzi if is_cjk_char(character))
    if not characters:
        return tokens, bool(tokens)
    if not HAS_PYPINYIN:
        return tokens, bool(tokens)

    possible_by_character: List[Set[str]] = []
    for character in characters:
        readings = pypinyin.pinyin(
            character,
            style=pypinyin.Style.TONE,
            heteronym=True,
        )
        values = readings[0] if readings and readings[0] else []
        possible_by_character.append(
            {
                base
                for value in values
                if (base := _pinyin_base(value))
            }
        )

    fallback = tuple(get_contextual_pinyin("".join(characters)))
    if not tokens:
        return fallback, False

    # Dans l'erhua, le 儿 final est couramment écrit comme un simple suffixe
    # « r » (哪儿 -> nǎr). Pour les tags, il reste un Hanzi explicite : on
    # sépare donc la syllabe du caractère précédent et celle de 儿.
    erhua_slots = sum(character in {"儿", "兒"} for character in characters)
    if erhua_slots:
        expanded_tokens: list[str] = []
        for token in tokens:
            if (
                erhua_slots
                and token.endswith("r")
                and len(token) > 1
                and _pinyin_base(token) != "er"
            ):
                expanded_tokens.extend((token[:-1], "ér"))
                erhua_slots -= 1
            else:
                expanded_tokens.append(token)
        tokens = tuple(expanded_tokens)

    token_bases = tuple(_pinyin_base(token) for token in tokens)
    if len(token_bases) == len(possible_by_character):
        if all(
            token in possible
            for token, possible in zip(
                token_bases,
                possible_by_character,
                strict=True,
            )
        ):
            return tokens, True

    fallback_bases = tuple(_pinyin_base(token) for token in fallback)
    if (
        fallback
        and "".join(token_bases) == "".join(fallback_bases)
    ):
        return fallback, True

    supplied = set(token_bases)
    if all(bool(possible & supplied) for possible in possible_by_character):
        return tokens, True
    return fallback, False


def pinyin_is_plausible(hanzi: str, pinyin: str) -> bool:
    """Vérifie le pinyin fourni contre les lectures possibles de chaque Hanzi."""
    _, plausible = resolve_contextual_pinyin(hanzi, pinyin)
    return plausible


def legacy_flat_pinyin_values(hanzi: str, pinyin: str = "") -> List[str]:
    """Reproduit les pinyins plats historiques pour permettre leur retrait sûr."""
    values: Set[str] = set(pinyin_syllables(pinyin))
    for char in [value for value in hanzi if is_cjk_char(value)]:
        char_pinyin = get_char_pinyin(char)
        if char_pinyin:
            values.add(char_pinyin)
        for component in get_components_recursive(char):
            component_pinyin = get_char_pinyin(component)
            if component_pinyin:
                values.add(component_pinyin)
    return sorted(values)


def _source_from_legacy_tags(tags: List[str]) -> str:
    lowered = {tag.strip().lower() for tag in tags}
    if "chineasy" in lowered:
        return "chineasy"
    if lowered.intersection({"yoyo", "yoyo_chinese", "yoyochinese"}):
        return "yoyochinese"
    return ""


def _audio_source_from_legacy_tags(tags: List[str]) -> str:
    for tag in tags:
        if tag.startswith("audio_source::"):
            return tag.split("::", 1)[1]
    return ""


def generate_interdependent_tags(
    hanzi: str,
    base_tags: List[str] = None,
    *,
    traditional: str = "",
    pinyin: str = "",
    source: str = "",
    course_paths: tuple[YoyoCoursePath, ...] = (),
    explicit_components: tuple[str, ...] = (),
) -> List[str]:
    """
    Génère les tags hiérarchiques Huaxia et préserve les tags manuels.

    Les composants ne sont jamais déduits. ``CHARACTER_COMPONENTS`` reste
    disponible uniquement pour reconnaître les anciens tags plats lors d'une
    migration.
    """
    raw_tags = [
        cleaned
        for tag in (base_tags or [])
        if (cleaned := tag.strip().replace(" ", "_"))
    ]
    primary_text = hanzi if any(is_cjk_char(char) for char in hanzi) else traditional
    resolved_pinyin, plausible = resolve_contextual_pinyin(primary_text, pinyin)
    supplied_pinyin = " ".join(resolved_pinyin) if pinyin and plausible else ""
    fallback_pinyin = () if supplied_pinyin else resolved_pinyin
    resolved_source = source or _source_from_legacy_tags(raw_tags)
    context = TagContext(
        hanzi=hanzi,
        traditional=traditional,
        pinyin=supplied_pinyin,
        source=resolved_source,
        course_paths=course_paths,
        explicit_components=explicit_components,
        audio_source=_audio_source_from_legacy_tags(raw_tags),
        fallback_pinyin=fallback_pinyin,
    )
    managed = set(build_managed_tags(context))
    legacy_values = legacy_flat_pinyin_values(hanzi + traditional, pinyin)
    preserved = {
        tag
        for tag in raw_tags
        if not is_legacy_managed_tag(
            tag,
            legacy_flat_values=legacy_values,
        )
    }
    return sorted(managed | preserved)


def plan_interdependent_tag_update(
    existing_tags: List[str],
    hanzi: str,
    base_tags: List[str] = None,
    *,
    traditional: str = "",
    pinyin: str = "",
    source: str = "",
    course_paths: tuple[YoyoCoursePath, ...] = (),
    explicit_components: tuple[str, ...] = (),
    cleanup_legacy: bool = True,
):
    desired = generate_interdependent_tags(
        hanzi,
        base_tags,
        traditional=traditional,
        pinyin=pinyin,
        source=source,
        course_paths=course_paths,
        explicit_components=explicit_components,
    )
    legacy_values = legacy_flat_pinyin_values(hanzi + traditional, pinyin)
    return plan_tag_update(
        existing_tags,
        desired,
        owned_prefixes=(
            AUDIO_SOURCE_TAG_PREFIX,
            HANZI_TAG_PREFIX,
            PINYIN_TAG_PREFIX,
            SOURCE_TAG_PREFIX,
        ),
        cleanup_legacy=cleanup_legacy,
        legacy_flat_values=legacy_values,
    )
