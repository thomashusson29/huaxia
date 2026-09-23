from __future__ import annotations

import unittest

from huaxia_tags import (
    COMPONENT_TAG_PREFIX,
    HANZI_TAG_PREFIX,
    PINYIN_TAG_PREFIX,
    TECHNICAL_TAG_PREFIXES,
    YOYO_SOURCE_TAG_PREFIX,
    TagContext,
    YoyoCoursePath,
    anki_to_obsidian_tag,
    build_managed_tags,
    obsidian_to_anki_tag,
    pinyin_syllables,
    pinyin_tokens,
    plan_tag_update,
)


class HuaxiaTagsTests(unittest.TestCase):
    def test_builds_character_and_contextual_pinyin_tags(self) -> None:
        tags = set(build_managed_tags(TagContext(hanzi="电脑", pinyin="diàn nǎo")))
        self.assertEqual(
            tags,
            {
                f"{HANZI_TAG_PREFIX}电",
                f"{HANZI_TAG_PREFIX}脑",
                f"{PINYIN_TAG_PREFIX}diàn",
                f"{PINYIN_TAG_PREFIX}nǎo",
            },
        )

    def test_uses_supplied_polyphonic_pronunciation(self) -> None:
        tags = set(build_managed_tags(TagContext(hanzi="银行", pinyin="yín háng")))
        self.assertIn(f"{PINYIN_TAG_PREFIX}háng", tags)
        self.assertNotIn(f"{PINYIN_TAG_PREFIX}xíng", tags)

    def test_includes_traditional_characters_without_duplicates(self) -> None:
        tags = set(
            build_managed_tags(
                TagContext(
                    hanzi="电脑",
                    traditional="電腦",
                    pinyin="diàn nǎo",
                )
            )
        )
        for character in "电脑電腦":
            self.assertIn(f"{HANZI_TAG_PREFIX}{character}", tags)

    def test_normalizes_numeric_tones(self) -> None:
        tags = set(build_managed_tags(TagContext(hanzi="电脑", pinyin="dian4 nao3")))
        self.assertIn(f"{PINYIN_TAG_PREFIX}diàn", tags)
        self.assertIn(f"{PINYIN_TAG_PREFIX}nǎo", tags)

    def test_normalizes_pinyin_font_variants_and_erhua(self) -> None:
        self.assertEqual(pinyin_syllables("diàn yǐnɡ"), ("diàn", "yǐng"))
        self.assertEqual(pinyin_syllables("Yàzhõu yánjiū"), ("yàzhōu", "yánjiū"))
        self.assertEqual(pinyin_syllables("shì(r)"), ("shì", "ér"))
        self.assertEqual(pinyin_tokens("huà huàr"), ("huà", "huàr"))

    def test_pinyin_tokens_keep_repeated_syllables_for_alignment(self) -> None:
        self.assertEqual(pinyin_tokens("hǎo hǎo"), ("hǎo", "hǎo"))
        self.assertEqual(pinyin_syllables("hǎo hǎo"), ("hǎo",))

    def test_builds_one_complete_yoyo_path(self) -> None:
        tags = build_managed_tags(
            TagContext(
                hanzi="水",
                pinyin="shuǐ",
                course_paths=(
                    YoyoCoursePath(
                        course="Beginner Conversational",
                        level=2,
                        unit=14,
                        lesson=1,
                    ),
                ),
            )
        )
        self.assertIn(
            f"{YOYO_SOURCE_TAG_PREFIX}::cours::beginner_conversational"
            "::niveau::02::unite::014::lecon::01",
            tags,
        )

    def test_accumulates_complete_paths_for_reused_card(self) -> None:
        paths = (
            YoyoCoursePath("Beginner Conversational", 2, 14, 1),
            YoyoCoursePath("Beginner Conversational", 2, 14, 2),
        )
        tags = [
            tag
            for tag in build_managed_tags(TagContext(hanzi="水", course_paths=paths))
            if tag.startswith(YOYO_SOURCE_TAG_PREFIX)
        ]
        self.assertEqual(len(tags), 2)

    def test_component_is_never_inferred(self) -> None:
        automatic = build_managed_tags(TagContext(hanzi="休", pinyin="xiū"))
        explicit = build_managed_tags(
            TagContext(hanzi="休", pinyin="xiū", explicit_components=("木",))
        )
        self.assertNotIn(f"{COMPONENT_TAG_PREFIX}木", automatic)
        self.assertIn(f"{COMPONENT_TAG_PREFIX}木", explicit)

    def test_converts_hierarchy_between_anki_and_obsidian(self) -> None:
        anki_tag = f"{HANZI_TAG_PREFIX}电"
        obsidian_tag = "chinois/caracteres/hanzi/电"
        self.assertEqual(anki_to_obsidian_tag(anki_tag), obsidian_tag)
        self.assertEqual(obsidian_to_anki_tag(obsidian_tag), anki_tag)

    def test_cleanup_preserves_manual_and_mdanki_tags(self) -> None:
        technical = f"{TECHNICAL_TAG_PREFIXES[0]}vault::uuid"
        desired = build_managed_tags(TagContext(hanzi="电", pinyin="diàn"))
        update = plan_tag_update(
            [
                "chinois",
                "电",
                "diàn",
                "course::beginner_conversational",
                "manual-tag",
                technical,
            ],
            desired,
            owned_prefixes=(HANZI_TAG_PREFIX, PINYIN_TAG_PREFIX),
            cleanup_legacy=True,
            legacy_flat_values=("diàn",),
        )
        self.assertEqual(
            set(update.remove),
            {"电", "diàn", "course::beginner_conversational"},
        )
        self.assertIn("chinois", update.final)
        self.assertIn("manual-tag", update.final)
        self.assertIn(technical, update.final)

    def test_update_plan_is_idempotent(self) -> None:
        desired = build_managed_tags(TagContext(hanzi="电", pinyin="diàn"))
        update = plan_tag_update(
            list(desired),
            desired,
            owned_prefixes=(HANZI_TAG_PREFIX, PINYIN_TAG_PREFIX),
            cleanup_legacy=True,
            legacy_flat_values=("diàn",),
        )
        self.assertEqual(update.add, ())
        self.assertEqual(update.remove, ())


if __name__ == "__main__":
    unittest.main()
