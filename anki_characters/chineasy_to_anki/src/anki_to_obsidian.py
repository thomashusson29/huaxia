"""
Module d'exportation de cartes Anki vers Obsidian avec mise en page "Base de Données" Markdown,
gestion du frontmatter YAML, et copie automatique des médias (images mnémoniques et audios).
"""

import os
from pathlib import Path
import re
import html
import shutil
import json
import sys
import urllib.request
from typing import List, Dict, Any, Optional

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from huaxia_tags import (  # noqa: E402
    TagContext,
    anki_to_obsidian_tag,
    build_managed_tags,
)

ANKI_CONNECT_PORTS = [8766, 8765]
DEFAULT_DECK = "chinois::chineasy_characters"
DEFAULT_OBSIDIAN_DIR = "/Users/thomashusson/Documents/Projets/Docs_internat/Chinois/caracteres"
DEFAULT_MEDIA_DIR = os.path.join(DEFAULT_OBSIDIAN_DIR, "media")
DATABASE_STEM = "00_Base_de_Donnees_Caracteres"
DATABASE_VIEW_NAME = "Tous les caractères"
_ANKI_NOTE_ID_RE = re.compile(
    r"^anki_note_id:\s*[\"']?(\d+)[\"']?\s*$",
    flags=re.MULTILINE,
)

DATABASE_BASE_CONTENT = f"""filters:
  and:
    - 'file.folder == this.file.folder'
    - 'file.ext == "md"'
    - 'file.name != "{DATABASE_STEM}.md"'
formulas:
  caractere: 'html("<strong>" + escapeHTML(hanzi) + "</strong>")'
  fiche: 'file.asLink(file.basename)'
  mnemonique: 'if(file.embeds.filter(["png", "jpg", "jpeg", "gif", "webp", "svg"].contains(value.asFile().ext.lower())).length > 0, image(file.embeds.filter(["png", "jpg", "jpeg", "gif", "webp", "svg"].contains(value.asFile().ext.lower()))[0].asFile()), "")'
  audio: 'if(file.embeds.filter(["mp3", "wav", "m4a", "ogg", "flac"].contains(value.asFile().ext.lower())).length > 0, html("<audio src=\\"media/" + file.embeds.filter(["mp3", "wav", "m4a", "ogg", "flac"].contains(value.asFile().ext.lower()))[0].asFile().name + "\\" controls style=\\"height:30px; width:130px; vertical-align:middle;\\"></audio>"), "")'
properties:
  formula.caractere:
    displayName: Caractère
  pinyin:
    displayName: Pinyin
  traduction:
    displayName: Traduction
  formula.fiche:
    displayName: Fiche Obsidian
  formula.mnemonique:
    displayName: Mnémonique
  formula.audio:
    displayName: Audio
views:
  - type: table
    name: {DATABASE_VIEW_NAME}
    order:
      - formula.caractere
      - pinyin
      - traduction
      - formula.fiche
      - formula.mnemonique
      - formula.audio
    rowHeight: tall
"""

DATABASE_MARKDOWN_CONTENT = f"""---
tags:
  - index
  - base-de-donnees
---
# 📚 Base de Données des Caractères Chineasy

![[{DATABASE_STEM}.base#{DATABASE_VIEW_NAME}]]
"""

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


def source_from_deck_name(deck_name: str) -> str:
    lowered = (deck_name or "").lower()
    if "chineasy" in lowered:
        return "chineasy"
    if "yoyo" in lowered or "ychinese" in lowered:
        return "yoyochinese"
    if "integrated chinese" in lowered:
        return "integrated_chinese"
    if "le_chinois_facile" in lowered:
        return "le_chinois_facile"
    return ""


def existing_markdown_paths_by_note_id(target_dir: str) -> Dict[str, str]:
    paths: Dict[str, str] = {}
    if not os.path.isdir(target_dir):
        return paths
    for filename in os.listdir(target_dir):
        path = os.path.join(target_dir, filename)
        if (
            filename == f"{DATABASE_STEM}.md"
            or not filename.lower().endswith(".md")
            or not os.path.isfile(path)
        ):
            continue
        with open(path, "r", encoding="utf-8") as f:
            match = _ANKI_NOTE_ID_RE.search(f.read())
        if match:
            paths[match.group(1)] = path
    return paths


def resolve_markdown_path(
    target_dir: str,
    filename_base: str,
    note_id: Any,
    existing_by_note_id: Dict[str, str],
) -> str:
    note_id_text = str(note_id)
    existing = existing_by_note_id.get(note_id_text)
    if existing:
        return existing

    preferred = os.path.join(target_dir, f"{filename_base}.md")
    if not os.path.exists(preferred):
        return preferred
    return os.path.join(
        target_dir,
        f"{filename_base}__anki_{note_id_text}.md",
    )


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
    existing_by_note_id = existing_markdown_paths_by_note_id(target_dir)

    for note in notes_info:
        fields = note.get("fields", {})
        note_id = note.get("noteId", "")
        
        # Extraction des valeurs des champs
        hanzi = fields.get("Hanzi", {}).get("value", "").strip()
        traditional = fields.get("Traditional", {}).get("value", "").strip()
        pinyin = fields.get("Pinyin", {}).get("value", "").strip()
        anglais = fields.get("Anglais", {}).get("value", "").strip()
        explication_raw = fields.get("Explication", {}).get("value", "").strip()
        img_raw = fields.get("MnemoAuto", {}).get("value", "").strip()
        if not img_raw:
            img_raw = fields.get("ImageMnemo", {}).get("value", "").strip()
        audio_raw = fields.get("Audio", {}).get("value", "").strip()

        if not hanzi and not anglais:
            continue
            
        filename_base = hanzi if hanzi else anglais
        filename_base = re.sub(r'[\\/*?:"<>|]', '_', filename_base)
        md_filepath = resolve_markdown_path(
            target_dir,
            filename_base,
            note_id,
            existing_by_note_id,
        )

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
        
        # Les tags Anki utilisent ``::`` ; Obsidian représente la même
        # hiérarchie avec ``/``.
        generated_tags = set(
            build_managed_tags(
                TagContext(
                    hanzi=hanzi,
                    traditional=traditional,
                    pinyin=pinyin,
                    source=source_from_deck_name(deck_name),
                )
            )
        )
        generated_tags.update(
            tag
            for tag in note.get("tags", [])
            if tag.startswith("chinois::")
        )
        tags_list = sorted(anki_to_obsidian_tag(tag) for tag in generated_tags)

        # Frontmatter YAML structuré (Dataview / Properties / Base de données compatible)
        yaml_lines = [
            "---",
            f'hanzi: "{hanzi}"',
            f'traditionnel: "{traditional}"',
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
        existing_by_note_id[str(note_id)] = md_filepath

    # La note maître embarque une véritable vue Obsidian Bases. La vue lit
    # directement tous les Markdown du dossier et se rafraîchit sans reconstruire
    # un tableau statique à chaque modification.
    db_index_path = os.path.join(target_dir, f"{DATABASE_STEM}.md")
    db_base_path = os.path.join(target_dir, f"{DATABASE_STEM}.base")

    base_was_missing = not os.path.exists(db_base_path)
    if base_was_missing:
        with open(db_base_path, "w", encoding="utf-8") as f:
            f.write(DATABASE_BASE_CONTENT)

    # Lors de la première migration, remplacer l'ancien tableau statique par
    # l'embed Bases. Ensuite, préserver les réglages faits dans Obsidian.
    if base_was_missing or not os.path.exists(db_index_path):
        with open(db_index_path, "w", encoding="utf-8") as f:
            f.write(DATABASE_MARKDOWN_CONTENT)

    return {
        "success": True,
        "exported_count": exported_count,
        "copied_media_count": copied_media_count,
        "target_dir": target_dir,
        "files": created_files,
        "database_index": db_index_path,
        "database_base": db_base_path
    }

if __name__ == "__main__":
    print("[Anki -> Obsidian Exporter] Lancement du traitement...")
    result = export_anki_notes_to_obsidian()
    if result["success"]:
        print(f"[Succès] {result['exported_count']} note(s) exportée(s) dans : {result['target_dir']}")
        print(f"[Médias] {result['copied_media_count']} fichier(s) média copié(s) dans le dossier media/")
    else:
        print(f"[Erreur] {result.get('error')}")
