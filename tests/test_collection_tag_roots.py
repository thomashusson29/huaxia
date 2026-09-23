from __future__ import annotations

import sys
from pathlib import Path
import unittest


APP_DIR = Path(__file__).resolve().parents[1] / "anki_characters" / "chineasy_to_anki"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import update_collection_tag_roots as migration  # noqa: E402


def note(note_id: int, tags: list[str]) -> dict:
    return {
        "noteId": note_id,
        "modelName": "Basic",
        "tags": tags,
        "fields": {"Front": {"value": f"note {note_id}"}},
    }


class CollectionTagRootTests(unittest.TestCase):
    def test_statistics_hierarchy_is_preserved_below_new_root(self) -> None:
        add, remove = migration.plan_note_tags(
            ["M2biostatistiques::annales", "annee::2022", "_mdanki::id::1"],
            category="statistiques",
        )
        self.assertEqual(
            set(add),
            {
                "statistiques::M2biostatistiques::annales",
                "statistiques::annee::2022",
            },
        )
        self.assertEqual(set(remove), {"M2biostatistiques::annales", "annee::2022"})

    def test_existing_internat_root_and_technical_tags_are_preserved(self) -> None:
        add, remove = migration.plan_note_tags(
            ["internat", "internat::source::DES", "TNCD::estomac", "_mdanki::x"],
            category="internat",
        )
        self.assertEqual(add, ("internat::TNCD::estomac",))
        self.assertEqual(remove, ("TNCD::estomac",))

    def test_medical_tag_vocabulary_classifies_external_medical_note(self) -> None:
        notes = [
            note(1, ["foie", "TNCD"]),
            note(2, ["foie", "journal", "robot"]),
            note(3, ["M2biostatistiques", "annee::2024"]),
        ]
        report = migration.build_report(
            notes,
            statistics_note_ids=[3],
            medical_deck_note_ids=[1],
        )
        records = {record.note_id: record for record in report.records}
        self.assertEqual(records[2].category, "internat")
        self.assertIn("internat::journal", records[2].add)
        self.assertEqual(records[3].category, "statistiques")

    def test_unclassified_manual_tag_is_preserved_with_warning(self) -> None:
        report = migration.build_report(
            [note(4, ["mythologie"])],
            statistics_note_ids=[],
            medical_deck_note_ids=[],
        )
        self.assertEqual(report.notes_changed, 0)
        self.assertEqual(report.warnings, 1)
        self.assertEqual(report.records[0].remove, ())


if __name__ == "__main__":
    unittest.main()
