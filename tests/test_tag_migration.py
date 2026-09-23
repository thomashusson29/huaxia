from __future__ import annotations

import unittest

from anki_characters.chineasy_to_anki import update_anki_tags as migration


def field(value: str) -> dict[str, str]:
    return {"value": value}


def yoyo_note(*, tags: list[str] | None = None) -> dict:
    return {
        "noteId": 1784649646892,
        "modelName": "Yoyo Chinese Model v2-41f05",
        "tags": tags
        or [
            "yoyo_chinese",
            "course::beginner_conversational",
            "level::02",
            "unit::014",
            "lesson::01",
            "电",
            "脑",
            "diàn",
            "nǎo",
            "manual-tag",
            "_mdanki::vault::uuid",
        ],
        "fields": {
            "Hanzi": field("电脑"),
            "Traditional": field("電腦"),
            "Pinyin": field("diàn nǎo"),
            "YoyoId": field("card-1"),
        },
    }


class TagMigrationTests(unittest.TestCase):
    def test_addition_preview_never_removes_legacy_tags(self) -> None:
        report = migration.build_report([yoyo_note()], cleanup_legacy=False)
        self.assertEqual(report.notes_scanned, 1)
        self.assertEqual(report.tags_removed, 0)
        record = report.records[0]
        self.assertIn("chinois::caracteres::hanzi::电", record.add)
        self.assertIn("chinois::caracteres::pinyin::diàn", record.add)
        self.assertIn(
            "chinois::source::yoyochinese::cours::beginner_conversational"
            "::niveau::02::unite::014::lecon::01",
            record.add,
        )

    def test_report_keeps_recent_query_scope(self) -> None:
        report = migration.build_report(
            [yoyo_note()],
            cleanup_legacy=False,
            query=migration.RECENT_QUERY,
        )
        self.assertEqual(report.query, 'deck:"chinois" added:1')

    def test_added_days_cli_builds_safe_scoped_filter(self) -> None:
        args = migration.parse_args(["--added-days", "1"])
        self.assertEqual(args.added_days, 1)

    def test_deck_source_is_used_when_legacy_note_has_no_source_tag(self) -> None:
        note = yoyo_note(tags=["电", "脑", "diàn", "nǎo"])
        report = migration.build_report(
            [note],
            cleanup_legacy=False,
            source_by_note_id={note["noteId"]: "yoyochinese"},
        )
        self.assertIn(
            "chinois::source::yoyochinese",
            report.records[0].add,
        )

    def test_incoherent_pinyin_uses_contextual_fallback(self) -> None:
        if migration.pinyin_is_plausible("吴", "má"):
            self.skipTest("pypinyin n’est pas disponible dans cet environnement.")
        note = {
            "noteId": 5,
            "modelName": "Yoyo Chinese Model v2-41f05",
            "tags": [],
            "fields": {
                "Hanzi": field("吴"),
                "Traditional": field(""),
                "Pinyin": field("má"),
                "YoyoId": field("legacy"),
            },
        }
        report = migration.build_report([note], cleanup_legacy=False)
        record = report.records[0]
        self.assertIn("chinois::caracteres::pinyin::wú", record.add)
        self.assertNotIn("chinois::caracteres::pinyin::má", record.add)
        self.assertTrue(
            any("Pinyin du champ incohérent" in warning for warning in record.warnings)
        )

    def test_concatenated_pinyin_is_split_into_syllable_tags(self) -> None:
        note = {
            "noteId": 6,
            "modelName": "Chinesische Vokabeln+",
            "tags": [],
            "fields": {
                "Mandarin": field("小姐"),
                "Pinyin": field("xiǎojiě"),
            },
        }
        report = migration.build_report([note], cleanup_legacy=False)
        record = report.records[0]
        self.assertIn("chinois::caracteres::pinyin::xiǎo", record.add)
        self.assertIn("chinois::caracteres::pinyin::jiě", record.add)
        self.assertNotIn("chinois::caracteres::pinyin::xiǎojiě", record.add)
        self.assertFalse(record.warnings)

    def test_script_g_variant_does_not_create_false_pinyin_warning(self) -> None:
        note = {
            "noteId": 7,
            "modelName": "Yoyo Chinese Model v2-41f05",
            "tags": [],
            "fields": {
                "Hanzi": field("电影"),
                "Pinyin": field("diàn yǐnɡ"),
                "YoyoId": field("legacy"),
            },
        }
        report = migration.build_report([note], cleanup_legacy=False)
        record = report.records[0]
        self.assertIn("chinois::caracteres::pinyin::yǐng", record.add)
        self.assertFalse(record.warnings)

    def test_erhua_suffix_is_aligned_with_visible_er_character(self) -> None:
        note = {
            "noteId": 8,
            "modelName": "Yoyo Chinese Model v2-41f05",
            "tags": [],
            "fields": {
                "Hanzi": field("画画儿"),
                "Pinyin": field("huà huàr"),
                "YoyoId": field("legacy"),
            },
        }
        report = migration.build_report([note], cleanup_legacy=False)
        record = report.records[0]
        self.assertIn("chinois::caracteres::pinyin::huà", record.add)
        self.assertIn("chinois::caracteres::pinyin::ér", record.add)
        self.assertFalse(record.warnings)

    def test_internal_erhua_suffix_is_aligned(self) -> None:
        note = {
            "noteId": 9,
            "modelName": "Yoyo Chinese Model v2-41f05",
            "tags": [],
            "fields": {
                "Hanzi": field("有点儿热"),
                "Pinyin": field("yǒu diǎnr rè"),
                "YoyoId": field("legacy"),
            },
        }
        report = migration.build_report([note], cleanup_legacy=False)
        record = report.records[0]
        self.assertIn("chinois::caracteres::pinyin::diǎn", record.add)
        self.assertIn("chinois::caracteres::pinyin::ér", record.add)
        self.assertFalse(record.warnings)

    def test_cleanup_replaces_known_legacy_and_preserves_manual_tags(self) -> None:
        note = yoyo_note()
        desired, warnings, legacy_values = migration._desired_tags(note)
        update = migration.plan_tag_update(
            note["tags"],
            desired,
            owned_prefixes=(
                migration.HANZI_TAG_PREFIX,
                migration.PINYIN_TAG_PREFIX,
                migration.SOURCE_TAG_PREFIX,
            ),
            cleanup_legacy=not warnings,
            legacy_flat_values=legacy_values,
        )
        self.assertIn("电", update.remove)
        self.assertIn("diàn", update.remove)
        self.assertIn("course::beginner_conversational", update.remove)
        self.assertIn("manual-tag", update.final)
        self.assertIn("_mdanki::vault::uuid", update.final)

    def test_ambiguous_yoyo_relations_are_reported_not_crossed(self) -> None:
        note = yoyo_note(
            tags=[
                "yoyo_chinese",
                "course::beginner_conversational",
                "level::02",
                "unit::014",
                "lesson::01",
                "lesson::02",
            ]
        )
        note["fields"]["Traditional"] = field("")
        report = migration.build_report([note], cleanup_legacy=True)
        record = report.records[0]
        self.assertTrue(record.warnings)
        self.assertIn("lesson::01", record.remove)
        self.assertIn("lesson::02", record.remove)
        self.assertIn(
            "chinois::a_verifier::yoyochinese::lecon::01",
            record.add,
        )
        self.assertIn(
            "chinois::a_verifier::yoyochinese::lecon::02",
            record.add,
        )
        source_additions = [
            tag for tag in record.add if tag.startswith(migration.YOYO_SOURCE_TAG_PREFIX)
        ]
        self.assertEqual(source_additions, ["chinois::source::yoyochinese"])

    def test_leftover_flat_tags_are_classified_without_guessing_components(self) -> None:
        note = yoyo_note(
            tags=[
                "chinois",
                "yoyochinese",
                "course::advanced_conversational_chinese",
                "unit::020",
                "lesson::01",
                "vocabulary",
                "电",
                "diàn",
                "⺌",
                "manual-tag",
            ]
        )
        report = migration.build_report([note], cleanup_legacy=True)
        record = report.records[0]
        self.assertIn("chinois::type::vocabulaire", record.add)
        self.assertIn(
            "chinois::a_verifier::yoyochinese::cours::advanced_conversational_chinese",
            record.add,
        )
        self.assertIn("⺌", record.remove)
        self.assertIn("电", record.remove)
        self.assertNotIn("manual-tag", record.remove)

    def test_verified_source_alias_and_wrong_cat_tone_are_removed(self) -> None:
        note = yoyo_note(
            tags=[
                "chinois",
                "lechinoisfacile",
                "máo",
                "chinois::caracteres::pinyin::māo",
                "manual-tag",
            ]
        )
        report = migration.build_report([note], cleanup_legacy=True)
        record = report.records[0]
        self.assertIn("lechinoisfacile", record.remove)
        self.assertIn("máo", record.remove)
        self.assertNotIn("manual-tag", record.remove)
        self.assertNotIn("chinois", record.remove)

    def test_review_tags_are_idempotent_and_keep_warning_visible(self) -> None:
        note = yoyo_note(
            tags=[
                "chinois::source::yoyochinese",
                "chinois::a_verifier::yoyochinese::cours::ancien_cours",
                "chinois::caracteres::hanzi::电",
                "chinois::caracteres::hanzi::脑",
                "chinois::caracteres::pinyin::diàn",
                "chinois::caracteres::pinyin::nǎo",
            ]
        )
        note["fields"]["Traditional"] = field("")
        report = migration.build_report([note], cleanup_legacy=True)
        self.assertEqual(report.notes_changed, 0)
        self.assertEqual(report.warnings, 1)

    def test_integrated_chinese_lesson_is_mapped(self) -> None:
        note = {
            "noteId": 1,
            "modelName": "Chinesische Vokabeln+",
            "tags": ["IC1.1_L4_2"],
            "fields": {
                "Mandarin": field("你好"),
                "Pinyin": field("nǐ hǎo"),
            },
        }
        report = migration.build_report([note], cleanup_legacy=False)
        self.assertIn(
            "chinois::source::integrated_chinese::niveau::01::partie::01"
            "::lecon::04::section::02",
            report.records[0].add,
        )

    def test_existing_detailed_source_survives_second_cleanup(self) -> None:
        detailed = (
            "chinois::source::integrated_chinese::niveau::01::partie::01"
            "::lecon::04::section::02"
        )
        note = {
            "noteId": 10,
            "modelName": "Chinesische Vokabeln+",
            "tags": [detailed],
            "fields": {
                "Mandarin": field("你好"),
                "Pinyin": field("nǐ hǎo"),
            },
        }
        first = migration.build_report([note], cleanup_legacy=True)
        additions = list(first.records[0].add)
        note["tags"].extend(additions)
        second = migration.build_report([note], cleanup_legacy=True)
        self.assertEqual(second.notes_changed, 0)

    def test_valid_mnemonic_library_note_receives_derived_tag(self) -> None:
        note = {
            "noteId": 2,
            "modelName": "Huaxia Mnémotechnique v1",
            "tags": [],
            "fields": {
                "TypeLien": field("caractere"),
                "Cle": field("电"),
            },
        }
        report = migration.build_report([note], cleanup_legacy=False)
        self.assertEqual(
            report.records[0].add,
            ("chinois::mnemonique::type::caractere::cle::电",),
        )

    def test_visible_chinese_is_scanned_for_cloze_notes(self) -> None:
        note = {
            "noteId": 4,
            "modelName": "Enhanced Cloze 2.1 v2",
            "tags": ["chinois", "lechinoisfacile", "lecon1"],
            "fields": {
                "Content": field(
                    "Exemple : {{c1::他 (tā)}} puis {{c2::麻 (má)}}."
                ),
            },
        }
        report = migration.build_report([note], cleanup_legacy=False)
        additions = set(report.records[0].add)
        self.assertIn("chinois::caracteres::hanzi::他", additions)
        self.assertIn("chinois::caracteres::hanzi::麻", additions)
        self.assertIn(
            "chinois::source::le_chinois_facile::lecon::01",
            additions,
        )

    def test_invalid_mnemonic_library_note_is_only_reported(self) -> None:
        note = {
            "noteId": 3,
            "modelName": "Huaxia Mnémotechnique v1",
            "tags": ["manual-tag"],
            "fields": {
                "TypeLien": field(""),
                "Cle": field("熊猫"),
            },
        }
        report = migration.build_report([note], cleanup_legacy=True)
        record = report.records[0]
        self.assertTrue(record.warnings)
        self.assertEqual(record.add, ())
        self.assertEqual(record.remove, ())


if __name__ == "__main__":
    unittest.main()
