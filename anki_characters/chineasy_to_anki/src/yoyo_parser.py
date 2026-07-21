"""
Module de conversion PDF vers Markdown et de parsing structuré pour Yoyo Chinese.
Extrait le vocabulaire et les phrases des fiches de cours PDF Yoyo Chinese,
génère un fichier Markdown propre avec tableaux et uniquement des caractères chinois simplifiés,
génère les tags Anki appropriés (chinois, yoyochinese, unit1, lesson1, etc.)
et l'enregistre à la fois dans le dossier du PDF d'origine et dans output_markdown/.
"""

import os
import re
import subprocess
import unicodedata
import requests
from typing import List, Dict, Any, Tuple
import pypdf

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
    Ne conserve que les caractères simplifiés.
    """
    res = []
    idx = 0
    while idx < len(cjk_lines):
        curr_raw = cjk_lines[idx]
        curr_clean = extract_simplified_hanzi(curr_raw)
        res.append(curr_clean)
        
        if '/' in curr_raw:
            idx += 1
        elif idx + 1 < len(cjk_lines):
            nxt = cjk_lines[idx + 1]
            if is_cjk_string(nxt) and '/' not in nxt and len(nxt) == len(curr_raw):
                idx += 2
            else:
                idx += 1
        else:
            idx += 1
    return res

def build_tags_for_yoyo_item(lesson_title: str, base_filename: str, category: str) -> List[str]:
    """
    Génère une liste de tags Anki propres et hiérarchisés pour un élément Yoyo Chinese.
    Exemples de tags : ['chinois', 'yoyochinese', 'unit1', 'lesson1', 'vocabulary']
    """
    tags = ["chinois", "yoyochinese"]
    
    full_text = f"{lesson_title} {base_filename}".lower()
    
    m_unit = re.search(r'unit[-_\s]*(\d+)', full_text)
    if m_unit:
        tags.append(f"unit{int(m_unit.group(1))}")
        
    m_lesson = re.search(r'lesson[-_\s]*(\d+)', full_text)
    if m_lesson:
        tags.append(f"lesson{int(m_lesson.group(1))}")

    if category:
        tags.append(category.lower())

    return list(dict.fromkeys(tags)) # Éliminer les doublons éventuels

def generate_clean_markdown(lesson_title: str, items: List[Dict[str, Any]]) -> str:
    """
    Génère un document Markdown propre avec des tableaux comparatifs (Vocabulaire et Phrases)
    en utilisant EXCLUSIVEMENT des caractères chinois simplifiés.
    """
    md = [f"# {lesson_title}\n"]
    
    vocab_items = [it for it in items if it.get("category") == "Vocabulary"]
    sentence_items = [it for it in items if it.get("category") == "Sentence"]
    
    if vocab_items:
        md.append("## Vocabulaire\n")
        md.append("| Anglais | Pinyin | Caractère Simplifié | Sens Littéral / Remarques |")
        md.append("| :--- | :--- | :---: | :--- |")
        for v in vocab_items:
            eng = v.get("english", "").replace("|", "\\|")
            pinyin = v.get("pinyin", "").replace("|", "\\|")
            hanzi = v.get("hanzi", "").replace("|", "\\|")
            literal = v.get("literal", "").replace("|", "\\|")
            md.append(f"| {eng} | {pinyin} | {hanzi} | {literal} |")
        md.append("")
        
    if sentence_items:
        md.append("## Phrases d'exemple (Sentences)\n")
        md.append("| Anglais | Pinyin | Phrase Simplifiée |")
        md.append("| :--- | :--- | :---: |")
        for s in sentence_items:
            eng = s.get("english", "").replace("|", "\\|")
            pinyin = s.get("pinyin", "").replace("|", "\\|")
            hanzi = s.get("hanzi", "").replace("|", "\\|")
            md.append(f"| {eng} | {pinyin} | {hanzi} |")
        md.append("")
        
    return "\n".join(md)

def enhance_with_ollama(markdown_content: str, model_name: str = "qwen2.5-coder:latest") -> str:
    """
    Tente de faire relire/embellir le Markdown via Ollama Qwen local si disponible.
    """
    try:
        prompt = f"""Tu es un assistant linguistique expert en mandarin.
Voici le document Markdown extrait d'une fiche de cours PDF :

{markdown_content}

Consignes STRICTES :
1. Conserve TOUS les mots et phrases du tableau.
2. Assure-toi que les caractères chinois sont 100% SIMPLIFIÉS (aucun caractère traditionnel).
3. Ne réponds QU'AVEC le code Markdown formaté, sans aucun commentaire ou texte d'introduction.
"""
        res = requests.post("http://localhost:11434/api/generate", json={
            "model": model_name,
            "prompt": prompt,
            "stream": False
        }, timeout=15)
        if res.status_code == 200:
            resp_text = res.json().get("response", "").strip()
            resp_text = re.sub(r'^```markdown\s*', '', resp_text)
            resp_text = re.sub(r'^```\s*', '', resp_text)
            resp_text = re.sub(r'\s*```$', '', resp_text)
            if resp_text and "| Caractère Simplifié |" in resp_text:
                return resp_text
    except Exception as e:
        print(f"[Ollama Warning] Ollama non disponible ({e}), utilisation du Markdown généré.")
    return markdown_content

def parse_yoyo_pdf(pdf_path: str, output_md_dir: str = "output_markdown", use_ollama: bool = True) -> Dict[str, Any]:
    """
    Analyse un fichier PDF Yoyo Chinese, génère des tableaux Markdown avec caractères simplifiés uniques,
    construit les tags Anki appropriés et enregistre le document Markdown.
    """
    lines = extract_pdf_raw_lines(pdf_path)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    pdf_dir = os.path.dirname(os.path.abspath(pdf_path))
    
    lesson_title = base_name
    for l in lines:
        if l.lower().startswith("unit ") or "lesson " in l.lower():
            lesson_title = l
            break

    items = []
    vocab_idx = -1
    sentences_idx = -1
    for i, l in enumerate(lines):
        if l.lower() == "vocabulary":
            vocab_idx = i
        elif l.lower() == "sentences":
            sentences_idx = i

    # Section 1 : Pronoms / Verbes
    if vocab_idx > 0:
        head_lines = lines[:vocab_idx]
        eng_list, pinyin_list, cjk_list = [], [], []
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
            item_tags = build_tags_for_yoyo_item(lesson_title, base_name, "Vocabulary")
            items.append({
                "hanzi": cjk_clean[i],
                "pinyin": pinyin_list[i],
                "english": eng_list[i],
                "literal": "",
                "category": "Vocabulary",
                "lesson": lesson_title,
                "tags": item_tags
            })

    # Section 2 : Vocabulaire
    if vocab_idx != -1:
        end_v = sentences_idx if sentences_idx != -1 else len(lines)
        v_lines = lines[vocab_idx + 1:end_v]
        eng_items, pinyin_items, cjk_items = [], [], []
        
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
            item_tags = build_tags_for_yoyo_item(lesson_title, base_name, "Vocabulary")
            items.append({
                "hanzi": cjk_clean[k],
                "pinyin": pinyin_items[k],
                "english": eng_val,
                "literal": lit_val,
                "category": "Vocabulary",
                "lesson": lesson_title,
                "tags": item_tags
            })

    # Section 3 : Sentences
    if sentences_idx != -1:
        s_lines = lines[sentences_idx + 1:]
        eng_sents, pinyin_sents, cjk_sents = [], [], []
        
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
            item_tags = build_tags_for_yoyo_item(lesson_title, base_name, "Sentence")
            items.append({
                "hanzi": cjk_clean[k],
                "pinyin": pinyin_sents[k],
                "english": eng_sents[k],
                "literal": "",
                "category": "Sentence",
                "lesson": lesson_title,
                "tags": item_tags
            })

    # Générer le document Markdown avec tableaux
    md_content = generate_clean_markdown(lesson_title, items)
    if use_ollama:
        md_content = enhance_with_ollama(md_content)

    # 1. Sauvegarder dans output_markdown/
    os.makedirs(output_md_dir, exist_ok=True)
    md_path_output = os.path.join(output_md_dir, f"{base_name}.md")
    with open(md_path_output, "w", encoding="utf-8") as f:
        f.write(md_content)

    # 2. Sauvegarder directement à côté du fichier PDF d'origine
    md_path_pdf_dir = os.path.join(pdf_dir, f"{base_name}.md")
    try:
        with open(md_path_pdf_dir, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"[Yoyo Parser] Markdown sauvegardé à côté du PDF : {md_path_pdf_dir}")
    except Exception as e_save:
        print(f"[Yoyo Parser Warning] Écriture dans le dossier PDF d'origine ignorée ({e_save})")

    return {
        "lesson_title": lesson_title,
        "markdown_path": md_path_output,
        "pdf_dir_markdown_path": md_path_pdf_dir,
        "markdown_content": md_content,
        "items": items
    }

if __name__ == "__main__":
    import sys
    pdf = sys.argv[1] if len(sys.argv) > 1 else "/Users/thomashusson/Documents/Projets/Docs_internat/Chinois/yoyo_chinese/Beg-Unit-001-Lesson-01-LN.pdf"
    res = parse_yoyo_pdf(pdf)
    import json
    print(json.dumps(res, indent=2, ensure_ascii=False))
