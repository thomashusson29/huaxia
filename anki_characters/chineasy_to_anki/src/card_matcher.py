"""
Module d'appariement des cartes Chineasy.
Associe chaque carte de détail (Hanzi simple ou composé, Pinyin, Explication) avec son illustration mnémotechnique.
Utilise l'appariement par mot-clé ET le secours de séquence d'images adjacentes (Image N -> Image N+1).
"""

from typing import List, Dict, Any

def match_cards(extracted_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Forme des paires entre les cartes de détail et les cartes mnémotechniques.
    """
    detail_cards = [c for c in extracted_cards if c.get("card_type") == "detail"]
    mnemonic_cards = [c for c in extracted_cards if c.get("card_type") == "mnemonic"]
    
    paired_cards = []
    used_mnemos = set()
    
    # Map d'index des images dans la liste d'origine
    file_to_index = {c.get("file_path"): idx for idx, c in enumerate(extracted_cards)}
    
    for detail in detail_cards:
        english_key = detail.get("english", "").strip().lower()
        story_key = detail.get("story", "").strip().lower()
        hanzi_key = detail.get("hanzi", "").strip()
        detail_path = detail.get("file_path", "")
        detail_idx = file_to_index.get(detail_path, -1)
        
        matched_mnemo = None
        
        # 1. Correspondance exacte sur le mot anglais
        for idx, mnemo in enumerate(mnemonic_cards):
            if idx in used_mnemos:
                continue
            mnemo_eng = mnemo.get("english", "").strip().lower()
            if english_key and mnemo_eng and (english_key == mnemo_eng):
                matched_mnemo = mnemo
                used_mnemos.add(idx)
                break
                
        # 2. Correspondance du mot mnémotechnique dans le texte de l'histoire
        if not matched_mnemo and story_key:
            for idx, mnemo in enumerate(mnemonic_cards):
                if idx in used_mnemos:
                    continue
                mnemo_eng = mnemo.get("english", "").strip().lower()
                if mnemo_eng and len(mnemo_eng) >= 2 and mnemo_eng in story_key:
                    matched_mnemo = mnemo
                    used_mnemos.add(idx)
                    if not english_key or len(english_key) <= 1:
                        detail["english"] = mnemo_eng
                    break

        # 3. Correspondance sous-chaîne
        if not matched_mnemo and english_key:
            for idx, mnemo in enumerate(mnemonic_cards):
                if idx in used_mnemos:
                    continue
                mnemo_eng = mnemo.get("english", "").strip().lower()
                if mnemo_eng and (english_key in mnemo_eng or mnemo_eng in english_key):
                    matched_mnemo = mnemo
                    used_mnemos.add(idx)
                    break

        # 4. Secours de séquence adjacente : L'image mnémotechnique précède immédiatement la carte détail (Index N-1)
        if not matched_mnemo and detail_idx > 0:
            for idx, mnemo in enumerate(mnemonic_cards):
                if idx in used_mnemos:
                    continue
                mnemo_path = mnemo.get("file_path", "")
                mnemo_idx = file_to_index.get(mnemo_path, -2)
                if mnemo_idx == detail_idx - 1:
                    matched_mnemo = mnemo
                    used_mnemos.add(idx)
                    if not english_key and mnemo.get("english"):
                        detail["english"] = mnemo.get("english")
                    break

        paired_card = {
            "hanzi": hanzi_key,
            "pinyin": detail.get("pinyin", ""),
            "english": detail.get("english", ""),
            "story": detail.get("story", ""),
            "detail_image": detail.get("file_path", ""),
            "mnemonic_image": matched_mnemo.get("file_path", "") if matched_mnemo else ""
        }
        
        paired_cards.append(paired_card)
        
    return paired_cards
