from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


CORE_PATH = Path(__file__).parents[1] / "core.py"
SPEC = importlib.util.spec_from_file_location("huaxia_mnemo_core", CORE_PATH)
assert SPEC and SPEC.loader
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)


class MatchingTests(unittest.TestCase):
    def entry(self, link_type: str, key: str) -> core.MnemonicEntry:
        return core.MnemonicEntry(
            mnemonic_id=f"{link_type}-{key}",
            link_type=link_type,
            key=key,
            content=f'<img src="{key}.png">',
            description="Description",
        )

    def test_character_matches_visible_hanzi(self) -> None:
        self.assertTrue(
            core.note_matches(self.entry("caractere", "机"), "手机", "", [])
        )
        self.assertFalse(
            core.note_matches(self.entry("caractere", "木"), "手机", "", [])
        )

    def test_character_sequence_matches_visible_hanzi(self) -> None:
        self.assertTrue(
            core.note_matches(
                self.entry("caractere", "熊猫"),
                "我喜欢熊猫。",
                "",
                [],
            )
        )

    def test_chineasy_source_does_not_match_itself(self) -> None:
        entry = core.MnemonicEntry(
            mnemonic_id="chineasy-123",
            link_type="caractere",
            key="木",
            content='<img src="tree.png">',
            source="chineasy",
        )
        self.assertFalse(core.note_matches(entry, "木", "", [], note_id=123))
        self.assertTrue(core.note_matches(entry, "木", "", [], note_id=456))

    def test_chineasy_source_matches_other_mnemonic_for_same_key(self) -> None:
        self.assertTrue(
            core.note_matches(
                self.entry("caractere", "木"),
                "木",
                "",
                [],
                note_id=123,
            )
        )

    def test_word_matches_inside_sentence(self) -> None:
        self.assertTrue(
            core.note_matches(
                self.entry("mot", "手机"),
                "这是我的手机。",
                "",
                [],
            )
        )

    def test_component_requires_namespaced_tag(self) -> None:
        entry = self.entry("composant", "木")
        self.assertEqual(
            core.COMPONENT_TAG_PREFIX,
            "chinois::caracteres::composant::",
        )
        self.assertFalse(core.note_matches(entry, "手机", "", ["木"]))
        self.assertTrue(
            core.note_matches(
                entry,
                "手机",
                "",
                [f"{core.COMPONENT_TAG_PREFIX}木"],
            )
        )

    def test_component_accepts_multiple_characters(self) -> None:
        entry = self.entry("composant", "木目")
        core.validate_entry(entry)
        self.assertTrue(
            core.note_matches(
                entry,
                "相",
                "",
                [f"{core.COMPONENT_TAG_PREFIX}木目"],
            )
        )

    def test_library_tag_is_derived_from_type_and_key(self) -> None:
        self.assertEqual(
            core.library_tag("caractere", "电"),
            "chinois::mnemonique::type::caractere::cle::电",
        )


class EnhancedClozeAudioTests(unittest.TestCase):
    CONTENT = (
        "[sound:global.mp3]"
        "{{c1::un}} [sound:one.mp3]"
        "{{c2::deux}} [sound:two.mp3] [sound:two.mp3]"
    )

    def test_selects_global_and_current_cloze_audio(self) -> None:
        all_audio, selected = core.enhanced_cloze_audio_counts(self.CONTENT, 1)
        self.assertEqual(
            all_audio,
            {
                "global.mp3": 1,
                "one.mp3": 1,
                "two.mp3": 2,
            },
        )
        self.assertEqual(selected, {"global.mp3": 1, "one.mp3": 1})

    def test_preserves_intentional_repeated_audio_for_current_cloze(self) -> None:
        _, selected = core.enhanced_cloze_audio_counts(self.CONTENT, 2)
        self.assertEqual(selected, {"global.mp3": 1, "two.mp3": 2})


class MediaSelectionTests(unittest.TestCase):
    def test_extracts_relative_media_filename(self) -> None:
        self.assertEqual(
            core.media_filename_from_src("mnemo_Tree_IMG_9231.png"),
            "mnemo_Tree_IMG_9231.png",
        )

    def test_extracts_filename_from_editor_media_url(self) -> None:
        self.assertEqual(
            core.media_filename_from_src(
                "http://127.0.0.1:8765/mnemo%20Tree.png?cache=1"
            ),
            "mnemo Tree.png",
        )

    def test_rejects_transient_image_sources(self) -> None:
        self.assertEqual(
            core.media_filename_from_src("data:image/png;base64,AAAA"),
            "",
        )
        self.assertEqual(core.media_filename_from_src("blob:temporary"), "")


class RenderingTests(unittest.TestCase):
    def entry(
        self,
        mnemonic_id: str,
        source: str,
        description: str = "Description",
    ) -> core.MnemonicEntry:
        return core.MnemonicEntry(
            mnemonic_id=mnemonic_id,
            link_type="caractere",
            key="木",
            content=f'<img src="{source}">',
            description=description,
        )

    def test_preserves_manual_content_and_replaces_auto_block(self) -> None:
        existing = (
            '<p>manuel</p>'
            f"{core.AUTO_START}<div>ancien</div>{core.AUTO_END}"
        )
        result = core.render_mnemo_auto(
            existing,
            [self.entry("new", "tree.png")],
        )
        self.assertIn("<p>manuel</p>", result.html)
        self.assertNotIn("ancien", result.html)
        self.assertIn("tree.png", result.html)
        self.assertEqual(result.included_ids, ("new",))

    def test_deduplicates_media_already_present_manually(self) -> None:
        result = core.render_mnemo_auto(
            '<img src="tree.png">',
            [self.entry("tree", "tree.png")],
        )
        self.assertEqual(result.html, '<img src="tree.png">')
        self.assertEqual(result.skipped_ids, ("tree",))

    def test_supports_multiple_mnemonics_for_same_key(self) -> None:
        result = core.render_mnemo_auto(
            "",
            [
                self.entry("one", "tree-one.png"),
                self.entry("two", "tree-two.png"),
            ],
        )
        self.assertEqual(result.included_ids, ("one", "two"))
        self.assertIn("tree-one.png", result.html)
        self.assertIn("tree-two.png", result.html)

    def test_removing_source_removes_only_auto_block(self) -> None:
        existing = (
            "<p>manuel</p>\n"
            f"{core.AUTO_START}<div>automatique</div>{core.AUTO_END}"
        )
        result = core.render_mnemo_auto(existing, [])
        self.assertEqual(result.html, "<p>manuel</p>")


if __name__ == "__main__":
    unittest.main()
