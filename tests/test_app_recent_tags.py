from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from anki_characters.chineasy_to_anki import app as app_module
from anki_characters.chineasy_to_anki.update_anki_tags import (
    MigrationRecord,
    MigrationReport,
    RECENT_QUERY,
)


def sample_report(*, changed: bool = True) -> MigrationReport:
    records = (
        (
            MigrationRecord(
                note_id=123,
                model="Enhanced Cloze 2.1 v2",
                label="他",
                add=("chinois::caracteres::hanzi::他",),
                remove=(),
                preserved_count=1,
                warnings=(),
            ),
        )
        if changed
        else ()
    )
    return MigrationReport(
        generated_at="2026-07-29T12:00:00+02:00",
        mode="addition",
        cleanup_legacy=False,
        query=RECENT_QUERY,
        notes_scanned=1,
        notes_changed=1 if changed else 0,
        tags_added=1 if changed else 0,
        tags_removed=0,
        warnings=0,
        records=records,
    )


class RecentTagsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()
        with app_module.recent_tag_previews_lock:
            app_module.recent_tag_previews.clear()

    @patch.object(app_module, "prepare_live_report")
    @patch.object(app_module, "get_migration_ankiconnect_url")
    def test_preview_is_scoped_to_added_one_day(
        self,
        get_url,
        prepare_report,
    ) -> None:
        get_url.return_value = "http://127.0.0.1:8765"
        prepare_report.return_value = sample_report()

        response = self.client.post(
            "/api/tags/recent",
            json={"apply": False, "cleanup_legacy": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["preview_token"])
        self.assertEqual(payload["report"]["query"], RECENT_QUERY)
        prepare_report.assert_called_once_with(
            "http://127.0.0.1:8765",
            query='deck:"chinois" added:1',
            cleanup_legacy=False,
        )

    def test_apply_is_refused_without_confirmation(self) -> None:
        response = self.client.post(
            "/api/tags/recent",
            json={"apply": True, "cleanup_legacy": False},
        )
        self.assertEqual(response.status_code, 400)

    @patch.object(app_module, "apply_report")
    @patch.object(app_module, "backup_chinese_deck")
    @patch.object(app_module, "prepare_live_report")
    @patch.object(app_module, "get_migration_ankiconnect_url")
    def test_apply_requires_unchanged_preview_and_creates_backup(
        self,
        get_url,
        prepare_report,
        backup,
        apply_report,
    ) -> None:
        get_url.return_value = "http://127.0.0.1:8765"
        preview_report = sample_report()
        prepare_report.return_value = preview_report
        backup.return_value = Path("/tmp/chinois.apkg")

        preview_response = self.client.post(
            "/api/tags/recent",
            json={"apply": False, "cleanup_legacy": False},
        )
        preview_token = preview_response.get_json()["preview_token"]

        apply_response = self.client.post(
            "/api/tags/recent",
            json={
                "apply": True,
                "cleanup_legacy": False,
                "confirm": "AJOUTER_TAGS_CHINOIS",
                "preview_token": preview_token,
            },
        )

        self.assertEqual(apply_response.status_code, 200)
        self.assertTrue(apply_response.get_json()["applied"])
        backup.assert_called_once()
        apply_report.assert_called_once()

    @patch.object(app_module, "prepare_live_report")
    @patch.object(app_module, "get_migration_ankiconnect_url")
    def test_changed_collection_invalidates_preview(
        self,
        get_url,
        prepare_report,
    ) -> None:
        get_url.return_value = "http://127.0.0.1:8765"
        prepare_report.return_value = sample_report()
        preview_response = self.client.post(
            "/api/tags/recent",
            json={"apply": False, "cleanup_legacy": False},
        )
        preview_token = preview_response.get_json()["preview_token"]

        changed_report = replace(sample_report(), tags_added=2)
        prepare_report.return_value = changed_report
        apply_response = self.client.post(
            "/api/tags/recent",
            json={
                "apply": True,
                "cleanup_legacy": False,
                "confirm": "AJOUTER_TAGS_CHINOIS",
                "preview_token": preview_token,
            },
        )

        self.assertEqual(apply_response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
