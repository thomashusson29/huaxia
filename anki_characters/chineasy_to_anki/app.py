"""
Application Web locale Flask pour l'interface graphique Chineasy & Yoyo Chinese to Anki.
Permet d'importer et traiter les captures Chineasy (chinois::chineasy_characters)
ainsi que les fiches de cours PDF Yoyo Chinese (chinois::yoyo_chinese).
"""

import os
import sys
import glob
import json
import queue
import threading
from flask import Flask, render_template, request, Response, send_from_directory, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ocr_extractor import extract_card_info
from src.image_processor import remove_background
from src.card_matcher import match_cards
from src.audio_generator import generate_audio_sync
from src.anki_exporter import export_to_anki, export_yoyo_to_anki
from src.anki_to_obsidian import export_anki_notes_to_obsidian
from src.yoyo_parser import parse_yoyo_pdf

app = Flask(__name__, template_folder="templates")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURES_DIR = os.path.join(BASE_DIR, "captures")
PDF_INPUT_DIR = os.path.join(BASE_DIR, "pdf_input")
MEDIA_DIR = os.path.join(BASE_DIR, "output_media")
AUDIO_DIR = os.path.join(BASE_DIR, "output_audio")
MARKDOWN_DIR = os.path.join(BASE_DIR, "output_markdown")

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

@app.route("/api/pdf_files")
def get_pdf_files():
    """Renvoie la liste des fichiers PDF disponibles dans pdf_input/."""
    os.makedirs(PDF_INPUT_DIR, exist_ok=True)
    files = glob.glob(os.path.join(PDF_INPUT_DIR, "*.pdf"))
    files += glob.glob(os.path.join(PDF_INPUT_DIR, "*.PDF"))
    
    # Également vérifier les fichiers d'exemple externes si présents
    example_pdf = "/Users/thomashusson/Documents/Projets/Docs_internat/Chinois/yoyo_chinese/Beg-Unit-001-Lesson-01-LN.pdf"
    if os.path.exists(example_pdf) and example_pdf not in files:
        files.append(example_pdf)

    res = []
    for f in sorted(list(set(files))):
        res.append({
            "name": os.path.basename(f),
            "path": f
        })
    return jsonify(res)

@app.route("/api/upload_pdf", methods=["POST"])
def upload_pdf():
    """Route pour uploader ou glisser-déposer un fichier PDF Yoyo Chinese."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "Aucun fichier reçu"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "Nom de fichier vide"}), 400
        
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"success": False, "error": "Format non supporté (seuls les PDF sont acceptés)"}), 400

    os.makedirs(PDF_INPUT_DIR, exist_ok=True)
    save_path = os.path.join(PDF_INPUT_DIR, file.filename)
    file.save(save_path)
    return jsonify({"success": True, "filename": file.filename, "path": save_path})

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
                print(f"=== Traitement du dossier Chineasy : {folder_path} ===")
                
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
                print("[6/7] Exportation vers Anki...")
                export_to_anki(paired_cards)

                # 7. Synchronisation Obsidian
                print("[7/7] Synchronisation vers le coffre Obsidian...")
                try:
                    res_obs = export_anki_notes_to_obsidian()
                    if res_obs.get("success"):
                        print(f"  [OK Obsidian] {res_obs.get('exported_count')} fiches exportées.")
                except Exception as e_obs:
                    print(f"  [Avertissement Obsidian] {e_obs}")
                
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

@app.route("/api/process_pdf")
def process_pdf_stream():
    """Pipeline de traitement SSE pour les cours PDF Yoyo Chinese."""
    pdf_path = request.args.get("pdf_path", "").strip()
    if not pdf_path:
        pdf_path = "/Users/thomashusson/Documents/Projets/Docs_internat/Chinois/yoyo_chinese/Beg-Unit-001-Lesson-01-LN.pdf"
        
    full_pdf_path = os.path.abspath(pdf_path)

    def event_stream():
        log_queue = queue.Queue()
        old_stdout = sys.stdout
        sys.stdout = StreamLogger(log_queue)
        
        cards_result = []

        def run_yoyo_pipeline():
            nonlocal cards_result
            try:
                print(f"=== Traitement du cours PDF Yoyo Chinese : {os.path.basename(full_pdf_path)} ===")
                
                # 1. Parsing PDF -> Markdown -> Structure
                print("[1/4] Conversion PDF vers Markdown & Extraction du vocabulaire et phrases...")
                parsed_data = parse_yoyo_pdf(full_pdf_path, MARKDOWN_DIR)
                items = parsed_data.get("items", [])
                print(f"  -> {len(items)} élément(s) extrait(s) (Mots & Phrases). Markdown généré dans output_markdown/")

                # 2. Génération Audio HD Mandarin
                print("[2/4] Génération automatique des fichiers audio mandarin HD...")
                os.makedirs(AUDIO_DIR, exist_ok=True)
                for idx, item in enumerate(items, 1):
                    hanzi = item.get("hanzi")
                    if hanzi:
                        audio_filename = f"audio_zh_{hanzi}.mp3"
                        audio_out_path = os.path.join(AUDIO_DIR, audio_filename)
                        try:
                            res_audio = generate_audio_sync(hanzi, audio_out_path)
                            if res_audio:
                                item["audio_path"] = res_audio
                                print(f"  ({idx}/{len(items)}) [OK Audio] '{hanzi}' : {audio_filename}")
                        except Exception as e:
                            print(f"  ({idx}/{len(items)}) [Erreur Audio] '{hanzi}': {e}")

                # 3. Export vers le deck Anki 'chinois::yoyo_chinese'
                print("[3/4] Exportation des notes vers le deck Anki 'chinois::yoyo_chinese'...")
                export_yoyo_to_anki(items)

                # 4. Formater les cartes pour l'affichage Web
                for it in items:
                    audio_p = it.get("audio_path")
                    story_text = it.get("literal", "")
                    cards_result.append({
                        "hanzi": it.get("hanzi"),
                        "pinyin": it.get("pinyin"),
                        "english": it.get("english"),
                        "story": story_text,
                        "img_filename": "",
                        "audio_filename": os.path.basename(audio_p) if audio_p else ""
                    })

                print(f"[Succès] Traitement Yoyo Chinese terminé ! 2 cartes générées par note pour {len(items)} mots/phrases.")

            except Exception as e:
                print(f"[Erreur Yoyo Pipeline] {e}")
            finally:
                sys.stdout = old_stdout

        thread = threading.Thread(target=run_yoyo_pipeline)
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

@app.route("/api/export_obsidian", methods=["POST"])
def export_obsidian():
    """Endpoint pour exporter manuellement toutes les cartes Anki vers Obsidian."""
    req_data = request.get_json(silent=True) or {}
    deck_name = req_data.get("deck_name", "chinois::chineasy_characters")
    try:
        res = export_anki_notes_to_obsidian(deck_name=deck_name)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = 5001
    print(f"\n🚀 Interface graphique Chineasy & Yoyo Chinese to Anki démarrée sur : http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False)
