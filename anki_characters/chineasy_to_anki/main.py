"""
Script principal d'automatisation Chineasy vers Anki.
Scanne les dossiers de captures non traités, extrait les textes, détoure les images mnémotechniques,
génère la prononciation audio HD MP3 en mandarin,
apparie les cartes, synchronise directement vers le deck Anki 'chinois::chineasy_characters',
et marque les dossiers traités en les renommant avec le suffixe '_PROCESSED'.
"""

import os
import glob
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ocr_extractor import extract_card_info
from src.image_processor import remove_background
from src.card_matcher import match_cards
from src.audio_generator import generate_audio_sync
from src.anki_exporter import export_to_anki

PROCESSED_TAG = "_PROCESSED"

def is_processed_folder(path: str) -> bool:
    """Vérifie si un dossier est déjà marqué comme traité."""
    base = os.path.basename(path.rstrip("/\\"))
    return PROCESSED_TAG in base or "processed" in base.lower()

def process_single_folder(folder_path: str, output_media_dir: str = "output_media", output_audio_dir: str = "output_audio") -> bool:
    """
    Traite un dossier spécifique de captures d'écran.
    """
    if is_processed_folder(folder_path):
        print(f"[Ignoré] Le dossier '{folder_path}' a déjà été traité ({PROCESSED_TAG}).")
        return False

    print(f"\n=== Traitement du dossier : {folder_path} ===")
    
    extensions = ("*.jpg", "*.jpeg", "*.png", "*.PNG")
    image_paths = []
    for ext in extensions:
        image_paths.extend(glob.glob(os.path.join(folder_path, ext)))
        
    image_paths = sorted(list(set(image_paths)))
    if not image_paths:
        print(f"Aucune image trouvée dans '{folder_path}'.")
        return False
        
    print(f"[1/6] {len(image_paths)} images trouvées dans {os.path.basename(folder_path)}.")

    # 2. Extraction OCR & Métadonnées
    print("[2/6] Extraction du texte et analyse des cartes...")
    extracted_cards = []
    for idx, path in enumerate(image_paths, 1):
        print(f"  ({idx}/{len(image_paths)}) Analyse de {os.path.basename(path)}...")
        info = extract_card_info(path)
        extracted_cards.append(info)

    # 3. Appariement intelligent
    print("[3/6] Appariement des cartes...")
    paired_cards = match_cards(extracted_cards)
    print(f"  -> {len(paired_cards)} cartes complètes associées.")

    # 4. Traitement d'image & Détourage transparent
    print("[4/6] Détourage transparent des illustrations mnémotechniques...")
    os.makedirs(output_media_dir, exist_ok=True)
    
    for card in paired_cards:
        mnemo_img = card.get("mnemonic_image")
        if mnemo_img and os.path.exists(mnemo_img):
            base_name = os.path.splitext(os.path.basename(mnemo_img))[0]
            clean_eng = card.get("english", "img").replace(" ", "_")
            out_name = f"mnemo_{clean_eng}_{base_name}.png"
            out_path = os.path.join(output_media_dir, out_name)
            
            try:
                processed_path = remove_background(mnemo_img, out_path, color_tolerance=40.0)
                card["processed_mnemonic_image"] = processed_path
                print(f"  [OK Image] Détourage généré : {out_name}")
            except Exception as e:
                print(f"  [Erreur Image] Échec du détourage pour {mnemo_img}: {e}")
                card["processed_mnemonic_image"] = mnemo_img

    # 5. Génération Audio MP3 (Prononciation Mandarin HD)
    print("[5/6] Génération automatique de la prononciation audio mandarin HD...")
    os.makedirs(output_audio_dir, exist_ok=True)
    
    for card in paired_cards:
        hanzi = card.get("hanzi")
        if hanzi:
            audio_filename = f"audio_zh_{hanzi}.mp3"
            audio_out_path = os.path.join(output_audio_dir, audio_filename)
            try:
                res_audio = generate_audio_sync(hanzi, audio_out_path)
                if res_audio:
                    card["audio_path"] = res_audio
                    print(f"  [OK Audio] Fichier audio généré pour '{hanzi}' : {audio_filename}")
            except Exception as e:
                print(f"  [Erreur Audio] Échec audio pour '{hanzi}': {e}")

    # 6. Exportation vers Anki
    print("[6/6] Exportation vers Anki...")
    export_to_anki(paired_cards)
    
    # 7. Marquer le dossier comme traité (Renommage)
    new_folder_path = folder_path.rstrip("/\\") + PROCESSED_TAG
    try:
        os.rename(folder_path, new_folder_path)
        print(f"[Succès] Dossier renommé en '{os.path.basename(new_folder_path)}' pour éviter tout doublon.")
    except Exception as e:
        print(f"[Avertissement] Impossible de renommer le dossier '{folder_path}': {e}")
        
    return True

def process_captures(input_dir: str):
    """
    Scanne et traite tous les sous-dossiers non traités dans input_dir ou le dossier lui-même.
    """
    if not os.path.exists(input_dir):
        print(f"Le chemin '{input_dir}' n'existe pas.")
        return

    # Si le dossier se termine par _PROCESSED
    if is_processed_folder(input_dir):
        # Si c'était un dossier explicite mais déjà traité, tenter de retirer le suffixe pour trouver si l'utilisateur pointe dessus
        pass

    has_direct_images = any(
        glob.glob(os.path.join(input_dir, ext)) 
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.PNG")
    )
    
    if has_direct_images:
        process_single_folder(input_dir)
        return

    subdirs = [
        os.path.join(input_dir, d) for d in os.listdir(input_dir) 
        if os.path.isdir(os.path.join(input_dir, d))
    ]
    subdirs = sorted(subdirs)
    
    unprocessed = [d for d in subdirs if not is_processed_folder(d)]
    
    if not unprocessed:
        print(f"Tous les dossiers dans '{input_dir}' ont déjà été traités.")
        return
        
    print(f"=== {len(unprocessed)} dossier(s) non traité(s) trouvé(s) dans '{input_dir}' ===")
    for folder in unprocessed:
        process_single_folder(folder)

if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "captures"
    process_captures(target_dir)
