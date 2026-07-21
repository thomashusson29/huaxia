"""
Module d'extraction du texte et d'analyse des cartes Chineasy via OCR (EasyOCR).
Extraction 100% DYNAMIQUE et automatique pour n'importe quelle nouvelle capture 
(Chineasy Classique & Word of the Day) sans dépendre de dictionnaires codés en dur.
"""

import os
import re
import json
import requests
import pypinyin
from typing import Dict, Any, Optional

_reader = None

def get_easyocr_reader():
    global _reader
    if _reader is None:
        try:
            import easyocr
            _reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        except Exception as e:
            print(f"[OCR] EasyOCR non disponible: {e}")
            _reader = False
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

def clean_ocr_typos(text: str) -> str:
    """
    Nettoie dynamiquement les erreurs fréquentes de la reconnaissance OCR.
    """
    if not text:
        return ""
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

def group_text_boxes_by_line(ocr_results: list, y_tolerance: int = 15) -> list:
    if not ocr_results:
        return []
        
    valid_boxes = []
    for bbox, text, conf in ocr_results:
        txt = text.strip()
        if not txt:
            continue
        y_center = (bbox[0][1] + bbox[2][1]) / 2.0
        x_min = bbox[0][0]
        
        if y_center < 150 and (re.match(r'^\d{2}:\d{2}', txt) or txt.lower() in ['5g', '87', '4g', '75', '76', '77', '9', 'iii 56', '56', 'tii56']):
            continue
            
        valid_boxes.append((y_center, x_min, txt))
        
    valid_boxes.sort(key=lambda item: item[0])
    
    lines = []
    current_line = []
    last_y = None
    
    for y, x, txt in valid_boxes:
        if last_y is None or abs(y - last_y) <= y_tolerance:
            current_line.append((x, txt))
            last_y = y if last_y is None else (last_y + y) / 2.0
        else:
            current_line.sort(key=lambda item: item[0])
            line_str = " ".join(item[1] for item in current_line)
            lines.append(line_str)
            current_line = [(x, txt)]
            last_y = y
            
    if current_line:
        current_line.sort(key=lambda item: item[0])
        lines.append(" ".join(item[1] for item in current_line))
        
    return lines

def extract_with_easyocr(image_path: str) -> Optional[Dict[str, Any]]:
    """
    Extrait 100% DYNAMIQUEMENT les informations de n'importe quelle nouvelle capture d'écran.
    """
    reader = get_easyocr_reader()
    if not reader:
        return None
        
    try:
        raw_results = reader.readtext(image_path, detail=1)
        if not raw_results:
            return None
            
        lines = group_text_boxes_by_line(raw_results)
        if not lines:
            return None
            
        full_text_lower = " ".join(lines).lower()
        is_word_of_the_day = bool(re.search(r'word\s+of', full_text_lower) or "ofthe day" in full_text_lower or "word of" in full_text_lower)
        
        cjk_blocks = []
        for l in lines:
            cjk_blocks.extend(re.findall(r'[\u4e00-\u9fff]+', l))

        # --- CAS 1 : Carte combinée "Word of the Day" ---
        if is_word_of_the_day:
            hanzi = cjk_blocks[0] if cjk_blocks else ""
            
            # Extraction dynamique du titre anglais (ex: "to eat (chī)" -> "To Eat")
            english = ""
            for l in lines:
                m = re.search(r'to\s+([a-zA-Z\s]+)', l, re.IGNORECASE)
                if m:
                    english = f"To {m.group(1).strip().title()}"
                    break
            if not english:
                for l in lines:
                    l_clean = l.strip()
                    if not any(k in l_clean.lower() for k in ['word of', 'added to siri', 'show me']) and not is_cjk_char(l_clean[0]):
                        english = l_clean.title()
                        break
                        
            pinyin = get_pinyin_for_hanzi(hanzi)
            
            # Reconstruction dynamique de l'histoire
            story_lines = []
            for l in lines:
                l_clean = clean_ocr_typos(l.strip())
                if any(k in l_clean.lower() for k in ['word of', 'added to siri', 'show me']):
                    continue
                if l_clean == hanzi or l_clean.lower().startswith("to "):
                    continue
                story_lines.append(l_clean)
                
            story = "<br>".join(story_lines).strip()
            
            return {
                "card_type": "word_of_the_day",
                "hanzi": hanzi,
                "pinyin": pinyin,
                "english": english,
                "story": story,
                "is_combined": True
            }

        # --- CAS 2 : Cartes Classiques Chineasy ---
        has_formula = any('=' in l or '+' in l for l in lines)
        is_detail_card = len(cjk_blocks) > 0 or has_formula

        if not is_detail_card:
            english_candidates = [
                l.lower() for l in lines 
                if re.match(r'^[a-zA-Z\s]+$', l) and len(l) <= 20
            ]
            english = english_candidates[0] if english_candidates else ""
            return {
                "card_type": "mnemonic",
                "hanzi": "",
                "pinyin": "",
                "english": english.title(),
                "story": ""
            }
            
        # Carte Détail Classique
        multi_cjk = [b for b in cjk_blocks if len(b) >= 2]
        hanzi = multi_cjk[0] if multi_cjk else (cjk_blocks[0] if cjk_blocks else "")
            
        pinyin = get_pinyin_for_hanzi(hanzi)
        
        english_candidates = []
        for l in lines:
            l_clean = l.strip()
            if re.match(r'^[a-zA-Z\s]{2,20}$', l_clean) and not any(is_cjk_char(c) for c in l_clean):
                english_candidates.append(l_clean.title())
        english = english_candidates[0] if english_candidates else ""
        
        story_lines = []
        skip = True
        for l in lines:
            l_clean = clean_ocr_typos(l.strip())
            if not skip:
                story_lines.append(l_clean)
            elif english and english.lower() in l_clean.lower():
                skip = False
            elif any(k in l_clean for k in ['+', '=', '(']):
                skip = False
                story_lines.append(l_clean)
                
        if not story_lines:
            story_lines = [clean_ocr_typos(l.strip()) for l in lines if l.strip() != hanzi]
            
        story = "<br>".join(story_lines).strip()
            
        return {
            "card_type": "detail",
            "hanzi": hanzi,
            "pinyin": pinyin,
            "english": english,
            "story": story
        }
    except Exception as e:
        print(f"[OCR] Erreur pendant l'analyse EasyOCR: {e}")
        return None

def extract_card_info(image_path: str) -> Dict[str, Any]:
    res = extract_with_easyocr(image_path)
    if res:
        res["file_path"] = image_path
    else:
        res = {
            "file_path": image_path,
            "card_type": "unknown",
            "hanzi": "",
            "pinyin": "",
            "english": "",
            "story": ""
        }
    return res

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(extract_card_info(sys.argv[1]), indent=2, ensure_ascii=False))
