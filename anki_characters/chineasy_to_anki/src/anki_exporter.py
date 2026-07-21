"""
Module d'exportation vers Anki via AnkiConnect (API local ports 8766 / 8765) 
avec génération audio automatique systématique, recherche exacte du Hanzi, tags hiérarchisés 
et rendu adaptatif Mode Clair / Mode Nuit (#2c2c2c).
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
MODEL_NAME = "Chineasy Character Model v3"

# Yoyo Chinese Defaults
YOYO_DECK_NAME = "chinois::yoyo_chinese"
YOYO_MODEL_NAME = "Yoyo Chinese Model"

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
    font-size: 32px;
    font-weight: 600;
    color: #0284c7;
    margin-bottom: 10px;
}
.nightMode .pinyin {
    color: #56b6c2;
}

.english {
    font-size: 26px;
    font-weight: 600;
    text-transform: capitalize;
    color: #16a34a;
    margin-bottom: 15px;
}
.nightMode .english {
    color: #98c379;
}

.story {
    font-size: 15px;
    line-height: 1.6;
    color: #475569;
    max-width: 550px;
    margin: 15px auto 20px auto;
    font-style: italic;
    white-space: pre-wrap;
    text-align: center;
}
.nightMode .story {
    color: #abb2bf;
}

.mnemo-img {
    max-width: 250px;
    max-height: 250px;
    margin-top: 15px;
    border-radius: 12px;
}

/* Zone de Saisie - Mode Clair */
input#typeans {
    font-size: 22px !important;
    padding: 8px 12px !important;
    border-radius: 6px !important;
    border: 1px solid #cbd5e1 !important;
    background: #ffffff !important;
    color: #0284c7 !important;
    text-align: center !important;
    margin: 15px auto !important;
    display: block !important;
    width: 80% !important;
    max-width: 300px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
}

/* Zone de Saisie - Mode Nuit */
.nightMode input#typeans {
    border: 1px solid #3e4451 !important;
    background: #1e2227 !important;
    color: #61afef !important;
    box-shadow: none !important;
}

code#typeans {
    font-size: 20px !important;
    background: transparent !important;
}

/* Tableau Blanc Dessin - Mode Clair */
.canvas-container {
    margin: 15px auto;
    display: inline-block;
}
#strokeCanvas {
    border: 1px dashed #0284c7;
    border-radius: 8px;
    background-color: #ffffff;
    cursor: crosshair;
    touch-action: none;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.nightMode #strokeCanvas {
    border: 1px dashed #61afef;
    background-color: #1e2227;
    box-shadow: none;
}

/* Bouton Effacer - Mode Clair & Nuit */
.btn-clear {
    display: block;
    margin: 8px auto 0 auto;
    background: #f1f5f9;
    color: #334155;
    border: 1px solid #cbd5e1;
    padding: 5px 14px;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
    font-weight: 500;
}
.nightMode .btn-clear {
    background: #3b404d;
    color: #abb2bf;
    border: 1px solid #454c5c;
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
    <div class="card-type-header">Écoute & Écriture (Pinyin ou Caractères)</div>
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
    
    var isNight = document.body.classList.contains('nightMode') || 
                  (document.documentElement && document.documentElement.classList.contains('nightMode'));
    ctx.strokeStyle = isNight ? '#61afef' : '#0284c7';
    
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

<script>
(function() {
    var typeans = document.getElementById('typeans');
    if (!typeans) return;
    
    var userText = typeans.innerText.trim();
    var targetHanzi = "{{Hanzi}}".trim();
    var targetPinyin = "{{Pinyin}}".trim();

    function removeAccents(str) {
        return str.normalize("NFKD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase().replace(/\\s+/g, '');
    }

    var normUser = removeAccents(userText);
    var normPinyin = removeAccents(targetPinyin);
    var normHanzi = targetHanzi.replace(/\\s+/g, '');

    var isNight = document.body.classList.contains('nightMode') || 
                  (document.documentElement && document.documentElement.classList.contains('nightMode'));
    var successColor = isNight ? '#98c379' : '#16a34a';

    if (userText === targetHanzi || normUser === normHanzi || normUser === normPinyin) {
        typeans.innerHTML = '<div style="color:' + successColor + '; font-weight:bold; font-size:22px; margin: 10px 0;">✓ Correct : ' + userText + '</div>';
    }
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

def find_exact_note_ids_for_hanzi(hanzi: str, deck_name: str = DECK_NAME) -> List[int]:
    """Trouve les ID de notes Anki ayant EXACTEMENT ce Hanzi."""
    query = f'"deck:{deck_name}" "Hanzi:{hanzi}"'
    matched_ids = invoke_ankiconnect("findNotes", query=query)
    if not matched_ids:
        matched_ids = invoke_ankiconnect("findNotes", query=f'"Hanzi:{hanzi}"')
        
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
        
    try:
        invoke_ankiconnect("updateModelStyling", model={"name": target_model, "css": MODEL_CSS})
        invoke_ankiconnect("updateModelTemplates", model={
            "name": target_model,
            "templates": {
                "1. Reconnaissance Visuelle": {"Front": CARD1_FRONT, "Back": CARD1_BACK},
                "2. Écoute Audio & Écriture": {"Front": CARD2_FRONT, "Back": CARD2_BACK}
            }
        })
    except Exception as e:
        print(f"  [Styling Update Warning] {e}")

    models = invoke_ankiconnect("modelNames")
    if target_model not in models:
        invoke_ankiconnect(
            "createModel",
            modelName=target_model,
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

        # Définition des tags
        default_tags = ["chinois", "chineasy"] if target_deck == DECK_NAME else ["chinois", "yoyochinese"]
        card_tags = card.get("tags") or default_tags

        existing_notes = find_exact_note_ids_for_hanzi(hanzi, target_deck)

        if existing_notes:
            primary_id = existing_notes[0]
            invoke_ankiconnect("updateNoteFields", note={"id": primary_id, "fields": note_fields, "tags": card_tags})
            print(f"  [Mise à jour] Note '{hanzi}' (ID: {primary_id}) mise à jour avec tags : {card_tags}.")
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
                print(f"  [OK Duplicate Allowed] Note '{hanzi}' ajoutée avec tags {card_tags}.")
                added_count += 1

    print(f"[AnkiConnect] Synchronisation terminée pour {target_deck} : {added_count} note(s) créée(s), {updated_count} mise(s) à jour.")
    return True

def export_via_genanki(cards: List[Dict[str, Any]], output_apkg_path: str = "Chineasy.apkg", target_deck: str = DECK_NAME, target_model: str = MODEL_NAME) -> str:
    print(f"[genanki] Génération du paquet autonome {output_apkg_path}...")
    model_id = 1607392325 if target_deck == DECK_NAME else 1607392999
    deck_id = 2059401923 if target_deck == DECK_NAME else 2059401888
    
    my_model = genanki.Model(
        model_id,
        target_model,
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

    my_deck = genanki.Deck(deck_id, target_deck)
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

        story_text = card.get("story", "") or card.get("explanation", "")
        if card.get("literal"):
            story_text = f"{card.get('literal')}\n\n{story_text}".strip()

        default_tags = ["chinois", "chineasy"] if target_deck == DECK_NAME else ["chinois", "yoyochinese"]
        card_tags = card.get("tags") or default_tags

        note = genanki.Note(
            model=my_model,
            fields=[
                card.get("hanzi", ""),
                card.get("pinyin", ""),
                card.get("english", ""),
                story_text,
                img_html,
                audio_sound_tag
            ],
            tags=card_tags
        )
        my_deck.add_note(note)

    package = genanki.Package(my_deck)
    package.media_files = media_files
    package.write_to_file(output_apkg_path)
    return output_apkg_path

def export_to_anki(cards: List[Dict[str, Any]], apkg_output_path: str = "Chineasy.apkg") -> bool:
    if check_ankiconnect_available():
        try:
            return export_via_ankiconnect(cards, DECK_NAME, MODEL_NAME)
        except Exception as e:
            print(f"[AnkiConnect] Erreur de synchronisation ({e}), bascule sur genanki...")
    else:
        print("[AnkiConnect] AnkiConnect non détecté (Anki n'est pas ouvert).")

    export_via_genanki(cards, apkg_output_path, DECK_NAME, MODEL_NAME)
    return True

def export_yoyo_to_anki(items: List[Dict[str, Any]], apkg_output_path: str = "YoyoChinese.apkg") -> bool:
    """Exportation des cartes Yoyo Chinese vers le deck 'chinois::yoyo_chinese'."""
    if check_ankiconnect_available():
        try:
            return export_via_ankiconnect(items, YOYO_DECK_NAME, YOYO_MODEL_NAME)
        except Exception as e:
            print(f"[AnkiConnect] Erreur Yoyo ({e}), bascule sur genanki...")
    else:
        print("[AnkiConnect] AnkiConnect non détecté.")

    export_via_genanki(items, apkg_output_path, YOYO_DECK_NAME, YOYO_MODEL_NAME)
    return True
