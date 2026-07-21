"""
Module de conversion PDF vers Markdown et de parsing structuré pour Yoyo Chinese.
Extrait le vocabulaire et les phrases des fiches de cours PDF Yoyo Chinese,
génère un fichier Markdown intermédiaire et retourne des structures d'objets prêtes pour Anki.
"""

import os
import re
import subprocess
import unicodedata
from typing import List, Dict, Any, Tuple
import pypdf

# Plage Unicode des voyelles accentuées Pinyin
PINYIN_TONE_CHARS = "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙǕǗǙǛ"

def clean_text(text: str) -> str:
    """Nettoie et normalise le texte (supprime bruits d'impression, espaces insecables)."""
    if not text:
        return ""
    normalized = unicodedata.normalize('NFKC', text)
    cleaned = re.sub(r'[\xa0\u200b\u3000\x7f]', ' ', normalized)
    return re.sub(r'[ \t]+', ' ', cleaned).strip()

def extract_pdf_raw_lines(pdf_path: str) -> List[str]:
    """
    Extrait les lignes de texte d'un PDF Yoyo Chinese.
    Utilise `pdftotext` si disponible (pour conserver l'ordre des colonnes), sinon `pypdf`.
    """
    lines = []
    try:
        raw_out = subprocess.check_output(['pdftotext', pdf_path, '-']).decode('utf-8')
        for l in raw_out.splitlines():
            cl = clean_text(l)
            if cl:
                lines.append(cl)
    except Exception:
        reader = pypdf.PdfReader(pdf_path)
        for page in reader.pages:
            txt = page.extract_text()
            if txt:
                for l in txt.splitlines():
                    cl = clean_text(l)
                    if cl:
                        lines.append(cl)
    return lines

def is_cjk_string(s: str) -> bool:
    """Vérifie si une chaîne contient au moins un caractère chinois (Hanzi)."""
    return any('\u4e00' <= ch <= '\u9fff' for ch in s)

def is_pinyin_line(s: str) -> bool:
    """Vérifie si une ligne correspond à du Pinyin (contient des tons ou des mots Pinyin connus)."""
    if any(c in PINYIN_TONE_CHARS for c in s):
        return True
    words = s.lower().split()
    known_pinyin = {"wo", "nǐ", "ni", "ta", "ai", "hen", "hao", "ma", "ye", "dou", "bu", "ba", "de"}
    if words and all(w in known_pinyin or any(c in PINYIN_TONE_CHARS for c in w) for w in words):
        return True
    return False

def extract_simplified_hanzi(text: str) -> str:
    """
    Si le texte contient une barre oblique comme '爱/愛', extrait la première partie (Simplifié '爱').
    Si c'est du CJK pur, retourne le texte nettoyé.
    """
    if '/' in text:
        parts = text.split('/')
        first = parts[0].strip()
        if is_cjk_string(first):
            return first
    return text.strip()

def filter_simplified_cjk_list(cjk_lines: List[str]) -> List[str]:
    """
    Filtre une liste de lignes CJK alternant Simplifié/Traditionnel.
    Ne saute la ligne suivante que s'il s'agit explicitement de la version traditionnelle (même longueur).
    """
    res = []
    idx = 0
    while idx < len(cjk_lines):
        curr_raw = cjk_lines[idx]
        curr_clean = extract_simplified_hanzi(curr_raw)
        res.append(curr_clean)
        
        # Si la ligne courante contenait déjà '/' (ex: 爱/愛), la version traditionnelle était sur la même ligne
        if '/' in curr_raw:
            idx += 1
        # Si la ligne suivante existe, est CJK pur et de même longueur, c'est la ligne traditionnelle
        elif idx + 1 < len(cjk_lines):
            nxt = cjk_lines[idx + 1]
            if is_cjk_string(nxt) and '/' not in nxt and len(nxt) == len(curr_raw):
                idx += 2
            else:
                idx += 1
        else:
            idx += 1
    return res

def parse_yoyo_pdf(pdf_path: str, output_md_dir: str = "output_markdown") -> Dict[str, Any]:
    """
    Analyse un fichier PDF Yoyo Chinese et retourne la structure complète de la leçon et des cartes.
    """
    lines = extract_pdf_raw_lines(pdf_path)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    lesson_title = base_name
    for l in lines:
        if l.lower().startswith("unit ") or "lesson " in l.lower():
            lesson_title = l
            break

    # Génération du Markdown propre
    md_lines = [f"# {lesson_title}", ""]
    for l in lines:
        if l.lower() in ["vocabulary", "sentences"]:
            md_lines.append(f"\n## {l.capitalize()}\n")
        elif l in ["English", "Pinyin", "Chinese Characters"]:
            continue
        elif l != lesson_title:
            md_lines.append(l)

    md_content = "\n".join(md_lines)
    os.makedirs(output_md_dir, exist_ok=True)
    md_path = os.path.join(output_md_dir, f"{base_name}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    items = []
    
    vocab_idx = -1
    sentences_idx = -1
    for i, l in enumerate(lines):
        if l.lower() == "vocabulary":
            vocab_idx = i
        elif l.lower() == "sentences":
            sentences_idx = i

    # --- SECTION 1 : Pronoms / Verbes du tableau initial ---
    if vocab_idx > 0:
        head_lines = lines[:vocab_idx]
        eng_list = []
        pinyin_list = []
        cjk_list = []
        
        for l in head_lines:
            if l == lesson_title or l in ["English", "Pinyin", "Chinese Characters"]:
                continue
            if is_cjk_string(l):
                cjk_list.append(l)
            elif is_pinyin_line(l):
                pinyin_list.append(l)
            else:
                eng_list.append(l)

        cjk_clean = filter_simplified_cjk_list(cjk_list)
        min_len = min(len(eng_list), len(pinyin_list), len(cjk_clean))
        for i in range(min_len):
            items.append({
                "hanzi": cjk_clean[i],
                "pinyin": pinyin_list[i],
                "english": eng_list[i],
                "literal": "",
                "category": "Vocabulary",
                "lesson": lesson_title
            })

    # --- SECTION 2 : Vocabulaire ---
    if vocab_idx != -1:
        end_v = sentences_idx if sentences_idx != -1 else len(lines)
        v_lines = lines[vocab_idx + 1:end_v]
        
        eng_items = []
        pinyin_items = []
        cjk_items = []
        
        for l in v_lines:
            if is_cjk_string(l):
                cjk_items.append(l)
            elif is_pinyin_line(l):
                pinyin_items.append(l)
            else:
                eng_items.append(l)

        clean_eng = []
        i = 0
        while i < len(eng_items):
            main_eng = eng_items[i]
            lit_note = ""
            if i + 1 < len(eng_items) and "(lit" in eng_items[i+1].lower():
                lit_note = eng_items[i+1]
                i += 2
            else:
                i += 1
            clean_eng.append((main_eng, lit_note))

        cjk_clean = filter_simplified_cjk_list(cjk_items)
        min_len = min(len(clean_eng), len(pinyin_items), len(cjk_clean))
        for k in range(min_len):
            eng_val, lit_val = clean_eng[k]
            items.append({
                "hanzi": cjk_clean[k],
                "pinyin": pinyin_items[k],
                "english": eng_val,
                "literal": lit_val,
                "category": "Vocabulary",
                "lesson": lesson_title
            })

    # --- SECTION 3 : Sentences ---
    if sentences_idx != -1:
        s_lines = lines[sentences_idx + 1:]
        eng_sents = []
        pinyin_sents = []
        cjk_sents = []
        
        for l in s_lines:
            if is_cjk_string(l):
                cjk_sents.append(l)
            elif is_pinyin_line(l):
                pinyin_sents.append(l)
            else:
                eng_sents.append(l)

        cjk_clean = filter_simplified_cjk_list(cjk_sents)
        min_len = min(len(eng_sents), len(pinyin_sents), len(cjk_clean))
        for k in range(min_len):
            items.append({
                "hanzi": cjk_clean[k],
                "pinyin": pinyin_sents[k],
                "english": eng_sents[k],
                "literal": "",
                "category": "Sentence",
                "lesson": lesson_title
            })

    return {
        "lesson_title": lesson_title,
        "markdown_path": md_path,
        "markdown_content": md_content,
        "items": items
    }

if __name__ == "__main__":
    import sys
    pdf = sys.argv[1] if len(sys.argv) > 1 else "/Users/thomashusson/Documents/Projets/Docs_internat/Chinois/yoyo_chinese/Beg-Unit-001-Lesson-01-LN.pdf"
    res = parse_yoyo_pdf(pdf)
    import json
    print(json.dumps(res, indent=2, ensure_ascii=False))
