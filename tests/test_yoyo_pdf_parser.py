from __future__ import annotations

import unittest

from anki_characters.chineasy_to_anki import app as app_module
from anki_characters.chineasy_to_anki.src.yoyo_parser import (
    filter_simplified_cjk_list,
    parse_rowwise_section,
)


class YoyoPdfParserTests(unittest.TestCase):
    def test_parses_english_pinyin_hanzi_rows_without_column_shift(self) -> None:
        rows = parse_rowwise_section([
            "English",
            "Pinyin",
            "Chinese Characters",
            "Cardinal Numbers",
            "zero",
            "línɡ",
            "零",
            "one",
            "yī",
            "一",
            "two",
            "èr",
            "二",
        ])
        self.assertEqual(
            rows,
            [
                ("zero", "línɡ", "零"),
                ("one", "yī", "一"),
                ("two", "èr", "二"),
            ],
        )

    def test_parses_pinyin_first_and_wrapped_english(self) -> None:
        rows = parse_rowwise_section([
            "Pinyin",
            "English",
            "Chinese Characters",
            "chōu",
            "to slap; to take out (of",
            "something)",
            "抽",
        ])
        self.assertEqual(
            rows,
            [("to slap; to take out (of something)", "chōu", "抽")],
        )

    def test_distinct_hanzi_are_not_mistaken_for_traditional_pairs(self) -> None:
        self.assertEqual(
            filter_simplified_cjk_list(
                ["零", "一", "二", "三"],
                expected_count=4,
            ),
            ["零", "一", "二", "三"],
        )
        self.assertEqual(
            filter_simplified_cjk_list(
                ["电影", "電影", "电话", "電話"],
                expected_count=2,
            ),
            ["电影", "电话"],
        )

    def test_app_rejects_shifted_pdf_columns_before_anki_export(self) -> None:
        valid = {
            "hanzi": "二",
            "pinyin": "èr",
            "english": "two",
        }
        shifted = {
            "hanzi": "二",
            "pinyin": "yī",
            "english": "Pinyin",
        }
        self.assertEqual(app_module.validate_yoyo_items([valid]), [])
        self.assertTrue(app_module.validate_yoyo_items([shifted]))

    def test_app_records_one_canonical_audio_source(self) -> None:
        item = {
            "tags": [
                "vocabulary",
                "chinois::audio::source::youdao",
            ]
        }
        app_module.attach_audio_source_tag(item, "edge_tts")
        self.assertEqual(
            item["tags"],
            ["vocabulary", "chinois::audio::source::edge_tts"],
        )


if __name__ == "__main__":
    unittest.main()
