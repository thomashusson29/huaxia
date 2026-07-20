"""
Module d'exportation vers Anki via AnkiConnect (API local ports 8766 / 8765) 
générant 2 cartes automatiques par note avec fond sombre #2c2c2c en mode nuit.
"""

import os
import json
import requests
import genanki
from typing import List, Dict, Any

ANKI_CONNECT_PORTS = [8766, 8765]
DECK_NAME = "chinois::chineasy_characters"
MODEL_NAME = "Chineasy Character Model v3"

MODEL_CSS = """
.card {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    font-size: 18px;
    text-align: center;
    color: #2c3e50;
    background-color: #f8f9fa;
    padding: 20px;
}
.nightMode .card {
    color: #abb2bf;
    background-color: #2c2c2c;
}
.card-type-header {
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #61afef;
    margin-bottom: 15px;
    font-weight: 600;
}
.hanzi {
    font-size: 110px;
    font-weight: bold;
    margin-top: 15px;
    margin-bottom: 15px;
    color: #e06c75;
}
.pinyin {
    font-size: 32px;
    font-weight: 600;
    color: #56b6c2;
    margin-bottom: 10px;
}
.english {
    font-size: 26px;
    font-weight: 600;
    text-transform: capitalize;
    color: #98c379;
    margin-bottom: 15px;
}
.story {
    font-size: 15px;
    line-height: 1.6;
    color: #abb2bf;
    max-width: 550px;
    margin: 15px auto 20px auto;
    font-style: italic;
    white-space: pre-wrap;
    text-align: center;
}
.mnemo-img {
    max-width: 250px;
    max-height: 250px;
    margin-top: 15px;
    border-radius: 12px;
}

/* Style de saisie Pinyin et Canvas de dessin */
input#typeans {
    font-size: 20px !important;
    padding: 8px 12px !important;
    border-radius: 6px !important;
    border: 1px solid #3e4451 !important;
    background: #21252b !important;
    color: #61afef !important;
    text-align: center !important;
    margin: 15px auto !important;
    display: block !important;
    width: 80% !important;
    max-width: 300px !important;
}
.canvas-container {
    margin: 15px auto;
    display: inline-block;
}
#strokeCanvas {
    border: 1px dashed #61afef;
    border-radius: 8px;
    background-color: #21252b;
    cursor: crosshair;
    touch-action: none;
}
.btn-clear {
    display: block;
    margin: 8px auto 0 auto;
    background: #3b404d;
    color: #abb2bf;
    border: 1px solid #454c5c;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
}
"""

CARD1_FRONT = """
<div class="card">
    <div class="hanzi">{{Hanzi}}</div>
</div>
"""

CARD1_BACK = """
<div class="card">
    <div class="hanzi" style="font-size: 60px;">{{Hanzi}}</div>
    <div class="pinyin">{{Pinyin}} {{Audio}}</div>
    <div class="english">{{Anglais}}</div>
    {{#Explication}}
    <div class="story">{{Explication}}</div>
    {{/Explication}}
    {{#ImageMnemo}}
    <div>{{ImageMnemo}}</div>
    {{/ImageMnemo}}
</div>
"""

CARD2_FRONT = """
<div class="card">
    <div class="card-type-header">Écoute & Prononciation</div>
    <div style="margin: 15px 0; transform: scale(1.3);">{{Audio}}</div>
    <div>{{type:Pinyin}}</div>
    
    <div class="canvas-container">
        <canvas id="strokeCanvas" width="220" height="220"></canvas>
        <button type="button" class="btn-clear" onclick="clearCanvas(event)">Effacer le dessin</button>
    </div>
</div>

<script>
(function() {
    var canvas = document.getElementById('strokeCanvas');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    ctx.lineWidth = 4;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#61afef';
    var drawing = false;

    function getPos(e) {
        var rect = canvas.getBoundingClientRect();
        var clientX = e.touches ? e.touches[0].clientX : e.clientX;
        var clientY = e.touches ? e.touches[0].clientY : e.clientY;
        return { x: clientX - rect.left, y: clientY - rect.top };
    }

    function startDraw(e) { drawing = true; ctx.beginPath(); var p = getPos(e); ctx.moveTo(p.x, p.y); }
    function moveDraw(e) { if (!drawing) return; e.preventDefault(); var p = getPos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); }
    function stopDraw() { drawing = false; }

    canvas.addEventListener('mousedown', startDraw);
    canvas.addEventListener('mousemove', moveDraw);
    canvas.addEventListener('mouseup', stopDraw);
    canvas.addEventListener('touchstart', startDraw);
    canvas.addEventListener('touchmove', moveDraw);
    canvas.addEventListener('touchend', stopDraw);

    window.clearCanvas = function(e) {
        if (e) e.stopPropagation();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
})();
</script>
"""

CARD2_BACK = """
<div class="card">
    <div>{{type:Pinyin}}</div>
    <div class="hanzi" style="font-size: 65px; margin-top: 15px;">{{Hanzi}}</div>
    <div class="pinyin">{{Pinyin}}</div>
    <div class="english">{{Anglais}}</div>
    {{#Explication}}
    <div class="story">{{Explication}}</div>
    {{/Explication}}
    {{#ImageMnemo}}
    <div>{{ImageMnemo}}</div>
    {{/ImageMnemo}}
</div>
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
        raise Exception("AnkiConnect non disponible")
        
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

def export_via_ankiconnect(cards: List[Dict[str, Any]]) -> bool:
    url = get_active_ankiconnect_url()
    print(f"[AnkiConnect] Synchronisation vers Anki ({url}) dans le deck '{DECK_NAME}'...")
    
    decks = invoke_ankiconnect("deckNames")
    if DECK_NAME not in decks:
        invoke_ankiconnect("createDeck", deck=DECK_NAME)
        
    # Toujours forcer la mise à jour du style CSS (mode nuit #2c2c2c)
    try:
        invoke_ankiconnect("updateModelStyling", model={"name": MODEL_NAME, "css": MODEL_CSS})
        invoke_ankiconnect("updateModelTemplates", model={
            "name": MODEL_NAME,
            "templates": {
                "1. Reconnaissance Visuelle": {"Front": CARD1_FRONT, "Back": CARD1_BACK},
                "2. Écoute Audio & Écriture": {"Front": CARD2_FRONT, "Back": CARD2_BACK}
            }
        })
    except Exception as e:
        print(f"  [Styling Update Warning] {e}")

    models = invoke_ankiconnect("modelNames")
    if MODEL_NAME not in models:
        invoke_ankiconnect(
            "createModel",
            modelName=MODEL_NAME,
            inOrderFields=["Hanzi", "Pinyin", "Anglais", "Explication", "ImageMnemo", "Audio"],
            css=MODEL_CSS,
            cardTemplates=[
                {"Name": "1. Reconnaissance Visuelle", "Front": CARD1_FRONT, "Back": CARD1_BACK},
                {"Name": "2. Écoute Audio & Écriture", "Front": CARD2_FRONT, "Back": CARD2_BACK}
            ]
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

        note_fields = {
            "Hanzi": hanzi,
            "Pinyin": card.get("pinyin", ""),
            "Anglais": card.get("english", ""),
            "Explication": card.get("story", ""),
            "ImageMnemo": img_html,
            "Audio": audio_sound_tag
        }

        query = f'"deck:{DECK_NAME}" "Hanzi:{hanzi}"'
        existing_notes = invoke_ankiconnect("findNotes", query=query)
        if not existing_notes:
            query_fallback = f'"Hanzi:{hanzi}"'
            existing_notes = invoke_ankiconnect("findNotes", query=query_fallback)

        if existing_notes:
            primary_id = existing_notes[0]
            invoke_ankiconnect("updateNoteFields", note={"id": primary_id, "fields": note_fields})
            print(f"  [Mise à jour 2-Cartes] Note '{hanzi}' (ID: {primary_id}) mise à jour.")
            updated_count += 1
            
            if len(existing_notes) > 1:
                duplicate_ids = existing_notes[1:]
                invoke_ankiconnect("deleteNotes", notes=duplicate_ids)
                print(f"  [Nettoyage Doublons] Supprimé {len(duplicate_ids)} doublon(s) pour '{hanzi}'.")
        else:
            note_payload = {
                "deckName": DECK_NAME,
                "modelName": MODEL_NAME,
                "fields": note_fields,
                "options": {
                    "allowDuplicate": False,
                    "duplicateScope": "deck"
                }
            }
            try:
                note_id = invoke_ankiconnect("addNote", note=note_payload)
                print(f"  [OK 2-Cartes] Note '{hanzi}' (ID: {note_id}) générée.")
                added_count += 1
            except Exception as err:
                note_payload["options"]["allowDuplicate"] = True
                note_id = invoke_ankiconnect("addNote", note=note_payload)
                print(f"  [OK Duplicate Allowed] Note '{hanzi}' ajoutée.")
                added_count += 1

    print(f"[AnkiConnect] Synchronisation terminée : {added_count} note(s) créée(s), {updated_count} mise(s) à jour.")
    return True

def export_via_genanki(cards: List[Dict[str, Any]], output_apkg_path: str = "Chineasy.apkg") -> str:
    print(f"[genanki] Génération du paquet autonome {output_apkg_path}...")
    model_id = 1607392325
    deck_id = 2059401923
    
    my_model = genanki.Model(
        model_id,
        MODEL_NAME,
        fields=[
            {"name": "Hanzi"},
            {"name": "Pinyin"},
            {"name": "Anglais"},
            {"name": "Explication"},
            {"name": "ImageMnemo"},
            {"name": "Audio"}
        ],
        templates=[
            {"name": "1. Reconnaissance Visuelle", "qfmt": CARD1_FRONT, "afmt": CARD1_BACK},
            {"name": "2. Écoute Audio & Écriture", "qfmt": CARD2_FRONT, "afmt": CARD2_BACK}
        ],
        css=MODEL_CSS
    )

    my_deck = genanki.Deck(deck_id, DECK_NAME)
    media_files = []

    for card in cards:
        img_html = ""
        audio_sound_tag = ""
        
        mnemo_path = card.get("processed_mnemonic_image") or card.get("mnemonic_image")
        if mnemo_path and os.path.exists(mnemo_path):
            img_filename = os.path.basename(mnemo_path)
            media_files.append(os.path.abspath(mnemo_path))
            img_html = f'<img class="mnemo-img" src="{img_filename}">'
            
        audio_path = card.get("audio_path")
        if audio_path and os.path.exists(audio_path):
            audio_filename = os.path.basename(audio_path)
            media_files.append(os.path.abspath(audio_path))
            audio_sound_tag = f"[sound:{audio_filename}]"

        note = genanki.Note(
            model=my_model,
            fields=[
                card.get("hanzi", ""),
                card.get("pinyin", ""),
                card.get("english", ""),
                card.get("story", ""),
                img_html,
                audio_sound_tag
            ]
        )
        my_deck.add_note(note)

    package = genanki.Package(my_deck)
    package.media_files = media_files
    package.write_to_file(output_apkg_path)
    return output_apkg_path

def export_to_anki(cards: List[Dict[str, Any]], apkg_output_path: str = "Chineasy.apkg") -> bool:
    if check_ankiconnect_available():
        try:
            return export_via_ankiconnect(cards)
        except Exception as e:
            print(f"[AnkiConnect] Erreur de synchronisation ({e}), bascule sur genanki...")
    else:
        print("[AnkiConnect] AnkiConnect non détecté (Anki n'est pas ouvert).")

    export_via_genanki(cards, apkg_output_path)
    return True
