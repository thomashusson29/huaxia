"""
Module d'exportation vers Anki via AnkiConnect (API local port 8765) 
avec repli automatique vers la création d'un fichier .apkg (via genanki).
"""

import os
import json
import requests
import genanki
from typing import List, Dict, Any

ANKI_CONNECT_URL = "http://127.0.0.1:8765"
DECK_NAME = "Chineasy"
MODEL_NAME = "Chineasy Character Model"

MODEL_CSS = """
.card {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 18px;
    text-align: center;
    color: #2c3e50;
    background-color: #f8f9fa;
    padding: 20px;
}
.nightMode .card {
    color: #ecf0f1;
    background-color: #1a1a2e;
}
.hanzi {
    font-size: 110px;
    font-weight: bold;
    margin-top: 20px;
    margin-bottom: 20px;
    color: #e74c3c;
}
.pinyin {
    font-size: 32px;
    font-weight: 600;
    color: #2980b9;
    margin-bottom: 10px;
}
.nightMode .pinyin {
    color: #3498db;
}
.english {
    font-size: 26px;
    font-weight: 500;
    text-transform: capitalize;
    color: #27ae60;
    margin-bottom: 15px;
}
.nightMode .english {
    color: #2ecc71;
}
.story {
    font-size: 16px;
    line-height: 1.5;
    color: #7f8c8d;
    max-width: 500px;
    margin: 0 auto 20px auto;
    font-style: italic;
}
.nightMode .story {
    color: #bdc3c7;
}
.mnemo-img {
    max-width: 250px;
    max-height: 250px;
    margin-top: 15px;
    border-radius: 12px;
}
"""

CARD_FRONT = """
<div class="card">
    <div class="hanzi">{{Hanzi}}</div>
</div>
"""

CARD_BACK = """
<div class="card">
    <div class="hanzi" style="font-size: 60px;">{{Hanzi}}</div>
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

def invoke_ankiconnect(action: str, **params) -> Dict[str, Any]:
    """Helper pour appeler l'API AnkiConnect."""
    payload = {"action": action, "version": 6, "params": params}
    response = requests.post(ANKI_CONNECT_URL, json=payload, timeout=5)
    if response.status_code == 200:
        res = response.json()
        if res.get("error"):
            raise Exception(res.get("error"))
        return res.get("result")
    raise Exception(f"HTTP Error {response.status_code}")

def check_ankiconnect_available() -> bool:
    """Vérifie si AnkiConnect est actif en arrière-plan."""
    try:
        res = invoke_ankiconnect("version")
        return res is not None
    except Exception:
        return False

def export_via_ankiconnect(cards: List[Dict[str, Any]]) -> bool:
    """
    Exporte les cartes directement dans Anki via AnkiConnect.
    """
    print("[AnkiConnect] Synchronisation directe vers Anki...")
    
    # 1. Vérifier / Créer le Deck
    decks = invoke_ankiconnect("deckNames")
    if DECK_NAME not in decks:
        invoke_ankiconnect("createDeck", deck=DECK_NAME)
        
    # 2. Vérifier / Créer le Modèle de Note
    models = invoke_ankiconnect("modelNames")
    if MODEL_NAME not in models:
        invoke_ankiconnect(
            "createModel",
            modelName=MODEL_NAME,
            inOrderFields=["Hanzi", "Pinyin", "Anglais", "Explication", "ImageMnemo"],
            css=MODEL_CSS,
            cardTemplates=[
                {
                    "Name": "Card 1",
                    "Front": CARD_FRONT,
                    "Back": CARD_BACK
                }
            ]
        )

    # 3. Envoyer les images médias et créer les notes
    notes_to_add = []
    for card in cards:
        img_html = ""
        mnemo_path = card.get("processed_mnemonic_image") or card.get("mnemonic_image")
        
        if mnemo_path and os.path.exists(mnemo_path):
            filename = os.path.basename(mnemo_path)
            # Envoi du fichier média dans Anki
            invoke_ankiconnect("storeMediaFile", filename=filename, path=os.path.abspath(mnemo_path))
            img_html = f'<img class="mnemo-img" src="{filename}">'

        notes_to_add.append({
            "deckName": DECK_NAME,
            "modelName": MODEL_NAME,
            "fields": {
                "Hanzi": card.get("hanzi", ""),
                "Pinyin": card.get("pinyin", ""),
                "Anglais": card.get("english", ""),
                "Explication": card.get("story", ""),
                "ImageMnemo": img_html
            },
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck"
            }
        })
        
    if notes_to_add:
        results = invoke_ankiconnect("addNotes", notes=notes_to_add)
        print(f"[AnkiConnect] {len(notes_to_add)} cartes synchronisées avec succès !")
        return True
    return False

def export_via_genanki(cards: List[Dict[str, Any]], output_apkg_path: str = "Chineasy.apkg") -> str:
    """
    Exporte les cartes au format .apkg autonome à importer dans Anki.
    """
    print(f"[genanki] Génération du paquet autonome {output_apkg_path}...")
    
    # ID uniques stables pour le modèle et le deck
    model_id = 1607392319
    deck_id = 2059401923
    
    my_model = genanki.Model(
        model_id,
        MODEL_NAME,
        fields=[
            {"name": "Hanzi"},
            {"name": "Pinyin"},
            {"name": "Anglais"},
            {"name": "Explication"},
            {"name": "ImageMnemo"}
        ],
        templates=[
            {
                "name": "Card 1",
                "qfmt": CARD_FRONT,
                "afmt": CARD_BACK
            }
        ],
        css=MODEL_CSS
    )

    my_deck = genanki.Deck(deck_id, DECK_NAME)
    media_files = []

    for card in cards:
        img_html = ""
        mnemo_path = card.get("processed_mnemonic_image") or card.get("mnemonic_image")
        if mnemo_path and os.path.exists(mnemo_path):
            filename = os.path.basename(mnemo_path)
            media_files.append(os.path.abspath(mnemo_path))
            img_html = f'<img class="mnemo-img" src="{filename}">'
            
        note = genanki.Note(
            model=my_model,
            fields=[
                card.get("hanzi", ""),
                card.get("pinyin", ""),
                card.get("english", ""),
                card.get("story", ""),
                img_html
            ]
        )
        my_deck.add_note(note)

    package = genanki.Package(my_deck)
    package.media_files = media_files
    package.write_to_file(output_apkg_path)
    print(f"[genanki] Paquet généré avec succès : {output_apkg_path}")
    return output_apkg_path

def export_to_anki(cards: List[Dict[str, Any]], apkg_output_path: str = "Chineasy.apkg") -> bool:
    """
    Tente l'export direct AnkiConnect, sinon génère le fichier .apkg.
    """
    if check_ankiconnect_available():
        try:
            return export_via_ankiconnect(cards)
        except Exception as e:
            print(f"[AnkiConnect] Erreur de synchronisation ({e}), bascule sur genanki...")
    else:
        print("[AnkiConnect] AnkiConnect non détecté (Anki n'est pas ouvert).")

    export_via_genanki(cards, apkg_output_path)
    return True
