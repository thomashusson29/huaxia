from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fill_missing_anki_audio as fill_audio


class FakeAnkiConnect:
    def __init__(self) -> None:
        self.updated: list[dict] = []
        self.tags: list[dict] = []
        self.stored: list[dict] = []
        self.notes = [
            {
                "noteId": 1,
                "modelName": "Vocabulary",
                "fields": {
                    "Mandarin": {"value": "今年"},
                    "Audio": {"value": ""},
                },
            },
            {
                "noteId": 2,
                "modelName": "Vocabulary",
                "fields": {
                    "Mandarin": {"value": "你好"},
                    "Audio": {"value": "[sound:existing.mp3]"},
                },
            },
            {
                "noteId": 3,
                "modelName": "General",
                "fields": {
                    "Recto": {"value": "Signification de pinyin"},
                    "Verso": {"value": "Spell-Sounds"},
                },
            },
        ]

    def invoke(self, action: str, **params):
        if action == "findNotes":
            return [note["noteId"] for note in self.notes]
        if action == "notesInfo":
            wanted = set(params["notes"])
            return [note for note in self.notes if note["noteId"] in wanted]
        if action == "getMediaFilesNames":
            return []
        if action == "storeMediaFile":
            self.stored.append(params)
            return params["filename"]
        if action == "updateNoteFields":
            self.updated.append(params["note"])
            note_id = params["note"]["id"]
            for note in self.notes:
                if note["noteId"] == note_id:
                    for name, value in params["note"]["fields"].items():
                        note["fields"][name]["value"] = value
            return None
        if action == "addTags":
            self.tags.append(params)
            return None
        raise AssertionError(action)


class MissingAnkiAudioTests(unittest.TestCase):
    def test_discovers_only_silent_mandarin_note_with_audio_field(self) -> None:
        candidates, stats = fill_audio.discover_candidates(FakeAnkiConnect())
        self.assertEqual([candidate.text for candidate in candidates], ["今年"])
        self.assertEqual(stats["candidates"], 1)
        self.assertEqual(stats["already_has_sound"], 1)
        self.assertEqual(stats["no_audio_field"], 1)

    def test_generates_stores_and_updates_audio(self) -> None:
        client = FakeAnkiConnect()
        candidates, _ = fill_audio.discover_candidates(client)

        def generator(text: str, path: str | Path) -> str:
            self.assertEqual(text, "今年")
            Path(path).write_bytes(b"ID3" + b"x" * 2_000)
            return "youdao"

        with tempfile.TemporaryDirectory() as temporary:
            results = fill_audio.fill_candidates(
                client,
                candidates,
                Path(temporary),
                generator=generator,
            )

        self.assertEqual(results[0]["provider"], "youdao")
        self.assertEqual(len(client.stored), 1)
        self.assertIn("[sound:anki_zh_", client.updated[0]["fields"]["Audio"])
        self.assertEqual(
            client.tags[0]["tags"],
            "chinois::audio::source::youdao",
        )


if __name__ == "__main__":
    unittest.main()
