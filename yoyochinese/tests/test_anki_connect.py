from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import anki_connect
import anki_export
import download_yoyo as yoyo


class FakeAnkiConnect:
    def __init__(self, *, existing: bool = False) -> None:
        self.url = "http://127.0.0.1:8766"
        self.existing = existing
        self.actions: list[tuple[str, dict]] = []

    def invoke(self, action: str, **params):
        self.actions.append((action, params))
        if action == "modelNames":
            return [anki_export.MODEL_NAME] if self.existing else []
        if action == "modelFieldNames":
            return list(anki_export.FIELD_NAMES)
        if action == "findNotes":
            if "YoyoId" in params.get("query", "") and self.existing:
                return [42]
            return []
        if action == "notesInfo":
            return [
                {
                    "noteId": 42,
                    "fields": {"YoyoId": {"value": "card-1"}},
                    "tags": [
                        "yoyo_chinese",
                        "level::02",
                        "unit::014",
                        "lesson::01",
                        "manual-tag",
                        "_mdanki::vault::uuid",
                    ],
                }
            ]
        if action == "findCards":
            return [84, 85]
        if action == "addNote":
            return 43
        return None


def make_plan(root: Path, *, with_audio: bool = True) -> yoyo.LessonPlan:
    assets = []
    if with_audio:
        normal = root / "BCC-014-01-001-N.mp3"
        slow = root / "BCC-014-01-001-S.mp3"
        normal.write_bytes(b"ID3-normal")
        slow.write_bytes(b"ID3-slow")
        assets = [
            yoyo.Asset("flashcard_audio_normal", "https://example.invalid/n", str(normal)),
            yoyo.Asset("flashcard_audio_slow", "https://example.invalid/s", str(slow)),
        ]
    tags = list(
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
    )
    card = yoyo.FlashcardPlan(
        flashcard_id="card-1",
        code="BCC-014-01-001",
        index_number=1,
        simplified="杯子",
        traditional="杯子",
        pinyin="bēi zi",
        english="cup",
        tags=tags,
        assets=assets,
    )
    return yoyo.LessonPlan(
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
        unit_title="Drinking",
        lesson_number=1,
        directory=str(root / "lesson"),
        assets=[],
        flashcards_available=True,
        flashcards=[card],
    )


class AnkiConnectTests(unittest.TestCase):
    def test_adds_card_and_media_to_bulk_export_deck(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fake = FakeAnkiConnect()
            result = anki_connect.sync_plans(
                [make_plan(Path(temporary))],
                client=fake,
            )
        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["deck_name"], "chinois::ychinese::bulk export")
        self.assertEqual(result["added_count"], 1)
        self.assertEqual(result["media_count"], 2)
        add_note = next(params for action, params in fake.actions if action == "addNote")
        self.assertEqual(add_note["note"]["deckName"], result["deck_name"])
        self.assertEqual(add_note["note"]["fields"]["YoyoId"], "card-1")
        self.assertTrue(add_note["note"]["options"]["allowDuplicate"])

    def test_updates_existing_yoyo_id_and_moves_cards_to_bulk_deck(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fake = FakeAnkiConnect(existing=True)
            result = anki_connect.sync_plans(
                [make_plan(Path(temporary), with_audio=False)],
                client=fake,
            )
        self.assertEqual(result["added_count"], 0)
        self.assertEqual(result["updated_count"], 1)
        change_deck = next(params for action, params in fake.actions if action == "changeDeck")
        self.assertEqual(change_deck["cards"], [84, 85])
        self.assertEqual(change_deck["deck"], "chinois::ychinese::bulk export")
        removed = [
            params["tags"]
            for action, params in fake.actions
            if action == "removeTags"
        ]
        self.assertIn("yoyo_chinese", " ".join(removed).split())
        added = [
            params["tags"]
            for action, params in fake.actions
            if action == "addTags"
        ]
        self.assertTrue(
            any(
                tag.startswith("chinois::source::yoyochinese::")
                for tag in " ".join(added).split()
            )
        )

    def test_imports_packages_then_consolidates_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "course.apkg"
            package.write_bytes(b"test package")
            fake = FakeAnkiConnect(existing=True)
            result = anki_connect.sync_packages([package], client=fake)
        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["package_count"], 1)
        self.assertEqual(result["note_count"], 1)
        self.assertEqual(result["card_count"], 2)
        imported = next(params for action, params in fake.actions if action == "importPackage")
        self.assertEqual(Path(imported["path"]).name, "course.apkg")
        moved = next(params for action, params in fake.actions if action == "changeDeck")
        self.assertEqual(moved["deck"], "chinois::ychinese::bulk export")


if __name__ == "__main__":
    unittest.main()
