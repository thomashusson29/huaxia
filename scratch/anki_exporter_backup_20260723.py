"""
Module d'exportation vers Anki via AnkiConnect (API local ports 8766 / 8765) 
avec génération audio automatique systématique, lecture audio automatique forcée au chargement des cartes,
recherche exacte du Hanzi ciblée par deck, tags hiérarchisés et rendu adaptatif Mode Clair / Mode Nuit (#2c2c2c).
Prise en charge de Chineasy (chinois::chineasy_characters) et de Yoyo Chinese (chinois::yoyo_chinese).
"""

import os
import json
import requests
import genanki
from typing import List, Dict, Any

ANKI_CONNECT_PORTS = [8766, 8765]

# Chineasy Defaults
DECK_NAME = "chinois::chineasy_characters"
SHARED_MODEL_NAME = "Yoyo Chinese Model v2-41f05"
MODEL_NAME = SHARED_MODEL_NAME

# Yoyo Chinese Defaults
YOYO_DECK_NAME = "chinois::yoyo_chinese"
YOYO_MODEL_NAME = SHARED_MODEL_NAME

MODEL_FIELD_NAMES = [
    "Hanzi",
    "Traditional",
    "Pinyin",
    "Anglais",
    "Explication",
    "ImageMnemo",
    "Audio",
    "AudioLent",
    "YoyoId",
    "Source",
]

MODEL_CSS = """
.card {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    font-size: 18px;
    text-align: center;
    color: #2c3e50;
    background-color: #ffffff;
    padding: 20px;
}

/* Mode Nuit */
.nightMode .card, body.nightMode {
    color: #abb2bf;
    background-color: #2c2c2c !important;
}

.card-type-header {
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #0284c7;
    margin-bottom: 15px;
    font-weight: 600;
}
.nightMode .card-type-header {
    color: #61afef;
}

.hanzi {
    font-size: 110px;
    font-weight: bold;
    margin-top: 15px;
    margin-bottom: 15px;
    color: #e11d48;
}
.nightMode .hanzi {
    color: #e06c75;
}

.pinyin {
    font-size: 28px;
    font-weight: 500;
    color: #0d9488;
    margin-bottom: 10px;
}
.nightMode .pinyin {
    color: #56b6c2;
}

.english {
    font-size: 22px;
    font-weight: 600;
    color: #16a34a;
    margin-bottom: 20px;
}
.nightMode .english {
    color: #98c379;
}

.mnemo-box {
    margin: 20px auto;
    padding: 15px;
    background: #f8fafc;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    display: inline-block;
    max-width: 90%;
}
.nightMode .mnemo-box {
    background: #21252b;
    border-color: #3e4451;
}

.mnemo-img {
    max-height: 280px;
    max-width: 100%;
    object-fit: contain;
    border-radius: 8px;
}

.story {
    font-size: 16px;
    line-height: 1.6;
    color: #475569;
    text-align: left;
    margin-top: 20px;
    padding: 15px;
    background-color: #f1f5f9;
    border-left: 4px solid #0284c7;
    border-radius: 4px;
}
.nightMode .story {
    color: #abb2bf;
    background-color: #21252b;
    border-left-color: #61afef;
}

.hint-text {
    font-size: 14px;
    color: #64748b;
    font-style: italic;
    margin-top: 15px;
}
.nightMode .hint-text {
    color: #5c6370;
}
"""

CARD1_FRONT = """
<div class="card-type-header">Chineasy — Reconnaissance Visuelle</div>
<div class="hanzi">{{Hanzi}}</div>
<div class="hint-text">Quel est le Pinyin et le sens de ce caractère ?</div>
"""

CARD1_BACK = """
<div class="card-type-header">Chineasy — Reconnaissance Visuelle</div>
<div class="hanzi">{{Hanzi}}</div>
<div class="pinyin">{{Pinyin}} {{Audio}}</div>
<div class="english">{{Anglais}}</div>

{{#ImageMnemo}}
<div class="mnemo-box">
    {{ImageMnemo}}
</div>
{{/ImageMnemo}}

{{#Explication}}
<div class="story">
    {{Explication}}
</div>
{{/Explication}}

<script>
(function() {
    var playAudio = function() {
        var audioLinks = document.querySelectorAll('a.replay-button, .soundLink, a[href*="javascript:py.link"]');
        if (audioLinks.length > 0) {
            audioLinks[0].click();
        }
    };
    setTimeout(playAudio, 100);
})();
</script>
"""

CARD2_FRONT = """
<div class="card-type-header">Chineasy — Écoute & Écriture</div>
<div class="pinyin" style="font-size: 36px; margin-top: 30px;">{{Pinyin}} {{Audio}}</div>
<div class="english" style="margin-top: 15px;">{{Anglais}}</div>
<div class="hint-text" style="margin-top: 40px;">Tracez ou devinez le caractère Hanzi correspondant.</div>

<script>
(function() {
    var playAudio = function() {
        var audioLinks = document.querySelectorAll('a.replay-button, .soundLink, a[href*="javascript:py.link"]');
        if (audioLinks.length > 0) {
            audioLinks[0].click();
        }
    };
    setTimeout(playAudio, 100);
})();
</script>
"""

CARD2_BACK = """
<div class="card-type-header">Chineasy — Écoute & Écriture</div>
<div class="hanzi">{{Hanzi}}</div>
<div class="pinyin">{{Pinyin}} {{Audio}}</div>
<div class="english">{{Anglais}}</div>

{{#ImageMnemo}}
<div class="mnemo-box">
    {{ImageMnemo}}
</div>
{{/ImageMnemo}}

{{#Explication}}
<div class="story">
    {{Explication}}
</div>
{{/Explication}}

<script>
(function() {
    var playAudio = function() {
        var audioLinks = document.querySelectorAll('a.replay-button, .soundLink, a[href*="javascript:py.link"]');
        if (audioLinks.length > 0) {
            audioLinks[0].click();
        }
    };
    setTimeout(playAudio, 100);
})();
</script>
"""

def get_active_ankiconnect_url() -> str:
    for port in ANKI_CONNECT_PORTS:
        url = f"http://127.0.0.1:{port}"
        try:
            res = requests.post(url, json={"action": "version", "version": 6}, timeout=2)
            if res.status_code == 200 and res.json().get("result") is not None:
                return url
        except Exception:
            continue
    return ""

def invoke_ankiconnect(action: str, **params) -> Any:
    url = get_active_ankiconnect_url()
    if not url:
        raise Exception("AnkiConnect n'est disponible sur aucun port (8766 / 8765).")
        
    payload = {"action": action, "version": 6, "params": params}
    response = requests.post(url, json=payload, timeout=10)
    if response.status_code == 200:
        res = response.json()
        if res.get("error"):
            raise Exception(res.get("error"))
        return res.get("result")
    raise Exception(f"HTTP Error {response.status_code}")

def check_ankiconnect_available() -> bool:
    return bool(get_active_ankiconnect_url())

def find_exact_note_ids_for_hanzi(hanzi: str, deck_name: str = DECK_NAME) -> List[int]:
    """Trouve les ID de notes Anki ayant EXACTEMENT ce Hanzi dans ce deck spécifique."""
    query = f'"deck:{deck_name}" "Hanzi:{hanzi}"'
    matched_ids = invoke_ankiconnect("findNotes", query=query)
    if not matched_ids:
        return []
        
    info = invoke_ankiconnect("notesInfo", notes=matched_ids)
    exact_ids = []
    for n in info:
        val = n['fields'].get('Hanzi', {}).get('value', '').strip()
        if val == hanzi:
            exact_ids.append(n['noteId'])
    return exact_ids

def export_via_ankiconnect(cards: List[Dict[str, Any]], target_deck: str = DECK_NAME, target_model: str = MODEL_NAME) -> bool:
    url = get_active_ankiconnect_url()
    print(f"[AnkiConnect] Synchronisation vers Anki ({url}) dans le deck '{target_deck}'...")
    
    decks = invoke_ankiconnect("deckNames")
    if target_deck not in decks:
        invoke_ankiconnect("createDeck", deck=target_deck)

    models = invoke_ankiconnect("modelNames")
    if target_model not in models:
        raise Exception(
            f"Le modèle Anki unique '{target_model}' est absent. "
            "L'export est interrompu pour ne pas recréer un type de note parallèle."
        )

    actual_fields = invoke_ankiconnect("modelFieldNames", modelName=target_model)
    if actual_fields != MODEL_FIELD_NAMES:
        raise Exception(
            f"Le modèle Anki unique '{target_model}' possède un schéma inattendu : "
            f"{actual_fields!r}."
        )

    templates = invoke_ankiconnect("modelTemplates", modelName=target_model)
    listening_template = templates.get("2. Écoute Audio & Écriture")
    if not listening_template:
        raise Exception(
            "Le modèle Anki unique ne contient pas la carte "
            "'2. Écoute Audio & Écriture'."
        )
    if (
        'id="huaxiaAnswer"' not in listening_template.get("Front", "")
        or "normalizePinyin" not in listening_template.get("Back", "")
        or "normalizeHanzi" not in listening_template.get("Back", "")
        or "{{ImageMnemo}}" not in listening_template.get("Back", "")
    ):
        raise Exception(
            "Le gabarit Anki unique n'est pas la version validée "
            "(saisie hanzi/pinyin ou image mnémotechnique absente/incomplète)."
        )

    added_count = 0
    updated_count = 0

    for card in cards:
        hanzi = card.get("hanzi", "")
        if not hanzi:
            continue

        img_html = ""
        audio_sound_tag = ""
        
        mnemo_path = card.get("processed_mnemonic_image") or card.get("mnemonic_image")
        if mnemo_path and os.path.exists(mnemo_path):
            img_filename = os.path.basename(mnemo_path)
            try:
                invoke_ankiconnect("storeMediaFile", filename=img_filename, path=os.path.abspath(mnemo_path))
                img_html = f'<img class="mnemo-img" src="{img_filename}">'
            except Exception as e:
                print(f"  [Media Image Error] {e}")

        audio_path = card.get("audio_path")
        if audio_path and os.path.exists(audio_path):
            audio_filename = os.path.basename(audio_path)
            try:
                invoke_ankiconnect("storeMediaFile", filename=audio_filename, path=os.path.abspath(audio_path))
                audio_sound_tag = f"[sound:{audio_filename}]"
            except Exception as e:
                print(f"  [Media Audio Error] {e}")

        story_text = card.get("story", "") or card.get("explanation", "")
        if card.get("literal"):
            story_text = f"{card.get('literal')}\n\n{story_text}".strip()

        note_fields = {
            "Hanzi": hanzi,
            "Pinyin": card.get("pinyin", ""),
            "Anglais": card.get("english", ""),
            "Explication": story_text,
            "ImageMnemo": img_html,
            "Audio": audio_sound_tag
        }

        default_tags = ["chinois", "chineasy"] if target_deck == DECK_NAME else ["chinois", "yoyochinese"]
        card_tags = card.get("tags") or default_tags

        existing_notes = find_exact_note_ids_for_hanzi(hanzi, target_deck)

        if existing_notes:
            primary_id = existing_notes[0]
            invoke_ankiconnect("updateNoteFields", note={"id": primary_id, "fields": note_fields})
            if card_tags:
                invoke_ankiconnect("addTags", notes=[primary_id], tags=" ".join(card_tags))
            print(f"  [Mise à jour] Note '{hanzi}' (ID: {primary_id}) mise à jour avec tags {card_tags}.")
            updated_count += 1
            
            if len(existing_notes) > 1:
                duplicate_ids = existing_notes[1:]
                invoke_ankiconnect("deleteNotes", notes=duplicate_ids)
                print(f"  [Nettoyage Doublons] Supprimé {len(duplicate_ids)} doublon(s) pour '{hanzi}'.")
        else:
            note_payload = {
                "deckName": target_deck,
                "modelName": target_model,
                "fields": note_fields,
                "tags": card_tags,
                "options": {
                    "allowDuplicate": False,
                    "duplicateScope": "deck"
                }
            }
            try:
                note_id = invoke_ankiconnect("addNote", note=note_payload)
                print(f"  [OK Note] Note '{hanzi}' (ID: {note_id}) générée avec tags {card_tags}.")
                added_count += 1
            except Exception as err:
                note_payload["options"]["allowDuplicate"] = True
                note_id = invoke_ankiconnect("addNote", note=note_payload)
                if card_tags:
                    invoke_ankiconnect("addTags", notes=[note_id], tags=" ".join(card_tags))
                print(f"  [OK Duplicate Allowed] Note '{hanzi}' ajoutée avec tags {card_tags}.")
                added_count += 1

    print(f"[AnkiConnect] Synchronisation terminée pour {target_deck} : {added_count} note(s) créée(s), {updated_count} mise(s) à jour.")
    return True

def export_to_anki(cards: List[Dict[str, Any]]) -> bool:
    """Exporte des cartes vers Anki (Chineasy)."""
    return export_via_ankiconnect(cards, target_deck=DECK_NAME, target_model=MODEL_NAME)

def export_yoyo_to_anki(items: List[Dict[str, Any]]) -> bool:
    """Exporte des éléments du cours Yoyo Chinese vers Anki."""
    return export_via_ankiconnect(items, target_deck=YOYO_DECK_NAME, target_model=YOYO_MODEL_NAME)
