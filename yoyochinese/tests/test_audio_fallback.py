from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audio_fallback
import download_yoyo as yoyo


class AudioFallbackTests(unittest.TestCase):
    def test_uses_providers_in_required_order(self) -> None:
        calls = []

        def failed(name):
            def provider(_text, _path):
                calls.append(name)
                return False
            return provider

        def success(_text, path):
            calls.append("edge_tts")
            path.write_bytes(b"ID3" + b"x" * 2_000)
            return True

        providers = (
            ("youdao", failed("youdao")),
            ("baidu", failed("baidu")),
            ("edge_tts", success),
            ("gtts", failed("gtts")),
        )
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            audio_fallback,
            "PROVIDERS",
            providers,
        ):
            result = audio_fallback.generate_fallback_audio(
                "你好",
                Path(temporary) / "audio.mp3",
            )
        self.assertEqual(result, "edge_tts")
        self.assertEqual(calls, ["youdao", "baidu", "edge_tts"])

    @patch.object(yoyo, "download_asset", side_effect=yoyo.YoyoError("HTTP Error 403: Forbidden"))
    def test_failed_yoyo_audio_is_generated_and_not_partial(self, _download) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "audio.mp3"
            card = yoyo.FlashcardPlan(
                flashcard_id="card-1",
                code="TEST-001",
                index_number=1,
                simplified="你好",
                traditional="你好",
                pinyin="nǐ hǎo",
                english="hello",
                tags=["chinois::source::yoyochinese"],
                assets=[
                    yoyo.Asset(
                        "flashcard_audio_normal",
                        "https://cdn.yoyochinese.com/audio/practice/missing.mp3",
                        str(path),
                    )
                ],
            )
            plan = yoyo.LessonPlan(
                lesson_url="https://yoyochinese.com/lesson/example",
                lesson_id="lesson-1",
                code="TEST-01",
                title="Test",
                course="test",
                course_title="Test",
                course_code="TEST",
                level_number=1,
                level_title="Level 1",
                unit="Unit 1",
                unit_title="Unit 1",
                lesson_number=1,
                directory=temporary,
                assets=[],
                flashcards=[card],
            )

            def fallback(_text, output):
                Path(output).write_bytes(b"ID3" + b"x" * 2_000)
                return "youdao"

            with patch.object(yoyo, "generate_fallback_audio", side_effect=fallback):
                result = yoyo.download_lesson(plan, object(), overwrite=False)
        self.assertEqual(result["status"], "generated")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["flashcards"][0]["assets"][0]["provider"], "youdao")


if __name__ == "__main__":
    unittest.main()
