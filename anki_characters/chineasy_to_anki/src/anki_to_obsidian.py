"""
Module d'exportation de cartes Anki vers Obsidian avec mise en page "Base de Données" Markdown,
gestion du frontmatter YAML, et copie automatique des médias (images mnémoniques et audios).
"""

import os
import re
import html
import shutil
import json
import urllib.request
from typing import List, Dict, Any, Optional

ANKI_CONNECT_PORTS = [8766, 8765]
DEFAULT_DECK = "chinois::chineasy_characters"
DEFAULT_OBSIDIAN_DIR = "/Users/thomashusson/Documents/Projets/Docs_internat/Chinois/caracteres"
DEFAULT_MEDIA_DIR = os.path.join(DEFAULT_OBSIDIAN_DIR, "media")

# Recherche de dossiers média locaux fallback au cas où
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOCAL_MEDIA_SEARCH_DIRS = [
    os.path.join(PROJECT_ROOT, "output_media"),
    os.path.join(PROJECT_ROOT, "output_audio"),
    os.path.join(PROJECT_ROOT, "captures"),
    os.path.join(PROJECT_ROOT, "..")
]

def get_active_ankiconnect_url() -> str:
    for port in ANKI_CONNECT_PORTS:
        url = f"http://127.0.0.1:{port}"
        try:
            req = urllib.request.Request(
                url,
                json.dumps({"action": "version", "version": 6}).encode("utf-8")
            )
            with urllib.request.urlopen(req, timeout=2) as res:
                data = json.loads(res.read().decode("utf-8"))
                if data.get("result") is not None:
                    return url
        except Exception:
            continue
    return ""

def invoke_ankiconnect(action: str, **params) -> Any:
    url = get_active_ankiconnect_url()
    if not url:
        raise Exception("AnkiConnect n'est pas disponible (Anki doit être ouvert avec AnkiConnect).")
        
    payload = {"action": action, "version": 6, "params": params}
    req = urllib.request.Request(url, json.dumps(payload).encode("utf-8"))
    with urllib.request.urlopen(req, timeout=10) as response:
        res = json.loads(response.read().decode("utf-8"))
        if res.get("error"):
            raise Exception(res.get("error"))
        return res.get("result")

def clean_html_to_markdown(html_str: str) -> str:
    """Nettoie une chaîne HTML pour la convertir en Markdown lisible."""
    if not html_str:
        return ""
    
    # Remplacer les balises <br> et </p> par des retours à la ligne
    text = re.sub(r'<br\s*/?>', '\n', html_str, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '', text, flags=re.IGNORECASE)
    
    # Enlever les autres balises HTML résiduelles sauf le texte
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    
    # Nettoyer les espaces multiples et retours à la ligne consécutifs
    lines = [line.strip() for line in text.split('\n')]
    cleaned = '\n'.join(lines)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()

def locate_media_file(filename: str, anki_media_dir: Optional[str] = None) -> Optional[str]:
    """Cherche un fichier média dans le dossier Anki ou les dossiers projet locaux."""
    if not filename:
        return None
        
    filename = filename.strip()
    
    # 1. Vérifier dans le dossier média d'Anki s'il est connu
    if anki_media_dir and os.path.exists(anki_media_dir):
        path_in_anki = os.path.join(anki_media_dir, filename)
        if os.path.exists(path_in_anki):
            return path_in_anki
            
    # 2. Rechercher dans le profil utilisateur Anki standard mac
    user_home = os.path.expanduser("~")
    anki2_base = os.path.join(user_home, "Library/Application Support/Anki2")
    if os.path.exists(anki2_base):
        for root, dirs, files in os.walk(anki2_base):
            if "collection.media" in root and filename in files:
                return os.path.join(root, filename)

    # 3. Recherche dans les dossiers média du projet local
    for s_dir in LOCAL_MEDIA_SEARCH_DIRS:
        if os.path.exists(s_dir):
            for root, dirs, files in os.walk(s_dir):
                if filename in files:
                    return os.path.join(root, filename)
                    
    return None

def export_anki_notes_to_obsidian(
    deck_name: str = DEFAULT_DECK,
    target_dir: str = DEFAULT_OBSIDIAN_DIR,
    media_dir: str = DEFAULT_MEDIA_DIR
) -> Dict[str, Any]:
    """
    Exporte toutes les notes d'un deck Anki vers Obsidian sous forme de fiches Markdown individuelles.
    """
    os.makedirs(target_dir, exist_ok=True)
    os.makedirs(media_dir, exist_ok=True)

    url = get_active_ankiconnect_url()
    if not url:
        return {"success": False, "error": "AnkiConnect non disponible. Assurez-vous qu'Anki est démarré.", "exported_count": 0}

    # Récupérer le dossier média Anki si possible
    anki_media_dir = None
    try:
        anki_media_dir = invoke_ankiconnect("getMediaFolderPath")
    except Exception:
        pass

    # Récupérer les notes
    query = f'deck:"{deck_name}"'
    note_ids = invoke_ankiconnect("findNotes", query=query)
    if not note_ids:
        # Fallback recherche globale si le deck exacte a un format légèrement différent
        query = 'deck:*chineasy*'
        note_ids = invoke_ankiconnect("findNotes", query=query)
        
    if not note_ids:
        return {"success": True, "message": f"Aucune note trouvée pour le deck {deck_name}", "exported_count": 0}

    notes_info = invoke_ankiconnect("notesInfo", notes=note_ids)
    exported_count = 0
    copied_media_count = 0
    created_files = []

    for note in notes_info:
        fields = note.get("fields", {})
        note_id = note.get("noteId", "")
        
        # Extraction des valeurs des champs
        hanzi = fields.get("Hanzi", {}).get("value", "").strip()
        pinyin = fields.get("Pinyin", {}).get("value", "").strip()
        anglais = fields.get("Anglais", {}).get("value", "").strip()
        explication_raw = fields.get("Explication", {}).get("value", "").strip()
        img_raw = fields.get("ImageMnemo", {}).get("value", "").strip()
        audio_raw = fields.get("Audio", {}).get("value", "").strip()

        if not hanzi and not anglais:
            continue
            
        filename_base = hanzi if hanzi else anglais
        filename_base = re.sub(r'[\\/*?:"<>|]', '_', filename_base)
        md_filepath = os.path.join(target_dir, f"{filename_base}.md")

        # Extraction du nom d'image
        img_filename = None
        img_match = re.search(r'src=["\']([^"\']+)["\']', img_raw)
        if img_match:
            img_filename = img_match.group(1)

        # Extraction du nom d'audio
        audio_filename = None
        audio_match = re.search(r'\[sound:([^\]]+)\]', audio_raw)
        if audio_match:
            audio_filename = audio_match.group(1)

        # Copie de l'image mnémonique (largeur max 370px dans Obsidian)
        obs_img_link = ""
        if img_filename:
            src_path = locate_media_file(img_filename, anki_media_dir)
            if src_path and os.path.exists(src_path):
                dest_path = os.path.join(media_dir, img_filename)
                shutil.copy2(src_path, dest_path)
                copied_media_count += 1
            obs_img_link = f"![[{img_filename}|370]]"

        # Copie de l'audio
        obs_audio_link = ""
        if audio_filename:
            src_path = locate_media_file(audio_filename, anki_media_dir)
            if src_path and os.path.exists(src_path):
                dest_path = os.path.join(media_dir, audio_filename)
                shutil.copy2(src_path, dest_path)
                copied_media_count += 1
            obs_audio_link = f"![[{audio_filename}]]"

        explication_clean = clean_html_to_markdown(explication_raw)

        # Extraction des caractères chinois individuel pour les vues reliées (Backlinks & Tags)
        individual_chars = list(dict.fromkeys(re.findall(r'[\u4e00-\u9fff]', hanzi)))
        component_links = [f'"[[{char}]]"' for char in individual_chars]
        
        # Tags enrichis avec les caractères chinois
        tags_list = ["chinois", "chineasy", "caractere"]
        if hanzi:
            tags_list.append(f"caractere/{hanzi}")
            for char in individual_chars:
                if char not in tags_list and char != hanzi:
                    tags_list.append(f"racine/{char}")

        # Frontmatter YAML structuré (Dataview / Properties / Base de données compatible)
        yaml_lines = [
            "---",
            f'hanzi: "{hanzi}"',
            f'pinyin: "{pinyin}"',
            f'traduction: "{anglais}"',
            f'deck: "{deck_name}"',
            f'anki_note_id: {note_id}',
            "tags:"
        ]
        for tag in tags_list:
            yaml_lines.append(f'  - "{tag}"')
            
        if component_links:
            yaml_lines.append("composants:")
            for clink in component_links:
                yaml_lines.append(f'  - {clink}')
                
        yaml_lines.extend(["---", ""])

        # Structure du corps Markdown
        header_title = f"# {hanzi}" if hanzi else f"# {anglais}"
        if pinyin and anglais:
            header_title += f" ({pinyin}) — {anglais}"

        body_lines = [header_title, ""]

        if explication_clean:
            body_lines.append("> [!info] Explication & Histoire")
            for line in explication_clean.split('\n'):
                body_lines.append(f"> {line}" if line else ">")
            body_lines.append("")

        # Section pour les liaisons graphiques Obsidian (Liés)
        if len(individual_chars) > 0:
            char_items = [
                f'<a class="internal-link" href="{char}" style="font-size: 26px; text-decoration: none !important; border-bottom: none !important; display: inline-block; margin-right: 12px;">{char}</a>'
                for char in individual_chars if char != hanzi
            ]
            if char_items:
                rel_links = " ".join(char_items)
                body_lines.extend(["## Caractères reliés", rel_links, ""])

        if obs_img_link:
            body_lines.extend(["## Mnémonique", obs_img_link, ""])

        if obs_audio_link:
            body_lines.extend(["## Audio", obs_audio_link, ""])

        full_md_content = "\n".join(yaml_lines) + "\n".join(body_lines)

        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(full_md_content)

        exported_count += 1
        created_files.append(md_filepath)

    # Création / Mise à jour de la note maître Base de Données globale
    db_index_path = os.path.join(target_dir, "00_Base_de_Donnees_Caracteres.md")
    db_content_lines = [
        "---",
        "tags:",
        "  - index",
        "  - base-de-donnees",
        "---",
        "# 📚 Base de Données des Caractères Chineasy",
        "",
        "| Caractère | Pinyin | Traduction | Fiche Obsidian | Mnémonique | Audio |",
        "| :---: | :--- | :--- | :---: | :---: | :---: |"
    ]

    for note in notes_info:
        fields = note.get("fields", {})
        h = fields.get("Hanzi", {}).get("value", "").strip()
        p = fields.get("Pinyin", {}).get("value", "").strip()
        a = fields.get("Anglais", {}).get("value", "").strip()
        img_raw = fields.get("ImageMnemo", {}).get("value", "").strip()
        audio_raw = fields.get("Audio", {}).get("value", "").strip()
        
        if not h:
            continue

        img_match = re.search(r'src=["\']([^"\']+)["\']', img_raw)
        img_name = img_match.group(1) if img_match else ""
        img_cell = f'<img src="media/{img_name}" width="80" style="border-radius:4px;">' if img_name else "-"

        audio_match = re.search(r'\[sound:([^\]]+)\]', audio_raw)
        audio_name = audio_match.group(1) if audio_match else ""
        audio_cell = f'<audio src="media/{audio_name}" controls style="height:30px; width:130px; vertical-align:middle;"></audio>' if audio_name else "-"

        link_cell = f'<a class="internal-link" href="{h}" style="text-decoration:none !important; border-bottom:none !important; font-size:18px; font-weight:bold;">{h}</a>'

        db_content_lines.append(f"| **{h}** | {p} | {a} | {link_cell} | {img_cell} | {audio_cell} |")

    with open(db_index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(db_content_lines))

    return {
        "success": True,
        "exported_count": exported_count,
        "copied_media_count": copied_media_count,
        "target_dir": target_dir,
        "files": created_files,
        "database_index": db_index_path
    }

if __name__ == "__main__":
    print("[Anki -> Obsidian Exporter] Lancement du traitement...")
    result = export_anki_notes_to_obsidian()
    if result["success"]:
        print(f"[Succès] {result['exported_count']} note(s) exportée(s) dans : {result['target_dir']}")
        print(f"[Médias] {result['copied_media_count']} fichier(s) média copié(s) dans le dossier media/")
    else:
        print(f"[Erreur] {result.get('error')}")
