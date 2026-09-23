from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import download_yoyo as yoyo
import anki_export


def page_html(page_id: str, page_data: dict) -> str:
    payload = {"initialPageId": page_id, "initialPageData": page_data}
    return (
        "<html><body><script>window.yoyoData = "
        + json.dumps(payload)
        + "</script></body></html>"
    )


class YoyoDownloaderTests(unittest.TestCase):
    def test_parse_yoyo_data(self) -> None:
        parsed = yoyo.parse_yoyo_data(
            page_html("lesson", {"lessonTitle": "What Is Pinyin?"})
        )
        self.assertEqual(parsed["initialPageId"], "lesson")
        self.assertEqual(
            parsed["initialPageData"]["lessonTitle"],
            "What Is Pinyin?",
        )

    def test_lesson_plan_contains_exposed_mp4_and_pdf(self) -> None:
        data = {
            "initialPageId": "lesson",
            "initialPageData": {
                "lessonId": "lesson-2",
                "courseSlug": "beginner-conversational-chinese",
                "isLocked": False,
                "canWatchVideo": True,
                "mp4Src": "https://video.yoyochinese.com/token/BCC-001-02.mp4",
                "lesson": {
                    "code": "BCC-001-02",
                    "title": "What Is Pinyin?",
                    "isShowLecture": True,
                    "lectureFile": "Beg-Unit-001-Lesson-02-LN.pdf",
                },
                "practiceSectionProps": {
                    "isShowLecture": True,
                    "lectureFile": "Beg-Unit-001-Lesson-02-LN.pdf",
                },
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            plan = yoyo.build_lesson_plan(
                "https://yoyochinese.com/lesson/example/notes",
                data,
                Path(temporary),
            )
        self.assertEqual([asset.kind for asset in plan.assets], ["video", "pdf"])
        self.assertEqual(
            plan.assets[1].url,
            "https://cdn.yoyochinese.com/attachment/PDF/LectureNotes/"
            "Beg-Unit-001-Lesson-02-LN.pdf",
        )

    def test_hierarchy_is_course_level_unit_lesson(self) -> None:
        ref = yoyo.LessonRef(
            lesson_url="https://yoyochinese.com/lesson/example",
            course_slug="beginner-conversational-chinese",
            course_title="Beginner Conversational",
            course_code="BCC",
            level_number=1,
            level_title="Level 1",
            unit_slug="beginner-conversational-unit-1-Getting-Started",
            unit_prefix="Unit 1",
            unit_title="Getting Started",
            lesson_number=2,
            lesson_prefix="Lesson 2",
            lesson_title="What Is Pinyin?",
        )
        data = {
            "initialPageId": "lesson",
            "initialPageData": {
                "lessonId": "lesson-2",
                "mp4Src": "https://video.yoyochinese.com/token/BCC-001-02.mp4",
                "lesson": {"code": "BCC-001-02", "title": "What Is Pinyin?"},
            },
        }
        plan = yoyo.build_lesson_plan(ref, data, Path("downloads"))
        self.assertEqual(
            Path(plan.directory).parts[-4:],
            (
                "Beginner Conversational",
                "Level 01",
                "Unit 001 - Getting Started",
                "Lesson 02 - What Is Pinyin",
            ),
        )

    @patch.object(yoyo, "_keychain_read")
    def test_load_keychain_credentials(self, keychain_read) -> None:
        keychain_read.side_effect = ["student@example.com", "secret"]
        self.assertEqual(
            yoyo.load_keychain_credentials(),
            ("student@example.com", "secret"),
        )

    @patch.object(yoyo, "_keychain_read", return_value="secret")
    @patch.object(yoyo.subprocess, "run")
    def test_keychain_write_keeps_secret_out_of_process_arguments(
        self,
        run,
        _keychain_read,
    ) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["security", "-i"],
            returncode=0,
            stdout="",
            stderr="",
        )
        yoyo._keychain_write("fr.yoyochinese.test", "secret")
        command = run.call_args.args[0]
        self.assertEqual(command, ["security", "-i"])
        self.assertNotIn("secret", command)
        self.assertIn("736563726574", run.call_args.kwargs["input"])

    def test_login_uses_json_api(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"isEmailConfirmed": true}'

        class Opener:
            request = None

            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()

        client = yoyo.PageClient.__new__(yoyo.PageClient)
        client.timeout = 30
        client.authenticated = False
        client.opener = Opener()
        client.login("student@example.com", "secret")
        self.assertTrue(client.authenticated)
        self.assertEqual(client.opener.request.full_url, yoyo.LOGIN_URL)
        self.assertEqual(
            json.loads(client.opener.request.data),
            {"email": "student@example.com", "password": "secret"},
        )

    def test_locked_lesson_is_skipped(self) -> None:
        data = {
            "initialPageId": "lesson",
            "initialPageData": {
                "lessonId": "locked",
                "isLocked": True,
                "mp4Src": "https://video.yoyochinese.com/token/locked.mp4",
                "lesson": {"code": "BCC-999-01", "title": "Locked"},
            },
        }
        plan = yoyo.build_lesson_plan(
            "https://yoyochinese.com/lesson/locked",
            data,
            Path("downloads"),
        )
        self.assertEqual(plan.assets, [])
        self.assertIn("verrouillée", plan.skipped_reason)

    def test_unit_discovery_ignores_locked_unit(self) -> None:
        unlocked = {
            "initialPageData": {
                "isUnitLocked": False,
                "lessons": [
                    {"url": "/lesson/one"},
                    {"url": "/lesson/two"},
                ],
            }
        }
        locked = {
            "initialPageData": {
                "isUnitLocked": True,
                "lessons": [{"url": "/lesson/hidden"}],
            }
        }
        self.assertEqual(len(yoyo._lesson_urls_from_unit(unlocked)), 2)
        self.assertEqual(yoyo._lesson_urls_from_unit(locked), [])

    def test_rejects_untrusted_media_host(self) -> None:
        with self.assertRaises(yoyo.YoyoError):
            yoyo.validate_media_url("https://example.com/video.mp4")

    def test_flashcards_have_lesson_tags_and_both_original_sounds(self) -> None:
        ref = yoyo.LessonRef(
            lesson_url="https://yoyochinese.com/lesson/example",
            course_slug="beginner-conversational-chinese",
            course_title="Beginner Conversational",
            course_code="BCC",
            level_number=2,
            level_title="Level 2",
            unit_slug="unit-14",
            unit_prefix="Unit 14",
            unit_title="Something to Drink",
            lesson_number=1,
            lesson_prefix="Lesson 1",
            lesson_title="Something to Drink Part 1",
        )
        data = {
            "initialPageId": "lesson",
            "initialPageData": {
                "lessonId": "lesson-14-1",
                "lesson": {"code": "BCC-014-01", "title": ref.lesson_title},
                "practiceSectionProps": {"isShowFlashcards": True},
            },
        }
        plan = yoyo.build_lesson_plan(ref, data, Path("downloads"))
        cards = yoyo.build_flashcard_plans(
            plan,
            [
                {
                    "_id": "card-2",
                    "code": "BCC-014-01-002",
                    "indexNumber": 2,
                    "content": {
                        "simplified": "两杯水",
                        "traditional": "兩杯水",
                        "pinyin": "liǎng bēi shuǐ",
                        "english1": "two glasses of water",
                        "normal": "BCC-014-01-002-N",
                        "slow": "BCC-014-01-002-S",
                    },
                },
                {
                    "_id": "card-1",
                    "code": "BCC-014-01-001",
                    "indexNumber": 1,
                    "content": {
                        "simplified": "杯子",
                        "traditional": "杯子",
                        "pinyin": "bēi zi",
                        "english1": "cup",
                        "normal": "BCC-014-01-001-N",
                        "slow": "BCC-014-01-001-S",
                    },
                },
            ],
        )
        self.assertTrue(plan.flashcards_available)
        self.assertEqual([card.flashcard_id for card in cards], ["card-1", "card-2"])
        self.assertEqual(
            set(cards[0].tags),
            {
                "chinois::caracteres::hanzi::子",
                "chinois::caracteres::hanzi::杯",
                "chinois::caracteres::pinyin::bēi",
                "chinois::caracteres::pinyin::zi",
                "chinois::source::yoyochinese::cours::beginner_conversational"
                "::niveau::02::unite::014::lecon::01",
            },
        )
        self.assertEqual(
            [asset.kind for asset in cards[0].assets],
            ["flashcard_audio_normal", "flashcard_audio_slow"],
        )
        self.assertEqual(
            cards[0].assets[0].url,
            "https://cdn.yoyochinese.com/audio/practice/BCC-014-01-001-N.mp3",
        )

    def test_same_yoyo_card_is_merged_and_accumulates_lesson_tags(self) -> None:
        card_a = yoyo.FlashcardPlan(
            flashcard_id="shared-card",
            code="BCC-001-01-001",
            index_number=1,
            simplified="你好",
            traditional="你好",
            pinyin="nǐ hǎo",
            english="hello",
            tags=[
                "chinois::source::yoyochinese::cours::beginner_conversational"
                "::niveau::01::unite::001::lecon::01"
            ],
            assets=[],
        )
        card_b = yoyo.FlashcardPlan(
            flashcard_id="shared-card",
            code="BCC-002-02-001",
            index_number=1,
            simplified="你好",
            traditional="你好",
            pinyin="nǐ hǎo",
            english="hello",
            tags=[
                "chinois::source::yoyochinese::cours::beginner_conversational"
                "::niveau::01::unite::002::lecon::02"
            ],
            assets=[],
        )
        common = {
            "lesson_id": "lesson",
            "course": "beginner-conversational-chinese",
            "course_title": "Beginner Conversational",
            "course_code": "BCC",
            "level_number": 1,
            "level_title": "Level 1",
            "unit": "Unit 1",
            "unit_title": "Unit 1",
            "directory": "downloads",
            "assets": [],
        }
        first = yoyo.LessonPlan(
            lesson_url="https://yoyochinese.com/lesson/one",
            code="BCC-001-01",
            title="First",
            lesson_number=1,
            flashcards=[card_a],
            **common,
        )
        second = yoyo.LessonPlan(
            lesson_url="https://yoyochinese.com/lesson/two",
            code="BCC-002-02",
            title="Second",
            lesson_number=2,
            flashcards=[card_b],
            **common,
        )
        courses = anki_export.collect_course_cards([first, second])
        merged = courses["beginner-conversational-chinese"]["cards"]["shared-card"]
        self.assertEqual(
            merged["tags"],
            {
                "chinois::source::yoyochinese::cours::beginner_conversational"
                "::niveau::01::unite::001::lecon::01",
                "chinois::source::yoyochinese::cours::beginner_conversational"
                "::niveau::01::unite::002::lecon::02",
            },
        )
        self.assertEqual(len(merged["lessons"]), 2)

    def test_rejects_unsafe_practice_audio_name(self) -> None:
        with self.assertRaises(yoyo.YoyoError):
            yoyo.practice_audio_url("../secret.mp3")

    def test_accepts_safe_yoyo_media_subdirectories(self) -> None:
        self.assertEqual(
            yoyo.lecture_notes_url("lesson-id/notes.pdf"),
            "https://cdn.yoyochinese.com/attachment/PDF/LectureNotes/lesson-id/notes.pdf",
        )
        self.assertEqual(
            yoyo.practice_audio_url("card-id/BCC-027-01-013-S.mp3"),
            "https://cdn.yoyochinese.com/audio/practice/card-id/BCC-027-01-013-S.mp3",
        )
        with self.assertRaises(yoyo.YoyoError):
            yoyo.lecture_notes_url("lesson-id/../secret.pdf")

    def test_lesson_activity_suffix_is_removed_for_hierarchy_lookup(self) -> None:
        base = "/lesson/beginner-unit-14-lesson-1-title"
        for activity in ("notes", "flashcards", "ask", "audio", "video"):
            self.assertEqual(
                yoyo._lesson_base_path(f"https://yoyochinese.com{base}/{activity}"),
                base,
            )


if __name__ == "__main__":
    unittest.main()
