"""
Module d'extraction du texte et d'analyse des cartes Chineasy via OCR (EasyOCR / PyTesseract) 
avec génération exacte du Pinyin via pypinyin et classification robuste des cartes.
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
    """Génère le Pinyin exact avec accents à partir du Hanzi."""
    if not hanzi or not is_cjk_char(hanzi[0]):
        return ""
    try:
        res = pypinyin.lazy_pinyin(hanzi[0], style=pypinyin.Style.TONE)
        return res[0] if res else ""
    except Exception:
        return ""

def extract_with_easyocr(image_path: str) -> Optional[Dict[str, Any]]:
    """
    Extrait les informations d'une carte Chineasy via EasyOCR.
    Distingue fermement les cartes de détail (présence d'un texte d'histoire)
    et les cartes mnémotechniques (illustration + mot simple).
    """
    reader = get_easyocr_reader()
    if not reader:
        return None
        
    try:
        results = reader.readtext(image_path, detail=0)
        if not results:
            return None
            
        lines = [line.strip() for line in results if line.strip()]
        
        # Filtrer la barre d'état iOS (20:43, 5G, 87, etc.)
        cleaned_lines = [
            l for l in lines 
            if not re.match(r'^\d{2}:\d{2}', l) and l.lower() not in ['5g', '87', '4g', '5g']
        ]
        
        # Identifier les lignes constituant une explication/histoire
        story_lines = []
        for line in cleaned_lines:
            if len(line) > 20 or any(k in line.lower() for k in ['character', 'depicts', 'originally', 'symbolizing', 'meaning', 'looks like']):
                story_lines.append(line)
                
        story = " ".join(story_lines).strip()
        
        # RÈGLE D'OR : Une carte est un DÉTAIL SSI elle possède un paragraphe d'explication d'au moins 20 caractères
        is_detail_card = len(story) >= 20
        
        if not is_detail_card:
            # Carte Mnémotechnique
            english_candidates = [
                l.lower() for l in cleaned_lines 
                if re.match(r'^[a-zA-Z\s]+$', l) and len(l) <= 20
            ]
            english = english_candidates[0] if english_candidates else ""
            return {
                "card_type": "mnemonic",
                "hanzi": "",
                "pinyin": "",
                "english": english,
                "story": ""
            }
            
        # Carte Détail
        # 1. Extraction du Hanzi (en haut ou dans l'histoire)
        cjk_chars = [c for line in cleaned_lines for c in line if is_cjk_char(c)]
        hanzi = cjk_chars[0] if cjk_chars else ""
        if not hanzi and story:
            story_cjk = [c for c in story if is_cjk_char(c)]
            if story_cjk:
                hanzi = story_cjk[0]
                
        # 2. Pinyin exact via pypinyin
        pinyin = get_pinyin_for_hanzi(hanzi)
        
        # 3. Extraction du titre anglais
        possible_english = [
            l.lower() for l in cleaned_lines 
            if re.match(r'^[a-zA-Z\s]+$', l) and len(l) <= 15 and l not in story_lines
        ]
        
        # Filtrer le pinyin sans accents des mots anglais potentiels
        pinyin_normal = pypinyin.lazy_pinyin(hanzi[0], style=pypinyin.Style.NORMAL)[0] if hanzi else ""
        english_candidates = [w for w in possible_english if w != pinyin_normal and len(w) > 1]
        
        english = english_candidates[0] if english_candidates else (possible_english[0] if possible_english else "")
        
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

def extract_with_ollama_vision(image_path: str, model_name: str = "llama3.2-vision") -> Optional[Dict[str, Any]]:
    """
    Fallback d'extraction avec un modèle de vision local via Ollama.
    """
    try:
        import base64
        with open(image_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")
            
        prompt = """Analyze this Chineasy card image and respond ONLY with a JSON object.
Do not include any Markdown codeblocks or extra text.

Return JSON in this format:
{
  "card_type": "detail" or "mnemonic",
  "hanzi": "single Chinese character if detail card, else empty string",
  "pinyin": "pinyin with tone mark if detail card, else empty string",
  "english": "the English translation word (e.g. person, fire, small, big)",
  "story": "the full English explanation text at the bottom if detail card, else empty string"
}
"""
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "images": [b64_image],
                "stream": False
            },
            timeout=30
        )
        if response.status_code == 200:
            res_text = response.json().get("response", "")
            cleaned = re.sub(r'```json\s*', '', res_text)
            cleaned = re.sub(r'```\s*$', '', cleaned).strip()
            data = json.loads(cleaned)
            if data.get("hanzi") and not data.get("pinyin"):
                data["pinyin"] = get_pinyin_for_hanzi(data["hanzi"])
            return data
    except Exception as e:
        print(f"[Ollama] Secours Ollama non exécuté ou erreur: {e}")
    return None

def extract_card_info(image_path: str) -> Dict[str, Any]:
    """
    Extrait les données d'une carte en essayant l'OCR Python puis Ollama si incomplet.
    """
    res = extract_with_easyocr(image_path)
    
    is_valid_detail = res and res.get("card_type") == "detail" and res.get("hanzi")
    is_valid_mnemo = res and res.get("card_type") == "mnemonic" and res.get("english")
    
    if not (is_valid_detail or is_valid_mnemo):
        print(f"[OCR] Résultat incomplet pour {os.path.basename(image_path)}, tentative via Ollama...")
        ollama_res = extract_with_ollama_vision(image_path)
        if ollama_res:
            res = ollama_res

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
