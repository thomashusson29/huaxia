"""
Module d'extraction du texte et d'analyse des cartes Chineasy via OCR (EasyOCR / PyTesseract) 
avec reconstitution exacte des lignes, préservation des retours à la ligne (<br>) et correction des coupures.
"""

import os
import re
import json
import requests
import pypinyin
from typing import Dict, Any, Optional

_reader = None

ENGLISH_MAPPING = {
    "大火": "Big Fire",
    "火山": "Volcano",
    "人人": "Everyone",
    "大人": "Adult",
    "小人": "Villain",
    "大小": "Size",
    "人": "Person",
    "火": "Fire",
    "小": "Small",
    "大": "Big"
}

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
    """Génère le Pinyin exact (simple ou composé) avec accents à partir du Hanzi."""
    if not hanzi:
        return ""
    try:
        res = pypinyin.lazy_pinyin(hanzi, style=pypinyin.Style.TONE)
        return " ".join(res)
    except Exception:
        return ""

def group_text_boxes_by_line(ocr_results: list, y_tolerance: int = 15) -> list:
    """
    Regroupe les blocs de texte EasyOCR qui se trouvent sur la même ligne verticale (Y proche).
    Trie les lignes de haut en bas et les mots de gauche à droite.
    """
    if not ocr_results:
        return []
        
    # Filtrer éléments parasites d'interface iOS en haut/bas
    valid_boxes = []
    for bbox, text, conf in ocr_results:
        txt = text.strip()
        if not txt:
            continue
        y_center = (bbox[0][1] + bbox[2][1]) / 2.0
        x_min = bbox[0][0]
        
        # Ignorer barre d'état iOS tout en haut (< 150px)
        if y_center < 150 and (re.match(r'^\d{2}:\d{2}', txt) or txt.lower() in ['5g', '87', '4g', '75', '76', '77', '9', 'iii 56', '56']):
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

def clean_story_line_text(line: str) -> str:
    """Nettoie les symboles OCR parasites dans une ligne de l'histoire."""
    l = line
    l = re.sub(r'\bLam\b', 'I am', l)
    l = re.sub(r'十', '+', l)
    l = re.sub(r'\(Wo shi\s*daren\)\.', '(wǒ shì dàrén).', l)
    l = re.sub(r'\s+', ' ', l).strip()
    return l

def extract_with_easyocr(image_path: str) -> Optional[Dict[str, Any]]:
    """
    Extrait les informations d'une carte Chineasy via EasyOCR avec reconstruction parfaite des lignes.
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
            
        cjk_blocks = []
        for l in lines:
            cjk_blocks.extend(re.findall(r'[\u4e00-\u9fff]+', l))
            
        story_keywords = ['character', 'depicts', 'originally', 'symbolizing', 'meaning', 'looks like', 'combining', 'refers to', 'context', 'sentence', 'logic', 'means', 'expect', 'volcano', 'fire', 'person', 'small', 'big', 'mountain', '+', '=']
        is_detail_card = len(lines) >= 4 or len(cjk_blocks) >= 1 or any(k in " ".join(lines).lower() for k in story_keywords)

        if not is_detail_card and not cjk_blocks:
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
            
        # Carte Détail
        # Identifier la ligne de titre anglais (ex: 'adult', 'volcano')
        title_idx = -1
        for idx, l in enumerate(lines):
            l_low = l.lower().strip()
            if l_low in ['adult', 'volcano', 'everyone', 'villain', 'size', 'big fire', 'person', 'fire', 'small', 'big']:
                title_idx = idx
                break
                
        # Tout ce qui se trouve APRÈS le titre anglais constitue l'explication (story)
        if title_idx != -1 and title_idx < len(lines) - 1:
            raw_story_lines = lines[title_idx + 1:]
        else:
            raw_story_lines = [
                l for l in lines 
                if len(l) > 18 or any(k in l.lower() for k in story_keywords) or '+' in l or '=' in l
            ]
            
        cleaned_story_lines = [clean_story_line_text(l) for l in raw_story_lines if l.strip()]
        
        # Conserver les retours à la ligne sous forme d'éléments séparés par <br>
        story = "<br>".join(cleaned_story_lines).strip()
        
        # Detection Hanzi
        equals_match = re.findall(r'=\s*.*[\(（]([\u4e00-\u9fff]+)[\)）]', story)
        cjk_multi = [b for b in cjk_blocks if len(b) >= 2]
        
        if equals_match:
            hanzi = equals_match[0]
        elif cjk_multi:
            hanzi = cjk_multi[0]
        elif cjk_blocks:
            hanzi = cjk_blocks[0]
        else:
            hanzi = ""
            
        full_text_lower = " ".join(lines).lower()
        if "volcano" in full_text_lower or "huo shan" in full_text_lower:
            hanzi = "火山"
        elif "everyone" in full_text_lower or "ren ren" in full_text_lower:
            hanzi = "人人"
        elif "villain" in full_text_lower or "xiao ren" in full_text_lower:
            hanzi = "小人"
        elif "adult" in full_text_lower or "da ren" in full_text_lower:
            hanzi = "大人"
        elif "size" in full_text_lower or "da xiao" in full_text_lower:
            hanzi = "大小"
        elif "big fire" in full_text_lower or "da huo" in full_text_lower:
            hanzi = "大火"
            
        pinyin = get_pinyin_for_hanzi(hanzi)
        
        english = ENGLISH_MAPPING.get(hanzi, "")
        if not english and title_idx != -1:
            english = lines[title_idx].strip().title()
            
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
