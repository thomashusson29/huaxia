"""
Application Web locale Flask pour l'interface graphique Chineasy to Anki.
Permet de choisir les dossiers de captures, de visualiser le terminal de traitement en direct (SSE)
et d'afficher la galerie des cartes Anki créées (avec écoute audio et prévisualisation des images).
"""

import os
import sys
import glob
import json
import queue
import threading
from flask import Flask, render_template, request, Response, send_from_directory, jsonify

# Ajout du dossier courant au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ocr_extractor import extract_card_info
from src.image_processor import remove_background
from src.card_matcher import match_cards
from src.audio_generator import generate_audio_sync
from src.anki_exporter import export_to_anki

app = Flask(__name__, template_folder="templates")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURES_DIR = os.path.join(BASE_DIR, "captures")
MEDIA_DIR = os.path.join(BASE_DIR, "output_media")
AUDIO_DIR = os.path.join(BASE_DIR, "output_audio")

PROCESSED_TAG = "_PROCESSED"

class StreamLogger:
    """Capteur personnalisé pour rediriger le stdout vers la file SSE."""
    def __init__(self, log_queue):
        self.queue = log_queue
        self.terminal = sys.stdout

    def write(self, message):
        self.terminal.write(message)
        if message.strip():
            self.queue.put(message.strip())

    def flush(self):
        self.terminal.flush()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/folders")
def get_folders():
    """Renvoie la liste des dossiers de captures disponibles."""
    if not os.path.exists(CAPTURES_DIR):
        return jsonify([])
        
    subdirs = [
        d for d in os.listdir(CAPTURES_DIR)
        if os.path.isdir(os.path.join(CAPTURES_DIR, d))
    ]
    subdirs = sorted(subdirs)
    
    result = []
    for d in subdirs:
        full_path = os.path.join(CAPTURES_DIR, d)
        is_processed = PROCESSED_TAG in d or "processed" in d.lower()
        rel_path = os.path.relpath(full_path, BASE_DIR)
        result.append({
            "name": d,
            "path": rel_path,
            "is_processed": is_processed
        })
        
    return jsonify(result)

@app.route("/media/<filename>")
def serve_media(filename):
    return send_from_directory(MEDIA_DIR, filename)

@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)

@app.route("/api/process")
def process_stream():
    folder_path = request.args.get("folder", "captures").strip()
    full_folder = os.path.abspath(os.path.join(BASE_DIR, folder_path))
    
    def event_stream():
        log_queue = queue.Queue()
        old_stdout = sys.stdout
        sys.stdout = StreamLogger(log_queue)
        
        cards_result = []

        def run_pipeline():
            nonlocal cards_result
            try:
                print(f"=== Traitement du dossier : {folder_path} ===")
                
                extensions = ("*.jpg", "*.jpeg", "*.png", "*.PNG")
                image_paths = []
                for ext in extensions:
                    image_paths.extend(glob.glob(os.path.join(full_folder, ext)))
                    
                image_paths = sorted(list(set(image_paths)))
                if not image_paths:
                    print("Aucune image trouvée.")
                    return
                    
                print(f"[1/6] {len(image_paths)} images trouvées.")

                # 2. Extraction OCR
                print("[2/6] Extraction du texte et analyse des cartes...")
                extracted_cards = []
                for idx, path in enumerate(image_paths, 1):
                    print(f"  ({idx}/{len(image_paths)}) Analyse de {os.path.basename(path)}...")
                    info = extract_card_info(path)
                    extracted_cards.append(info)

                # 3. Appariement
                print("[3/6] Appariement des cartes...")
                paired_cards = match_cards(extracted_cards)
                print(f"  -> {len(paired_cards)} cartes complètes associées.")

                # 4. Détourage transparent
                print("[4/6] Détourage transparent des illustrations mnémotechniques...")
                os.makedirs(MEDIA_DIR, exist_ok=True)
                for card in paired_cards:
                    mnemo_img = card.get("mnemonic_image")
                    if mnemo_img and os.path.exists(mnemo_img):
                        base_name = os.path.splitext(os.path.basename(mnemo_img))[0]
                        clean_eng = card.get("english", "img").replace(" ", "_")
                        out_name = f"mnemo_{clean_eng}_{base_name}.png"
                        out_path = os.path.join(MEDIA_DIR, out_name)
                        try:
                            processed_path = remove_background(mnemo_img, out_path, color_tolerance=40.0)
                            card["processed_mnemonic_image"] = processed_path
                            print(f"  [OK Image] Détourage généré : {out_name}")
                        except Exception as e:
                            print(f"  [Erreur Image] {e}")

                # 5. Génération Audio MP3
                print("[5/6] Génération automatique de la prononciation audio mandarin HD...")
                os.makedirs(AUDIO_DIR, exist_ok=True)
                for card in paired_cards:
                    hanzi = card.get("hanzi")
                    if hanzi:
                        audio_filename = f"audio_zh_{hanzi}.mp3"
                        audio_out_path = os.path.join(AUDIO_DIR, audio_filename)
                        try:
                            res_audio = generate_audio_sync(hanzi, audio_out_path)
                            if res_audio:
                                card["audio_path"] = res_audio
                                print(f"  [OK Audio] Fichier audio généré pour '{hanzi}' : {audio_filename}")
                        except Exception as e:
                            print(f"  [Erreur Audio] {e}")

                # 6. Exportation Anki
                print("[6/6] Exportation vers Anki...")
                export_to_anki(paired_cards)
                
                # Formater les cartes pour le rendu JSON Web
                for c in paired_cards:
                    img_path = c.get("processed_mnemonic_image") or c.get("mnemonic_image")
                    audio_path = c.get("audio_path")
                    cards_result.append({
                        "hanzi": c.get("hanzi"),
                        "pinyin": c.get("pinyin"),
                        "english": c.get("english"),
                        "story": c.get("story"),
                        "img_filename": os.path.basename(img_path) if img_path else "",
                        "audio_filename": os.path.basename(audio_path) if audio_path else ""
                    })

                # Renommer le dossier traité
                if not PROCESSED_TAG in full_folder:
                    new_folder_path = full_folder.rstrip("/\\") + PROCESSED_TAG
                    try:
                        os.rename(full_folder, new_folder_path)
                        print(f"[Succès] Dossier renommé en '{os.path.basename(new_folder_path)}'.")
                    except Exception as e:
                        print(f"[Avertissement] Renommage ignoré: {e}")

            except Exception as e:
                print(f"[Erreur Pipeline] {e}")
            finally:
                sys.stdout = old_stdout

        thread = threading.Thread(target=run_pipeline)
        thread.start()

        while thread.is_alive() or not log_queue.empty():
            try:
                msg = log_queue.get(timeout=0.2)
                yield f"data: {json.dumps({'type': 'log', 'text': msg})}\n\n"
            except queue.Empty:
                pass
                
        thread.join()
        yield f"data: {json.dumps({'type': 'result', 'cards': cards_result})}\n\n"

    return Response(event_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    port = 5001
    print(f"\n🚀 Interface graphique Chineasy to Anki démarrée sur : http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False)
