from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


SRC_DIR = Path(__file__).parents[2] / "chineasy_to_anki" / "src"
EXPORTER_PATH = SRC_DIR / "anki_exporter.py"
sys.path.insert(0, str(SRC_DIR))
SPEC = importlib.util.spec_from_file_location("huaxia_anki_exporter", EXPORTER_PATH)
assert SPEC and SPEC.loader
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class ImporterBlockTests(unittest.TestCase):
    def test_preserves_manual_and_auto_blocks(self) -> None:
        existing = (
            "<p>manuel</p>\n"
            "<!-- HUAXIA_MNEMO_AUTO_START -->"
            '<img src="auto.png">'
            "<!-- HUAXIA_MNEMO_AUTO_END -->"
        )
        result = exporter.merge_imported_mnemo(
            existing,
            '<img src="import.png">',
        )
        self.assertIn("<p>manuel</p>", result)
        self.assertIn("auto.png", result)
        self.assertIn("import.png", result)

    def test_replaces_only_previous_import_block(self) -> None:
        existing = (
            "<p>manuel</p>\n"
            f"{exporter.MNEMO_IMPORT_START}"
            '<img src="old.png">'
            f"{exporter.MNEMO_IMPORT_END}"
        )
        result = exporter.merge_imported_mnemo(
            existing,
            '<img src="new.png">',
        )
        self.assertIn("<p>manuel</p>", result)
        self.assertNotIn("old.png", result)
        self.assertIn("new.png", result)

    def test_does_not_duplicate_existing_media(self) -> None:
        existing = '<img src="same.png">'
        result = exporter.merge_imported_mnemo(
            existing,
            '<img src="same.png">',
        )
        self.assertEqual(result, existing)

    def test_empty_import_removes_only_owned_block(self) -> None:
        existing = (
            "<p>manuel</p>\n"
            f"{exporter.MNEMO_IMPORT_START}"
            '<img src="old.png">'
            f"{exporter.MNEMO_IMPORT_END}"
        )
        result = exporter.merge_imported_mnemo(existing, "")
        self.assertEqual(result, "<p>manuel</p>")

    def test_visual_answer_relies_on_native_anki_audio(self) -> None:
        self.assertEqual(exporter.CARD1_BACK.count("{{Audio}}"), 1)
        self.assertNotIn("setTimeout", exporter.CARD1_BACK)
        self.assertNotIn(".click()", exporter.CARD1_BACK)

    def test_removes_only_forced_audio_replay_script(self) -> None:
        template = """
<div>{{Audio}}</div>
<script>
console.log("script conservé");
</script>
<script>
(function() {
    function triggerAudio() {
        document.querySelectorAll('.replay-button, .soundLink').forEach(
            function(button) { button.click(); }
        );
    }
    setTimeout(triggerAudio, 50);
    setTimeout(triggerAudio, 300);
})();
</script>
"""
        cleaned = exporter.strip_forced_audio_replay_scripts(template)
        self.assertIn('console.log("script conservé")', cleaned)
        self.assertNotIn("triggerAudio", cleaned)
        self.assertNotIn("setTimeout", cleaned)
        self.assertEqual(
            exporter.strip_forced_audio_replay_scripts(cleaned),
            cleaned,
        )


if __name__ == "__main__":
    unittest.main()
