from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import app as downloader_app


class InterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output_root = self.root / "downloads"
        self.obsidian_root = self.root / "obsidian"
        self.lesson_dir = self.output_root / "lecon-2"
        self.lesson_dir.mkdir(parents=True)
        self.lesson = self.lesson_dir / "lecon-2.md"
        self.lesson.write_text(
            "# Leçon 2\n\n<audio controls src=\"audio/test.mp3\"></audio>\n",
            encoding="utf-8",
        )
        self.obsidian_root.mkdir()
        self.obsidian_dir = self.obsidian_root / "lecon-2"
        self.obsidian_dir.symlink_to(self.lesson_dir, target_is_directory=True)
        self.summary = {
            "directory": str(self.lesson_dir),
            "archive": str(self.output_root / "lecon-2.zip"),
            "lesson": str(self.lesson),
            "manifest": str(self.lesson_dir / "manifest.json"),
            "obsidian_directory": str(self.obsidian_dir),
            "obsidian_lesson": str(self.obsidian_dir / "lecon-2.md"),
            "images": 3,
            "audio": 2,
        }
        self.original_output_root = downloader_app.OUTPUT_ROOT
        self.original_obsidian_root = downloader_app.OBSIDIAN_ROOT
        self.original_downloader = downloader_app.DOWNLOADER
        downloader_app.OUTPUT_ROOT = self.output_root
        downloader_app.OBSIDIAN_ROOT = self.obsidian_root
        downloader_app.DOWNLOADER = Path(__file__)
        downloader_app.app.config.update(TESTING=True)
        self.client = downloader_app.app.test_client()

    def tearDown(self) -> None:
        downloader_app.OUTPUT_ROOT = self.original_output_root
        downloader_app.OBSIDIAN_ROOT = self.original_obsidian_root
        downloader_app.DOWNLOADER = self.original_downloader
        self.temporary.cleanup()

    def test_get_displays_url_form(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="url"', response.data)
        self.assertIn("Télécharger".encode(), response.data)

    @patch.object(downloader_app.subprocess, "run")
    def test_post_displays_generated_markdown_and_obsidian_path(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(self.summary), stderr=""
        )
        response = self.client.post(
            "/",
            data={"url": "https://www.lechinoisfacile.fr/cours/lecon/lecon-2/"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(self.obsidian_dir / "lecon-2.md").encode(), response.data)
        self.assertIn(b"# Le\xc3\xa7on 2", response.data)
        self.assertIn(b"&lt;audio controls", response.data)
        command = run.call_args.args[0]
        self.assertIn("--output-root", command)
        self.assertIn("--obsidian-root", command)

    @patch.object(downloader_app.subprocess, "run")
    def test_downloader_error_is_shown(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=2, stdout="", stderr="Erreur : URL refusée"
        )
        response = self.client.post("/", data={"url": "https://example.com/lecon/1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("URL refusée".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
