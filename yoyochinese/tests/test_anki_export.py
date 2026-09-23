from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

import anki_export
import download_yoyo as yoyo


@unittest.skipUnless(importlib.util.find_spec("genanki"), "genanki non installé")
class AnkiPackageTests(unittest.TestCase):
    def test_writes_one_course_package_with_both_audio_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            normal = root / "BCC-014-01-001-N.mp3"
            slow = root / "BCC-014-01-001-S.mp3"
            normal.write_bytes(b"ID3-normal-test")
            slow.write_bytes(b"ID3-slow-test")
            card = yoyo.FlashcardPlan(
                flashcard_id="card-1",
                code="BCC-014-01-001",
                index_number=1,
                simplified="杯子",
                traditional="杯子",
                pinyin="bēi zi",
                english="cup",
                tags=list(
                    yoyo.build_managed_tags(
                        yoyo.TagContext(
                            hanzi="杯子",
                            traditional="杯子",
                            pinyin="bēi zi",
                            course_paths=(
                                yoyo.YoyoCoursePath(
                                    "Beginner Conversational",
                                    2,
                                    14,
                                    1,
                                ),
                            ),
                        )
                    )
                ),
                assets=[
                    yoyo.Asset("flashcard_audio_normal", "https://example.invalid/normal", str(normal)),
                    yoyo.Asset("flashcard_audio_slow", "https://example.invalid/slow", str(slow)),
                ],
            )
            plan = yoyo.LessonPlan(
                lesson_url="https://yoyochinese.com/lesson/example",
                lesson_id="lesson-1",
                code="BCC-014-01",
                title="Something to Drink - Part 1",
                course="beginner-conversational-chinese",
                course_title="Beginner Conversational",
                course_code="BCC",
                level_number=2,
                level_title="Level 2",
                unit="Unit 14",
                unit_title="Something to Drink",
                lesson_number=1,
                directory=str(root / "lesson"),
                assets=[],
                flashcards_available=True,
                flashcards=[card],
            )

            results = anki_export.export_course_packages([plan], root)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["card_count"], 1)
            self.assertEqual(results[0]["media_count"], 2)
            package = Path(results[0]["path"])
            self.assertTrue(package.is_file())
            with ZipFile(package) as archive:
                self.assertIn("collection.anki2", archive.namelist())
                self.assertIn("media", archive.namelist())


if __name__ == "__main__":
    unittest.main()
