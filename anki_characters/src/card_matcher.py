"""
Module d'appariement des cartes Chineasy.
Associe chaque carte de détail (Hanzi, Pinyin, Explication) avec son illustration mnémotechnique
en se basant sur le mot-clé anglais et le contenu de l'histoire,
indépendamment de l'ordre ou des noms de fichiers.
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
    
    for detail in detail_cards:
        english_key = detail.get("english", "").strip().lower()
        story_key = detail.get("story", "").strip().lower()
        
        matched_mnemo = None
        
        # 1. Correspondance exacte sur le mot anglais
        for idx, mnemo in enumerate(mnemonic_cards):
            if idx in used_mnemos:
                continue
            mnemo_eng = mnemo.get("english", "").strip().lower()
            if english_key and mnemo_eng == english_key:
                matched_mnemo = mnemo
                used_mnemos.add(idx)
                break
                
        # 2. Correspondance du mot mnémotechnique dans le texte de l'histoire
        if not matched_mnemo and story_key:
            for idx, mnemo in enumerate(mnemonic_cards):
                if idx in used_mnemos:
                    continue
                mnemo_eng = mnemo.get("english", "").strip().lower()
                if mnemo_eng and len(mnemo_eng) > 2 and mnemo_eng in story_key:
                    matched_mnemo = mnemo
                    used_mnemos.add(idx)
                    # Mettre à jour le titre anglais du détail s'il était manquant
                    if not english_key or len(english_key) <= 1:
                        detail["english"] = mnemo_eng
                    break

        # 3. Correspondance partielle (sous-chaîne)
        if not matched_mnemo and english_key:
            for idx, mnemo in enumerate(mnemonic_cards):
                if idx in used_mnemos:
                    continue
                mnemo_eng = mnemo.get("english", "").strip().lower()
                if (english_key in mnemo_eng or mnemo_eng in english_key) and len(mnemo_eng) > 1:
                    matched_mnemo = mnemo
                    used_mnemos.add(idx)
                    break
                    
        paired_card = {
            "hanzi": detail.get("hanzi", ""),
            "pinyin": detail.get("pinyin", ""),
            "english": detail.get("english", ""),
            "story": detail.get("story", ""),
            "detail_image": detail.get("file_path", ""),
            "mnemonic_image": matched_mnemo.get("file_path", "") if matched_mnemo else ""
        }
        
        paired_cards.append(paired_card)
        
    return paired_cards
