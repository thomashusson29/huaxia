"""
Script principal d'automatisation Chineasy vers Anki.
Scanne les dossiers de captures, extrait les textes, détoure les images mnémotechniques,
apparie les cartes et synchronise le tout vers Anki.
"""

import os
import glob
import sys
from typing import List

# Ajout du dossier courant au path Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ocr_extractor import extract_card_info
from src.image_processor import remove_background
from src.card_matcher import match_cards
from src.anki_exporter import export_to_anki

def process_captures(input_dir: str, output_media_dir: str = "output_media", apkg_output: str = "Chineasy.apkg"):
    """
    Exécute le pipeline complet de traitement.
    """
    print(f"=== Scan du dossier de captures : {input_dir} ===")
    
    # 1. Recherche de toutes les images (.jpg, .jpeg, .png, .PNG)
    extensions = ("*.jpg", "*.jpeg", "*.png", "*.PNG")
    image_paths = []
    for ext in extensions:
        image_paths.extend(glob.glob(os.path.join(input_dir, "**", ext), recursive=True))
        
    image_paths = sorted(list(set(image_paths)))
    print(f"[1/5] {len(image_paths)} images trouvées.")
    if not image_paths:
        print("Aucune image trouvée. Vérifiez le chemin spécifié.")
        return

    # 2. Extraction OCR & Métadonnées
    print("[2/5] Extraction du texte et analyse du type de carte (OCR / Vision)...")
    extracted_cards = []
    for idx, path in enumerate(image_paths, 1):
        print(f"  ({idx}/{len(image_paths)}) Analyse de {os.path.basename(path)}...")
        info = extract_card_info(path)
        extracted_cards.append(info)

    # 3. Appariement intelligent des cartes
    print("[3/5] Appariement des cartes de détail et mnémotechniques...")
    paired_cards = match_cards(extracted_cards)
    print(f"  -> {len(paired_cards)} cartes complètes associées.")

    # 4. Traitement d'image & Détourage transparent
    print("[4/5] Détourage transparent des images mnémotechniques...")
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
                print(f"  [OK] Détourage généré : {out_name}")
            except Exception as e:
                print(f"  [Erreur] Échec du détourage pour {mnemo_img}: {e}")
                card["processed_mnemonic_image"] = mnemo_img

    # Résumé dans la console
    print("\n--- RÉSUMÉ DES CARTES CRÉÉES ---")
    for idx, card in enumerate(paired_cards, 1):
        print(f"{idx}. {card.get('hanzi')} | Pinyin: {card.get('pinyin')} | Anglais: {card.get('english')}")
        print(f"   Explication: {card.get('story')[:60]}...")
        print(f"   Image détourée: {card.get('processed_mnemonic_image')}\n")

    # 5. Exportation Anki
    print("[5/5] Exportation vers Anki...")
    export_to_anki(paired_cards, apkg_output_path=apkg_output)
    print("\n=== Traitement terminé avec succès ! ===")

if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "captures"
    process_captures(target_dir)
