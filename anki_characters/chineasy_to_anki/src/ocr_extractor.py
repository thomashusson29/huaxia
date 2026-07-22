"""
Module d'extraction du texte et d'analyse des cartes Chineasy via OCR (EasyOCR).
Accélération matérielle forcée sur Apple Silicon MPS (Metal Performance Shaders).
Extraction 100% DYNAMIQUE et automatique avec détection automatique 'Word of the Day'
et auto-correction des coquilles OCR (Pinyin, Hanzi, Anglais).
"""

import os
import re
import json
import torch
import pypinyin
import unicodedata
from typing import Dict, Any, Optional, List, Tuple

# Activer l'accélération matérielle Apple Silicon (MPS) & PyTorch Fallback
if torch.backends.mps.is_available():
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

_reader = None

def get_easyocr_reader():
    global _reader
    if _reader is None:
        try:
            import easyocr
            if torch.backends.mps.is_available():
                print("[OCR] Accélération matérielle activée sur : APPLE SILICON (MPS GPU)")
                _reader = easyocr.Reader(['ch_sim', 'en'], gpu=True)
            elif torch.cuda.is_available():
                print("[OCR] Accélération matérielle activée sur : NVIDIA CUDA GPU")
                _reader = easyocr.Reader(['ch_sim', 'en'], gpu=True)
            else:
                print("[OCR] Exécution sur CPU")
                _reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        except Exception as e:
            print(f"[OCR] Repli sur CPU (Erreur initialisation GPU: {e})")
            import easyocr
            _reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
    return _reader

def is_cjk_char(ch: str) -> bool:
    """Vérifie si un caractère est un Hanzi CJK."""
    return '\u4e00' <= ch <= '\u9fff'

def get_pinyin_for_hanzi(hanzi: str) -> str:
    """Génère automatiquement le Pinyin exact avec accents pour n'importe quel Hanzi."""
    if not hanzi:
        return ""
    try:
        res = pypinyin.lazy_pinyin(hanzi, style=pypinyin.Style.TONE)
        return " ".join(res)
    except Exception:
        return ""

CONCEPT_REFERENCE_MAP = {
    'sun': ('日', 'rì', 'Sun'),
    'day': ('日', 'rì', 'Sun'),
    'moon': ('月', 'yuè', 'Moon / Month'),
    'month': ('月', 'yuè', 'Moon / Month'),
    'moon/month': ('月', 'yuè', 'Moon / Month'),
    'yue': ('月', 'yuè', 'Moon / Month'),
    'dusk': ('夕', 'xī', 'Dusk / Evening'),
    'evening': ('夕', 'xī', 'Dusk / Evening'),
    'dusk/evening': ('夕', 'xī', 'Dusk / Evening'),
    'xi': ('夕', 'xī', 'Dusk / Evening'),
    'xt': ('夕', 'xī', 'Dusk / Evening'),
    'water': ('水', 'shuǐ', 'Water'),
    'shui': ('水', 'shuǐ', 'Water'),
    'tree': ('木', 'mù', 'Tree'),
    'wood': ('木', 'mù', 'Tree'),
    'mu': ('木', 'mù', 'Tree'),
    'sky': ('天', 'tiān', 'Sky'),
    'heaven': ('天', 'tiān', 'Sky'),
    'tian': ('天', 'tiān', 'Sky'),
    'fire': ('火', 'huǒ', 'Fire'),
    'huo': ('火', 'huǒ', 'Fire'),
    'person': ('人', 'rén', 'Person'),
    'ren': ('人', 'rén', 'Person'),
    'mouth': ('口', 'kǒu', 'Mouth'),
    'kou': ('口', 'kǒu', 'Mouth'),
    'door': ('门', 'mén', 'Door'),
    'men': ('门', 'mén', 'Door'),
    'woman': ('女', 'nǚ', 'Woman'),
    'nv': ('女', 'nǚ', 'Woman'),
    'mountain': ('山', 'shān', 'Mountain'),
    'shan': ('山', 'shān', 'Mountain'),
    'volcano': ('火山', 'huǒ shān', 'Volcano'),
    'big': ('大', 'dà', 'Big'),
    'da': ('大', 'dà', 'Big'),
    'adult': ('大人', 'dà rén', 'Adult')
}

def clean_ocr_text_line(text: str) -> str:
    """Nettoie les scories OCR fréquentes."""
    if not text:
        return ""
    text = re.sub(r'[\xa0\u200b\u3000\x7f]', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text).strip()
    replacements = {
        r'\bLam\b': 'I am',
        r'\bchuild\b': 'child',
        r'\brchild\b': 'child',
        r'\'"': '"',
        r'"\'': '"',
        r'’': "'",
        r'”': '"',
        r'“': '"'
    }
    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text)
    return text

def extract_card_info(image_path: str) -> Dict[str, Any]:
    """
    Extrait dynamiquement les informations d'une capture d'écran Chineasy via EasyOCR sur GPU MPS.
    Supporte la détection automatique 'Word of the Day' et le filtrage des bruits d'interface iOS.
    """
    reader = get_easyocr_reader()
    if not reader:
        return {
            "file_path": image_path,
            "card_type": "mnemonic",
            "hanzi": "", "pinyin": "", "english": "", "story": ""
        }
        
    try:
        raw_results = reader.readtext(image_path, detail=1)
        if not raw_results:
            return {
                "file_path": image_path,
                "card_type": "mnemonic",
                "hanzi": "", "pinyin": "", "english": "", "story": ""
            }

        valid_lines = []
        for bbox, text, prob in raw_results:
            ymin = int(min(pt[1] for pt in bbox))
            txt = text.strip()
            if not txt:
                continue
            if ymin < 140 and (re.match(r'^\d{1,2}:\d{2}', txt) or any(k in txt.lower() for k in ['5g', '4g', 'lte', 'wi-fi', '68', '75', '76', 'ii56', '411156'])):
                continue
            if 'siri' in txt.lower() or 'show me' in txt.lower() or 'added to' in txt.lower():
                continue
            valid_lines.append((ymin, txt, prob))

        valid_lines.sort(key=lambda x: x[0])
        full_text = " ".join(t for _, t, _ in valid_lines)
        full_text_lower = full_text.lower()

        # Détection automatique "Word of the Day"
        is_word_of_the_day = bool(
            re.search(r'word\s*of\s*the\s*day', full_text_lower) or 
            'wordoftheday' in full_text_lower or 
            'ofthe day' in full_text_lower or
            'word of' in full_text_lower
        )

        joined_text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', full_text)
        cjk_blocks = re.findall(r'[\u4e00-\u9fff]+', joined_text)

        # --- CAS 1 : Carte combinée "Word of the Day" ---
        if is_word_of_the_day:
            raw_hanzi = cjk_blocks[0] if cjk_blocks else ""
            
            english = ""
            pinyin = ""
            for _, t, _ in valid_lines:
                m = re.search(r'([A-Za-z\s/]+)\s*\(([^)]+)\)', t)
                if m:
                    candidate_eng = m.group(1).strip()
                    candidate_pinyin = m.group(2).strip()
                    if candidate_eng.lower() not in ['word of the day', 'word of']:
                        english = candidate_eng.title()
                        pinyin = candidate_pinyin.lower()
                        break
                        
            if not english:
                for _, t, _ in valid_lines:
                    t_clean = re.sub(r'[^a-zA-Z\s/]', '', t).strip().lower()
                    if t_clean and t_clean not in ['word of the day', 'word of', 'to siri', 'a']:
                        for key, (h_map, p_map, e_map) in CONCEPT_REFERENCE_MAP.items():
                            if key in t_clean.split():
                                english = e_map
                                if not raw_hanzi: raw_hanzi = h_map
                                pinyin = p_map
                                break
                    if english: break

            if raw_hanzi and (not english or english.lower() in ['to siri', 'siri']):
                for key, (h_map, p_map, e_map) in CONCEPT_REFERENCE_MAP.items():
                    if raw_hanzi == h_map:
                        english = e_map
                        pinyin = p_map
                        break

            if not pinyin and raw_hanzi:
                pinyin = get_pinyin_for_hanzi(raw_hanzi)

            story_lines = []
            for y, t, _ in valid_lines:
                t_clean = clean_ocr_text_line(t)
                if y < 1450: continue
                if any(k in t_clean.lower() for k in ['word of', 'wordoftheday', 'ofthe day']): continue
                if t_clean == raw_hanzi or (english and english.lower() in t_clean.lower()): continue
                story_lines.append(t_clean)
                
            story = "<br>".join(story_lines).strip()

            return {
                "file_path": image_path,
                "card_type": "word_of_the_day",
                "hanzi": raw_hanzi,
                "pinyin": pinyin,
                "english": english if english else "Word of the Day",
                "story": story,
                "is_combined": True
            }

        # --- CAS 2 : Cartes Classiques Chineasy ---
        story_lines = [t for y, t, _ in valid_lines if y > 1750]
        story_text = " ".join(story_lines)
        
        is_detail_card = len(story_text) > 20 or len(cjk_blocks) > 0 or any('=' in t or '+' in t for _, t, _ in valid_lines)

        # Mnemonic card (Illustration seule)
        if not is_detail_card or len(story_text) == 0:
            english = ""
            for y, t, _ in valid_lines:
                if y > 1200:
                    t_clean = re.sub(r'[^a-zA-Z\s/]', '', t).strip().lower()
                    for key, (h_map, p_map, e_map) in CONCEPT_REFERENCE_MAP.items():
                        if key in t_clean.split():
                            english = e_map
                            break
                    if english: break
                    if len(t_clean) >= 2:
                        english = t.strip().title()
                        
            return {
                "file_path": image_path,
                "card_type": "mnemonic",
                "hanzi": "",
                "pinyin": "",
                "english": english,
                "story": ""
            }

        # Detail card (Fiche lexicographique)
        english = ""
        pinyin = ""
        raw_hanzi = ""

        # Détecter le mot-clé d'abord
        for y, t, _ in valid_lines:
            if 1400 <= y <= 1950:
                t_clean = re.sub(r'[^a-zA-Z\s/]', '', t).strip().lower()
                for key, (h_map, p_map, e_map) in CONCEPT_REFERENCE_MAP.items():
                    if key in t_clean.split():
                        english = e_map
                        raw_hanzi = h_map
                        pinyin = p_map
                        break
                if english: break

        # Vérification si le Hanzi est mentionné dans la story
        if not raw_hanzi:
            for key, (h_map, p_map, e_map) in CONCEPT_REFERENCE_MAP.items():
                if h_map in story_text or e_map.lower() in story_text.lower():
                    raw_hanzi = h_map
                    english = e_map
                    pinyin = p_map
                    break

        if not raw_hanzi and cjk_blocks:
            raw_hanzi = cjk_blocks[0]

        if not english:
            for y, t, _ in valid_lines:
                if 1400 <= y <= 1950 and re.match(r'^[a-zA-Z\s/]{2,20}$', t.strip()):
                    english = t.strip().title()
                    break

        if not pinyin and raw_hanzi:
            pinyin = get_pinyin_for_hanzi(raw_hanzi)

        formatted_story = "<br>".join([clean_ocr_text_line(t) for t in story_lines]).strip()

        return {
            "file_path": image_path,
            "card_type": "detail",
            "hanzi": raw_hanzi,
            "pinyin": pinyin,
            "english": english,
            "story": formatted_story
        }

    except Exception as e:
        print(f"[OCR Erreur] {e}")
        return {
            "file_path": image_path,
            "card_type": "mnemonic",
            "hanzi": "", "pinyin": "", "english": "", "story": ""
        }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(extract_card_info(sys.argv[1]), indent=2, ensure_ascii=False))
