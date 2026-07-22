"""
Module d'appariement intelligent des cartes Chineasy.
Forme des paires parfaites entre les cartes de détail et leurs illustrations mnémotechniques 
par correspondance de mots-clés (Anglais, Hanzi, Pinyin) indépendamment de l'ordre de capture.
Prend en charge les cartes combinées 'Word of the Day'.
"""

import os
import re
from typing import List, Dict, Any

def normalize_key(text: str) -> str:
    """Normalise un texte pour la comparaison de mots-clés."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return " ".join(text.split())

def match_cards(extracted_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Associe de manière optimale chaque carte de détail à sa carte mnémotechnique correspondante.
    """
    wotd_cards = [c for c in extracted_cards if c.get("card_type") == "word_of_the_day"]
    detail_cards = [c for c in extracted_cards if c.get("card_type") == "detail"]
    mnemonic_cards = [c for c in extracted_cards if c.get("card_type") == "mnemonic"]
    
    paired_cards = []
    
    # 1. Cartes 'Word of the Day' combinées
    for wotd in wotd_cards:
        paired_cards.append({
            "hanzi": wotd.get("hanzi", ""),
            "pinyin": wotd.get("pinyin", ""),
            "english": wotd.get("english", "").title(),
            "story": wotd.get("story", ""),
            "detail_image": wotd.get("file_path", ""),
            "mnemonic_image": wotd.get("file_path", ""),
            "is_word_of_the_day": True
        })

    used_mnemos = set()
    file_to_index = {c.get("file_path"): idx for idx, c in enumerate(extracted_cards)}

    # 2. Cartes Classiques : Appariement par Mot-Clé (Keyword-First)
    for detail in detail_cards:
        d_eng = normalize_key(detail.get("english", ""))
        d_hanzi = detail.get("hanzi", "").strip()
        d_pinyin = normalize_key(detail.get("pinyin", ""))
        d_story = normalize_key(detail.get("story", ""))
        detail_path = detail.get("file_path", "")
        detail_idx = file_to_index.get(detail_path, -1)

        best_mnemo = None
        best_score = -1
        best_mnemo_idx = -1

        for idx, mnemo in enumerate(mnemonic_cards):
            if idx in used_mnemos:
                continue
            
            m_eng = normalize_key(mnemo.get("english", ""))
            mnemo_path = mnemo.get("file_path", "")
            mnemo_idx = file_to_index.get(mnemo_path, -2)
            
            score = 0
            
            # Match exact sur le mot anglais
            if d_eng and m_eng and d_eng == m_eng:
                score += 100
            # Match partiel sur le mot anglais (ex: 'sun' dans 'sun', 'moon' dans 'moon month')
            elif d_eng and m_eng and (d_eng in m_eng or m_eng in d_eng):
                score += 70
            # Match du mot anglais de l'illustration dans l'histoire de la carte détail
            elif m_eng and len(m_eng) >= 3 and m_eng in d_story:
                score += 50

            # Adjacence séquentielle (bonus de proximité si captures successives N-1)
            if detail_idx >= 0 and mnemo_idx == detail_idx - 1:
                score += 15
            elif detail_idx >= 0 and mnemo_idx == detail_idx + 1:
                score += 10

            if score > best_score and score >= 40:
                best_score = score
                best_mnemo = mnemo
                best_mnemo_idx = idx

        if best_mnemo:
            used_mnemos.add(best_mnemo_idx)
        else:
            # Secours si aucun mot-clé n'a correspondu : chercher l'image mnémotechnique adjacente (N-1)
            for idx, mnemo in enumerate(mnemonic_cards):
                if idx in used_mnemos:
                    continue
                mnemo_path = mnemo.get("file_path", "")
                mnemo_idx = file_to_index.get(mnemo_path, -2)
                if detail_idx >= 0 and mnemo_idx == detail_idx - 1:
                    best_mnemo = mnemo
                    used_mnemos.add(idx)
                    break

        clean_english = best_mnemo.get("english", "") if best_mnemo and best_mnemo.get("english") else detail.get("english", "")
        if not clean_english:
            clean_english = detail.get("english", "")

        paired_cards.append({
            "hanzi": d_hanzi,
            "pinyin": detail.get("pinyin", ""),
            "english": clean_english.title(),
            "story": detail.get("story", ""),
            "detail_image": detail_path,
            "mnemonic_image": best_mnemo.get("file_path", "") if best_mnemo else "",
            "is_word_of_the_day": False
        })

    return paired_cards
