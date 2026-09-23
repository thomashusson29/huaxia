#!/usr/bin/env python3
"""Synchronize Yoyo Chinese cards with a local AnkiConnect instance."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from huaxia_tags import (  # noqa: E402
    HANZI_TAG_PREFIX,
    PINYIN_TAG_PREFIX,
    YOYO_SOURCE_TAG_PREFIX,
    plan_tag_update,
)

try:
    from .anki_export import (
        FIELD_NAMES,
        MODEL_NAME,
        collect_all_cards,
        model_layout,
        note_fields,
    )
except ImportError:  # Script execution from the yoyochinese directory.
    from anki_export import (
        FIELD_NAMES,
        MODEL_NAME,
        collect_all_cards,
        model_layout,
        note_fields,
    )


ANKI_CONNECT_PORTS = (8766, 8765)
DEFAULT_DECK_NAME = "chinois::ychinese::bulk export"


class AnkiConnectError(RuntimeError):
    pass


class AnkiConnectClient:
    def __init__(self, url: str, timeout: int = 30) -> None:
        self.url = url
        self.timeout = timeout

    def invoke(self, action: str, **params: Any) -> Any:
        payload = json.dumps(
            {"action": action, "version": 6, "params": params},
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            self.url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise AnkiConnectError(f"AnkiConnect inaccessible: {exc}") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AnkiConnectError("Réponse AnkiConnect illisible.") from exc
        if not isinstance(result, dict) or "error" not in result or "result" not in result:
            raise AnkiConnectError("Réponse AnkiConnect inattendue.")
        if result["error"]:
            raise AnkiConnectError(f"AnkiConnect ({action}): {result['error']}")
        return result["result"]

    @classmethod
    def find(cls, timeout: int = 2) -> AnkiConnectClient | None:
        for port in ANKI_CONNECT_PORTS:
            client = cls(f"http://127.0.0.1:{port}", timeout=timeout)
            try:
                if client.invoke("version") is not None:
                    client.timeout = 30
                    return client
            except AnkiConnectError:
                continue
        return None


def _ensure_model(client: AnkiConnectClient) -> None:
    css, card1_front, card1_back, card2_front, card2_back = model_layout()
    model_names = client.invoke("modelNames") or []
    if MODEL_NAME not in model_names:
        client.invoke(
            "createModel",
            modelName=MODEL_NAME,
            inOrderFields=FIELD_NAMES,
            css=css,
            cardTemplates=[
                {
                    "Name": "1. Reconnaissance Visuelle",
                    "Front": card1_front,
                    "Back": card1_back,
                },
                {
                    "Name": "2. Écoute Audio & Écriture",
                    "Front": card2_front,
                    "Back": card2_back,
                },
            ],
        )
        return
    actual_fields = client.invoke("modelFieldNames", modelName=MODEL_NAME) or []
    if actual_fields != FIELD_NAMES:
        raise AnkiConnectError(
            f"Le modèle Anki « {MODEL_NAME} » existe avec des champs différents. "
            "Renommez-le ou supprimez-le avant la synchronisation bulk export."
        )
    client.invoke(
        "updateModelStyling",
        model={"name": MODEL_NAME, "css": css},
    )
    client.invoke(
        "updateModelTemplates",
        model={
            "name": MODEL_NAME,
            "templates": {
                "1. Reconnaissance Visuelle": {
                    "Front": card1_front,
                    "Back": card1_back,
                },
                "2. Écoute Audio & Écriture": {
                    "Front": card2_front,
                    "Back": card2_back,
                },
            },
        },
    )


def _existing_notes_by_yoyo_id(
    client: AnkiConnectClient,
) -> dict[str, dict[str, Any]]:
    note_ids = client.invoke("findNotes", query="YoyoId:*") or []
    by_yoyo_id: dict[str, dict[str, Any]] = {}
    for start in range(0, len(note_ids), 500):
        notes = client.invoke("notesInfo", notes=note_ids[start : start + 500]) or []
        for note in notes:
            field = note.get("fields", {}).get("YoyoId", {})
            yoyo_id = str(field.get("value") or "").strip()
            if yoyo_id and yoyo_id not in by_yoyo_id:
                by_yoyo_id[yoyo_id] = note
    return by_yoyo_id


def _store_sound(
    client: AnkiConnectClient,
    path_value: str,
    stored_media: dict[str, str],
) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_file() or path.stat().st_size == 0:
        return ""
    filename = path.name
    previous = stored_media.get(filename)
    if previous and Path(previous).resolve() != path.resolve():
        raise AnkiConnectError(f"Deux sons Anki portent le même nom: {filename}")
    if not previous:
        client.invoke("storeMediaFile", filename=filename, path=str(path.resolve()))
        stored_media[filename] = str(path.resolve())
    return f"[sound:{filename}]"


def sync_plans(
    plans: Iterable[Any],
    *,
    deck_name: str = DEFAULT_DECK_NAME,
    client: AnkiConnectClient | None = None,
) -> dict[str, Any]:
    client = client or AnkiConnectClient.find()
    if client is None:
        return {
            "status": "unavailable",
            "deck_name": deck_name,
            "card_count": 0,
            "added_count": 0,
            "updated_count": 0,
            "media_count": 0,
        }

    cards = collect_all_cards(plans)
    if not cards:
        return {
            "status": "empty",
            "deck_name": deck_name,
            "card_count": 0,
            "added_count": 0,
            "updated_count": 0,
            "media_count": 0,
        }
    client.invoke("createDeck", deck=deck_name)
    _ensure_model(client)
    existing_notes = _existing_notes_by_yoyo_id(client)
    stored_media: dict[str, str] = {}
    moved_card_ids: list[int] = []
    added_count = 0
    updated_count = 0

    for card in cards:
        normal_tag = _store_sound(client, card["normal_path"], stored_media)
        slow_tag = _store_sound(client, card["slow_path"], stored_media)
        fields = note_fields(card, normal_tag, slow_tag)
        tags = sorted(card["tags"])
        existing_note = existing_notes.get(card["id"])
        if existing_note is None:
            note_id = client.invoke(
                "addNote",
                note={
                    "deckName": deck_name,
                    "modelName": MODEL_NAME,
                    "fields": fields,
                    "tags": tags,
                    "options": {"allowDuplicate": True},
                },
            )
            if note_id is None:
                raise AnkiConnectError(f"Anki n’a pas ajouté la carte {card['id']}")
            existing_notes[card["id"]] = {
                "noteId": int(note_id),
                "tags": tags,
                "fields": {"YoyoId": {"value": card["id"]}},
            }
            added_count += 1
            continue
        note_id = int(existing_note["noteId"])
        client.invoke("updateNoteFields", note={"id": note_id, "fields": fields})
        legacy_pinyin = [
            tag.removeprefix(PINYIN_TAG_PREFIX)
            for tag in tags
            if tag.startswith(PINYIN_TAG_PREFIX)
        ]
        tag_update = plan_tag_update(
            existing_note.get("tags", []),
            tags,
            owned_prefixes=(
                HANZI_TAG_PREFIX,
                PINYIN_TAG_PREFIX,
                YOYO_SOURCE_TAG_PREFIX,
            ),
            cleanup_legacy=True,
            legacy_flat_values=legacy_pinyin,
        )
        if tag_update.remove:
            client.invoke(
                "removeTags",
                notes=[note_id],
                tags=" ".join(tag_update.remove),
            )
        if tag_update.add:
            client.invoke(
                "addTags",
                notes=[note_id],
                tags=" ".join(tag_update.add),
            )
        existing_note["tags"] = list(tag_update.final)
        card_ids = client.invoke("findCards", query=f"nid:{note_id}") or []
        moved_card_ids.extend(int(card_id) for card_id in card_ids)
        updated_count += 1

    if moved_card_ids:
        client.invoke("changeDeck", cards=sorted(set(moved_card_ids)), deck=deck_name)
    return {
        "status": "synced",
        "url": client.url,
        "deck_name": deck_name,
        "card_count": len(cards),
        "added_count": added_count,
        "updated_count": updated_count,
        "media_count": len(stored_media),
    }


def sync_packages(
    package_paths: Iterable[str | Path],
    *,
    deck_name: str = DEFAULT_DECK_NAME,
    client: AnkiConnectClient | None = None,
) -> dict[str, Any]:
    """Import APKG files, then consolidate every Yoyo card in the bulk deck."""
    client = client or AnkiConnectClient.find(timeout=5)
    if client is None:
        return {
            "status": "unavailable",
            "deck_name": deck_name,
            "package_count": 0,
            "note_count": 0,
            "card_count": 0,
        }
    packages = [Path(path).resolve() for path in package_paths]
    missing = [str(path) for path in packages if not path.is_file()]
    if missing:
        raise AnkiConnectError(f"Paquet Anki introuvable: {missing[0]}")
    if not packages:
        return {
            "status": "empty",
            "deck_name": deck_name,
            "package_count": 0,
            "note_count": 0,
            "card_count": 0,
        }

    client.timeout = 1_800
    client.invoke("createDeck", deck=deck_name)
    imported: list[dict[str, Any]] = []
    for package in packages:
        result = client.invoke("importPackage", path=str(package))
        imported.append({"path": str(package), "result": result})

    note_ids = client.invoke("findNotes", query="YoyoId:*") or []
    card_ids = client.invoke("findCards", query="YoyoId:*") or []
    for start in range(0, len(card_ids), 5_000):
        client.invoke(
            "changeDeck",
            cards=card_ids[start : start + 5_000],
            deck=deck_name,
        )
    return {
        "status": "synced",
        "url": client.url,
        "deck_name": deck_name,
        "package_count": len(packages),
        "note_count": len(note_ids),
        "card_count": len(card_ids),
        "packages": imported,
    }
