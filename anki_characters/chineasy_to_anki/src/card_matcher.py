"""
Module d'appariement des cartes Chineasy.
Associe chaque carte de détail avec son illustration mnémotechnique.
Corrige dynamiquement et automatiquement les erreurs OCR du titre anglais en utilisant le titre propre de l'illustration.
"""

from typing import List, Dict, Any

def match_cards(extracted_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Forme des paires entre les cartes de détail et les cartes mnémotechniques,
    et applique le titre anglais propre de l'illustration pour remplacer les coquilles OCR.
    """
    detail_cards = [c for c in extracted_cards if c.get("card_type") == "detail"]
    mnemonic_cards = [c for c in extracted_cards if c.get("card_type") == "mnemonic"]
    wotd_cards = [c for c in extracted_cards if c.get("card_type") == "word_of_the_day"]
    
    paired_cards = []
    
    # 1. Cartes 'Word of the Day' combinées
    for wotd in wotd_cards:
        paired_cards.append({
            "hanzi": wotd.get("hanzi", ""),
            "pinyin": wotd.get("pinyin", ""),
            "english": wotd.get("english", ""),
            "story": wotd.get("story", ""),
            "detail_image": wotd.get("file_path", ""),
            "mnemonic_image": wotd.get("file_path", ""),
            "is_word_of_the_day": True
        })
        
    used_mnemos = set()
    file_to_index = {c.get("file_path"): idx for idx, c in enumerate(extracted_cards)}
    
    # 2. Cartes Classiques (Pairing 2 Screenshots)
    for detail in detail_cards:
        english_key = detail.get("english", "").strip().lower()
        story_key = detail.get("story", "").strip().lower()
        cjk_blocks = detail.get("cjk_blocks", [])
        hanzi_key = detail.get("hanzi", "").strip()
        detail_path = detail.get("file_path", "")
        detail_idx = file_to_index.get(detail_path, -1)
        
        matched_mnemo = None
        
        # Secours de séquence adjacente : L'illustration mnémotechnique précède immédiatement la carte détail (Index N-1)
        if detail_idx > 0:
            for idx, mnemo in enumerate(mnemonic_cards):
                if idx in used_mnemos:
                    continue
                mnemo_path = mnemo.get("file_path", "")
                mnemo_idx = file_to_index.get(mnemo_path, -2)
                if mnemo_idx == detail_idx - 1:
                    matched_mnemo = mnemo
                    used_mnemos.add(idx)
                    break

        # Correspondance par mot-clé si non trouvé par séquence
        if not matched_mnemo and english_key:
            for idx, mnemo in enumerate(mnemonic_cards):
                if idx in used_mnemos:
                    continue
                mnemo_eng = mnemo.get("english", "").strip().lower()
                if mnemo_eng and (english_key == mnemo_eng or mnemo_eng in english_key or english_key in mnemo_eng):
                    matched_mnemo = mnemo
                    used_mnemos.add(idx)
                    break
                    
        if not matched_mnemo and story_key:
            for idx, mnemo in enumerate(mnemonic_cards):
                if idx in used_mnemos:
                    continue
                mnemo_eng = mnemo.get("english", "").strip().lower()
                if mnemo_eng and len(mnemo_eng) >= 2 and mnemo_eng in story_key:
                    matched_mnemo = mnemo
                    used_mnemos.add(idx)
                    break

        # Remplacement dynamique du titre anglais par le titre propre de la carte mnémotechnique
        clean_english = matched_mnemo.get("english", "") if matched_mnemo and matched_mnemo.get("english") else detail.get("english", "")

        paired_cards.append({
            "hanzi": hanzi_key,
            "pinyin": detail.get("pinyin", ""),
            "english": clean_english.title(),
            "story": detail.get("story", ""),
            "detail_image": detail.get("file_path", ""),
            "mnemonic_image": matched_mnemo.get("file_path", "") if matched_mnemo else "",
            "is_word_of_the_day": False
        })
        
    return paired_cards
