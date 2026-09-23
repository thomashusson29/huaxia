from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
import uuid
from urllib.parse import unquote

from anki.cards import Card
from anki.notes import Note
from anki.sound import AVTag, SoundOrVideoTag
from aqt import gui_hooks, mw
from aqt.editor import Editor
from aqt.qt import (
    QAction,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
    qconnect,
)
from aqt.utils import askUser, showInfo, showWarning

from .core import (
    COMPONENT_TAG_PREFIX,
    MnemonicEntry,
    RenderResult,
    enhanced_cloze_audio_counts,
    extract_cjk,
    library_tag,
    media_filename_from_src,
    normalize_key,
    note_matches,
    render_mnemo_auto,
    source_content,
    unique_cjk,
    validate_entry,
)


TARGET_MODEL = "Yoyo Chinese Model v2-41f05"
SOURCE_DECK = "chinois::chineasy_characters"
LIBRARY_DECK = "chinois::mnemonics"
LIBRARY_MODEL = "Huaxia Mnémotechnique v1"
OLD_FIELD = "ImageMnemo"
TARGET_FIELD = "MnemoAuto"
ENHANCED_CLOZE_MODEL = "Enhanced Cloze 2.1 v2"
ENHANCED_CLOZE_CONTENT_FIELD = "Content"
LIBRARY_FIELDS = (
    "MnemoId",
    "TypeLien",
    "Cle",
    "Contenu",
    "Description",
    "Source",
)

SYNC_CSS_START = "/* HUAXIA_MNEMO_SYNC_CSS_START */"
SYNC_CSS = f"""
{SYNC_CSS_START}
.huaxia-mnemo-auto {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
    width: 100%;
    margin: 14px auto 0;
}}
.huaxia-mnemo-item {{
    min-width: 0;
    padding: 10px;
    border: 1px solid rgba(100, 116, 139, 0.24);
    border-radius: 12px;
    background: rgba(248, 250, 252, 0.62);
}}
.nightMode .huaxia-mnemo-item,
.night_mode .huaxia-mnemo-item {{
    border-color: rgba(148, 163, 184, 0.28);
    background: rgba(30, 34, 39, 0.7);
}}
.huaxia-mnemo-content img {{
    display: block;
    max-width: 100%;
    max-height: 260px;
    width: auto;
    height: auto;
    margin: 0 auto;
    object-fit: contain;
}}
.huaxia-mnemo-description {{
    margin-top: 8px;
    color: #64748b;
    font-size: 13px;
    line-height: 1.4;
    text-align: center;
}}
.nightMode .huaxia-mnemo-description,
.night_mode .huaxia-mnemo-description {{
    color: #abb2bf;
}}
/* HUAXIA_MNEMO_SYNC_CSS_END */
"""


@dataclass(frozen=True)
class PendingMnemonic:
    link_type: str
    key: str
    description: str
    media_name: str


IMAGE_SELECTION_TRACKER_JS = """
(() => {
    window.huaxiaSelectedImageSrc = null;
    if (window.huaxiaImageSelectionTrackerInstalled) {
        return;
    }
    document.addEventListener("pointerdown", (event) => {
        const image = event.composedPath().find(
            (node) => node instanceof HTMLImageElement
        );
        if (!image || !image.closest(
            '[contenteditable]:not([contenteditable="false"])'
        )) {
            return;
        }
        const source = image.getAttribute("src") || "";
        window.huaxiaSelectedImageSrc = source;
        pycmd(
            "huaxia_mnemo_image_selected:"
            + encodeURIComponent(source)
        );
    }, true);
    window.huaxiaImageSelectionTrackerInstalled = true;
})();
"""


def _standard_button(name: str):
    return getattr(QDialogButtonBox.StandardButton, name)


def _message_button(name: str):
    return getattr(QMessageBox.StandardButton, name)


class AddMnemonicDialog(QDialog):
    def __init__(
        self,
        note: Note,
        media_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.note = note
        self.media_name = media_name
        self.hanzi = note["Hanzi"] if "Hanzi" in note else ""
        self.traditional = note["Traditional"] if "Traditional" in note else ""

        self.setWindowTitle("Ajouter une mnémotechnique liée")
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        context = QLabel(
            "Texte chinois détecté : "
            f"{self.hanzi or '—'}"
            + (f" / {self.traditional}" if self.traditional else "")
        )
        context.setWordWrap(True)
        root.addWidget(context)

        form = QFormLayout()
        self.link_type = QComboBox()
        self.link_type.addItem("Caractère ou séquence visible", "caractere")
        self.link_type.addItem("Mot ou séquence", "mot")
        self.link_type.addItem("Composant explicite", "composant")
        form.addRow("Association obligatoire", self.link_type)

        self.key = QComboBox()
        self.key.setEditable(True)
        form.addRow("Clé chinoise", self.key)

        self.description = QPlainTextEdit()
        self.description.setPlaceholderText("Description courte obligatoire")
        self.description.setMaximumHeight(90)
        form.addRow("Description", self.description)
        root.addLayout(form)

        image_status = QLabel(f"Image sélectionnée dans l’éditeur : {media_name}")
        image_status.setWordWrap(True)
        root.addWidget(image_status)

        buttons = QDialogButtonBox(
            _standard_button("Ok") | _standard_button("Cancel")
        )
        qconnect(buttons.accepted, self._validate_and_accept)
        qconnect(buttons.rejected, self.reject)
        root.addWidget(buttons)

        qconnect(self.link_type.currentIndexChanged, self._populate_keys)
        self._populate_keys()

    def _populate_keys(self, *_args: object) -> None:
        current = self.key.currentText().strip()
        link_type = self.link_type.currentData()
        self.key.clear()

        if link_type == "caractere":
            full_values = tuple(
                value
                for value in (
                    normalize_key(self.hanzi),
                    normalize_key(self.traditional),
                )
                if value
            )
            values = tuple(
                dict.fromkeys(
                    (*full_values, *unique_cjk(f"{self.hanzi}{self.traditional}"))
                )
            )
        elif link_type == "mot":
            values = tuple(
                dict.fromkeys(
                    value
                    for value in (
                        normalize_key(self.hanzi),
                        normalize_key(self.traditional),
                    )
                    if value
                )
            )
        else:
            values = ()

        self.key.addItems(list(values))
        if current and current in values:
            self.key.setCurrentText(current)

    def _validate_and_accept(self) -> None:
        link_type = str(self.link_type.currentData())
        key = normalize_key(self.key.currentText())
        description = self.description.toPlainText().strip()

        if not description:
            showWarning("Une description courte est obligatoire.", parent=self)
            return

        preview_entry = MnemonicEntry(
            mnemonic_id="preview",
            link_type=link_type,
            key=key,
            content=(
                '<img class="mnemo-img" '
                f'src="{escape(self.media_name, quote=True)}">'
            ),
            description=description,
            source="manuel",
        )
        try:
            validate_entry(preview_entry)
        except ValueError as error:
            showWarning(str(error), parent=self)
            return

        if link_type in {"caractere", "mot"}:
            target_values = (
                normalize_key(self.hanzi),
                normalize_key(self.traditional),
            )
            if not any(key in value for value in target_values if value):
                showWarning(
                    "La clé liée doit apparaître dans Hanzi ou Traditional.",
                    parent=self,
                )
                return
        self.accept()

    def pending(self) -> PendingMnemonic:
        return PendingMnemonic(
            link_type=str(self.link_type.currentData()),
            key=normalize_key(self.key.currentText()),
            description=self.description.toPlainText().strip(),
            media_name=self.media_name,
        )


def _model_name(note: Note) -> str:
    return str(note.note_type().get("name", ""))


def _is_migrated() -> bool:
    model = mw.col.models.by_name(TARGET_MODEL)
    if not model:
        return False
    fields = mw.col.models.field_map(model)
    return TARGET_FIELD in fields and OLD_FIELD not in fields


def _ensure_library() -> None:
    model = mw.col.models.by_name(LIBRARY_MODEL)
    if not model:
        model = mw.col.models.new(LIBRARY_MODEL)
        for field_name in LIBRARY_FIELDS:
            mw.col.models.add_field(model, mw.col.models.new_field(field_name))
        template = mw.col.models.new_template("Bibliothèque")
        template["qfmt"] = (
            '<div style="font-size:42px">{{Cle}}</div>'
            "<div>{{TypeLien}}</div>"
        )
        template["afmt"] = (
            "{{FrontSide}}<hr id=answer>"
            "<div>{{Contenu}}</div>"
            "<div>{{Description}}</div>"
            "<div>{{Source}}</div>"
        )
        mw.col.models.add_template(model, template)
        mw.col.models.add(model)
    else:
        actual = tuple(name for name, _ in sorted(
            mw.col.models.field_map(model).items(),
            key=lambda item: item[1][0],
        ))
        if actual != LIBRARY_FIELDS:
            raise RuntimeError(
                f"Le type de note '{LIBRARY_MODEL}' possède un schéma inattendu : "
                f"{actual!r}."
            )
    mw.col.decks.id(LIBRARY_DECK)


def _replace_template_field_references(model: dict) -> bool:
    changed = False
    for template in model["tmpls"]:
        for side in ("qfmt", "afmt"):
            original = template[side]
            updated = original.replace(OLD_FIELD, TARGET_FIELD)
            if updated != original:
                template[side] = updated
                changed = True
    if SYNC_CSS_START not in model.get("css", ""):
        model["css"] = f"{model.get('css', '').rstrip()}\n\n{SYNC_CSS.strip()}\n"
        changed = True
    return changed


def migrate_collection() -> None:
    model = mw.col.models.by_name(TARGET_MODEL)
    if not model:
        showWarning(f"Le modèle '{TARGET_MODEL}' est introuvable.")
        return

    fields = mw.col.models.field_map(model)
    if OLD_FIELD in fields and TARGET_FIELD in fields:
        showWarning(
            f"Les champs '{OLD_FIELD}' et '{TARGET_FIELD}' existent tous les deux. "
            "La migration est interrompue pour éviter toute perte."
        )
        return
    if OLD_FIELD not in fields and TARGET_FIELD not in fields:
        showWarning(
            f"Le modèle ne contient ni '{OLD_FIELD}' ni '{TARGET_FIELD}'."
        )
        return

    if not askUser(
        "Anki va créer une sauvegarde, renommer ImageMnemo en MnemoAuto, "
        "adapter les gabarits du modèle Yoyo et créer la bibliothèque centrale. "
        "Continuer ?"
    ):
        return

    try:
        mw.create_backup_now()
        changed = False
        if OLD_FIELD in fields:
            field = fields[OLD_FIELD][1]
            mw.col.models.rename_field(model, field, TARGET_FIELD)
            changed = True
        changed = _replace_template_field_references(model) or changed
        if changed:
            mw.col.models.save(model)
        _ensure_library()
        mw.reset()
    except Exception as error:
        showWarning(f"Migration interrompue : {error}")
        return

    showInfo(
        "Migration terminée. Le contenu existant a été conservé dans MnemoAuto "
        "et aucune note n’a été synchronisée globalement."
    )


def _source_note_ids() -> set[int]:
    return set(mw.col.find_notes(f'deck:"{SOURCE_DECK}"'))


def _library_entries() -> tuple[list[MnemonicEntry], list[str]]:
    entries: list[MnemonicEntry] = []
    warnings: list[str] = []

    for note_id in mw.col.find_notes(f'note:"{LIBRARY_MODEL}"'):
        note = mw.col.get_note(note_id)
        entry = MnemonicEntry(
            mnemonic_id=note["MnemoId"].strip(),
            link_type=note["TypeLien"].strip(),
            key=normalize_key(note["Cle"]),
            content=note["Contenu"],
            description=note["Description"].strip(),
            source=note["Source"].strip(),
        )
        try:
            validate_entry(entry)
        except ValueError as error:
            warnings.append(f"Note de bibliothèque {note_id} ignorée : {error}")
            continue
        entries.append(entry)

    for note_id in sorted(_source_note_ids()):
        note = mw.col.get_note(note_id)
        if _model_name(note) != TARGET_MODEL or TARGET_FIELD not in note:
            continue
        key = normalize_key(note["Hanzi"])
        content = source_content(note[TARGET_FIELD])
        if not key or not content:
            continue
        link_type = "caractere" if len(extract_cjk(key)) == 1 else "mot"
        entry = MnemonicEntry(
            mnemonic_id=f"chineasy-{note_id}",
            link_type=link_type,
            key=key,
            content=content,
            description=note["Anglais"].strip(),
            source="chineasy",
        )
        try:
            validate_entry(entry)
        except ValueError as error:
            warnings.append(f"Note ChinEasy {note_id} ignorée : {error}")
            continue
        entries.append(entry)

    entries.sort(key=lambda item: (item.key, item.link_type, item.mnemonic_id))
    return entries, warnings


def _target_note_ids() -> list[int]:
    ids = mw.col.find_notes(f'note:"{TARGET_MODEL}"')
    return [int(note_id) for note_id in ids]


def _matching_entries(note: Note, entries: list[MnemonicEntry]) -> list[MnemonicEntry]:
    hanzi = note["Hanzi"] if "Hanzi" in note else ""
    traditional = note["Traditional"] if "Traditional" in note else ""
    return [
        entry
        for entry in entries
        if note_matches(entry, hanzi, traditional, note.tags, note.id)
    ]


def _render_note(note: Note, entries: list[MnemonicEntry]) -> tuple[list[MnemonicEntry], RenderResult]:
    if TARGET_FIELD not in note:
        raise RuntimeError(f"La note ne contient pas le champ {TARGET_FIELD}.")
    matches = _matching_entries(note, entries)
    return matches, render_mnemo_auto(note[TARGET_FIELD], matches)


def _preview_text(
    note: Note,
    matches: list[MnemonicEntry],
    result: RenderResult,
    warning_count: int = 0,
) -> str:
    keys = ", ".join(
        f"{entry.key} ({entry.link_type})" for entry in matches
    ) or "aucune"
    changed = result.html != note[TARGET_FIELD]
    return (
        f"Note : {note['Hanzi'] or note.id}\n"
        f"Associations trouvées : {keys}\n"
        f"Mnémotechniques ajoutées : {len(result.included_ids)}\n"
        f"Doublons évités : {len(result.skipped_ids)}\n"
        f"Avertissements de bibliothèque : {warning_count}\n"
        f"Le champ serait modifié : {'oui' if changed else 'non'}"
    )


def preview_note(note: Note) -> tuple[list[MnemonicEntry], RenderResult, list[str]]:
    if not _is_migrated():
        raise RuntimeError("La migration ImageMnemo → MnemoAuto doit être effectuée.")
    if _model_name(note) != TARGET_MODEL:
        raise RuntimeError("La note courante n’utilise pas le modèle Yoyo ciblé.")

    entries, warnings = _library_entries()
    matches, result = _render_note(note, entries)
    return matches, result, warnings


def preview_current_note(note: Note | None = None) -> None:
    note = note or _reviewer_note()
    if not note:
        showWarning("Aucune note Yoyo n’est actuellement ouverte.")
        return
    try:
        matches, result, warnings = preview_note(note)
    except Exception as error:
        showWarning(str(error))
        return
    message = _preview_text(note, matches, result, len(warnings))
    if warnings:
        message += "\n\n" + "\n".join(warnings[:5])
    showInfo(message)


def apply_current_note(note: Note | None = None) -> None:
    note = note or _reviewer_note()
    if not note:
        showWarning("Aucune note Yoyo n’est actuellement ouverte.")
        return
    try:
        matches, result, warnings = preview_note(note)
    except Exception as error:
        showWarning(str(error))
        return

    message = _preview_text(note, matches, result, len(warnings))
    if result.html == note[TARGET_FIELD]:
        showInfo(f"{message}\n\nAucune écriture n’est nécessaire.")
        return
    if not askUser(f"{message}\n\nAppliquer uniquement à cette note ?"):
        return

    note[TARGET_FIELD] = result.html
    mw.col.update_note(note)
    mw.reset()
    showInfo("La synchronisation a été appliquée uniquement à cette note.")


def _reviewer_note() -> Note | None:
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None)
    return card.note() if card else None


def _selected_media_name(selection: object) -> str:
    if isinstance(selection, str):
        source = selection
    elif isinstance(selection, dict) and isinstance(selection.get("src"), str):
        source = selection["src"]
    else:
        return ""
    media_name = media_filename_from_src(source)
    if not media_name:
        return ""
    if not (Path(mw.col.media.dir()) / media_name).is_file():
        return ""
    return media_name


def _create_library_note(entry: MnemonicEntry) -> int:
    _ensure_library()
    model = mw.col.models.by_name(LIBRARY_MODEL)
    if not model:
        raise RuntimeError("Impossible de créer le type de note de bibliothèque.")
    note = mw.col.new_note(model)
    note["MnemoId"] = entry.mnemonic_id
    note["TypeLien"] = entry.link_type
    note["Cle"] = entry.key
    note["Contenu"] = entry.content
    note["Description"] = entry.description
    note["Source"] = entry.source
    note.tags = [library_tag(entry.link_type, entry.key)]
    deck_id = mw.col.decks.id(LIBRARY_DECK)
    mw.col.add_note(note, deck_id)
    return int(note.id)


def _affected_note_ids(entry: MnemonicEntry, current_note: Note) -> list[int]:
    affected: list[int] = []
    component_tag = f"{COMPONENT_TAG_PREFIX}{entry.key}"
    for note_id in _target_note_ids():
        note = current_note if note_id == current_note.id else mw.col.get_note(note_id)
        tags = list(note.tags)
        if (
            entry.link_type == "composant"
            and note_id == current_note.id
            and component_tag not in tags
        ):
            tags.append(component_tag)
        if note_matches(
            entry,
            note["Hanzi"] if "Hanzi" in note else "",
            note["Traditional"] if "Traditional" in note else "",
            tags,
        ):
            affected.append(note_id)
    return affected


def add_mnemonic_from_editor(editor: Editor) -> None:
    note = editor.note
    if not note or not note.id:
        showWarning("La note doit être enregistrée avant l’ajout.")
        return
    if not _is_migrated():
        showWarning(
            "Lancez d’abord Outils → Huaxia Mnémotechniques → "
            "Initialiser / migrer."
        )
        return
    if _model_name(note) != TARGET_MODEL:
        showWarning("Ce bouton est réservé au modèle Yoyo ciblé par cette version.")
        return
    if not editor.web:
        showWarning("L’éditeur Anki n’est pas disponible.", parent=editor.widget)
        return

    media_name = _selected_media_name(
        getattr(editor, "_huaxia_selected_image_src", "")
    )
    if not media_name:
        showWarning(
            "Cliquez d’abord sur une image déjà présente dans un champ de "
            "cette note, puis cliquez sur 🧠+.",
            parent=editor.widget,
        )
        return
    _add_mnemonic_with_media(editor, note, media_name)


def _add_mnemonic_with_media(
    editor: Editor,
    note: Note,
    media_name: str,
) -> None:
    dialog = AddMnemonicDialog(note, media_name, editor.widget)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    pending = dialog.pending()
    mnemonic_id = f"manual-{uuid.uuid4().hex}"
    content = (
        '<img class="mnemo-img" '
        f'src="{escape(pending.media_name, quote=True)}">'
    )
    preview_entry = MnemonicEntry(
        mnemonic_id=mnemonic_id,
        link_type=pending.link_type,
        key=pending.key,
        content=content,
        description=pending.description,
        source="manuel",
    )
    affected = _affected_note_ids(preview_entry, note)
    component_note = (
        "\nLa note courante recevra aussi le tag explicite "
        f"{COMPONENT_TAG_PREFIX}{pending.key}."
        if pending.link_type == "composant"
        else ""
    )
    if not askUser(
        f"Association : {pending.key} ({pending.link_type})\n"
        f"Notes correspondantes : {len(affected)}\n"
        "Mode essai : seule la note courante sera mise à jour maintenant."
        f"{component_note}\n\n"
        "Créer la mnémotechnique et appliquer à cette note ?",
        parent=editor.widget,
    ):
        return

    try:
        entry = MnemonicEntry(
            mnemonic_id=mnemonic_id,
            link_type=pending.link_type,
            key=pending.key,
            content=content,
            description=pending.description,
            source="manuel",
        )
        validate_entry(entry)
        _create_library_note(entry)

        if entry.link_type == "composant":
            component_tag = f"{COMPONENT_TAG_PREFIX}{entry.key}"
            if component_tag not in note.tags:
                note.tags.append(component_tag)

        entries, _ = _library_entries()
        _, result = _render_note(note, entries)
        note[TARGET_FIELD] = result.html
        mw.col.update_note(note)
        editor.loadNoteKeepingFocus()
    except Exception as error:
        showWarning(f"Ajout interrompu : {error}", parent=editor.widget)
        return

    showInfo(
        "La mnémotechnique a été enregistrée dans la bibliothèque et appliquée "
        "uniquement à la note courante.",
        parent=editor.widget,
    )


def synchronize_all() -> None:
    config = mw.addonManager.getConfig(__name__) or {}
    if config.get("trialMode", True):
        showWarning(
            "La synchronisation globale est désactivée tant que trialMode vaut true. "
            "Le premier essai doit rester limité à une note."
        )
        return
    if not _is_migrated():
        showWarning("La migration ImageMnemo → MnemoAuto doit être effectuée.")
        return

    entries, warnings = _library_entries()
    changes: list[tuple[Note, str]] = []
    for note_id in _target_note_ids():
        note = mw.col.get_note(note_id)
        _, result = _render_note(note, entries)
        if result.html != note[TARGET_FIELD]:
            changes.append((note, result.html))

    if not askUser(
        f"Notes Yoyo à modifier : {len(changes)}\n"
        f"Avertissements de bibliothèque : {len(warnings)}\n\n"
        "Créer une sauvegarde et appliquer ces changements ?"
    ):
        return
    if not changes:
        showInfo("Aucune note ne nécessite de mise à jour.")
        return

    try:
        mw.create_backup_now()
        for note, value in changes:
            note[TARGET_FIELD] = value
            mw.col.update_note(note)
        mw.reset()
    except Exception as error:
        showWarning(f"Synchronisation globale interrompue : {error}")
        return
    showInfo(f"Synchronisation terminée pour {len(changes)} note(s).")


def _setup_image_selection_tracking(editor: Editor) -> None:
    setattr(editor, "_huaxia_selected_image_src", "")
    if editor.web:
        editor.web.eval(IMAGE_SELECTION_TRACKER_JS)


def _receive_image_selection(
    handled: tuple[bool, object | None],
    message: str,
    context: object,
) -> tuple[bool, object | None]:
    prefix = "huaxia_mnemo_image_selected:"
    if not message.startswith(prefix) or not isinstance(context, Editor):
        return handled
    setattr(
        context,
        "_huaxia_selected_image_src",
        unquote(message[len(prefix):]),
    )
    return (True, None)


def _add_editor_button(buttons: list[str], editor: Editor) -> None:
    preview_button = editor.addButton(
        icon=None,
        cmd="huaxia_preview_linked_mnemonics",
        func=lambda active_editor: preview_current_note(active_editor.note),
        tip="Prévisualiser les mnémotechniques liées",
        label="🧠?",
        id="huaxia-preview-linked-mnemonics",
    )
    apply_button = editor.addButton(
        icon=None,
        cmd="huaxia_apply_linked_mnemonics",
        func=lambda active_editor: apply_current_note(active_editor.note),
        tip="Appliquer les mnémotechniques à cette note",
        label="🧠✓",
        id="huaxia-apply-linked-mnemonics",
    )
    add_button = editor.addButton(
        icon=None,
        cmd="huaxia_add_linked_mnemonic",
        func=add_mnemonic_from_editor,
        tip="Ajouter une mnémotechnique liée",
        label="🧠+",
        id="huaxia-add-linked-mnemonic",
    )
    buttons.extend((preview_button, apply_button, add_button))


def _scope_enhanced_cloze_sounds(card: Card, sounds: list[AVTag]) -> None:
    """Keep only Content sounds associated with the current Cloze card."""
    note = card.note()
    if _model_name(note) != ENHANCED_CLOZE_MODEL:
        return
    if ENHANCED_CLOZE_CONTENT_FIELD not in note:
        return

    all_audio, selected_audio = enhanced_cloze_audio_counts(
        note[ENHANCED_CLOZE_CONTENT_FIELD],
        card.ord + 1,
    )
    if not all_audio:
        return

    kept_counts: Counter[str] = Counter()
    filtered: list[AVTag] = []
    for tag in sounds:
        if not isinstance(tag, SoundOrVideoTag):
            filtered.append(tag)
            continue

        filename = tag.filename
        if filename not in all_audio:
            # Do not alter audio coming from another field.
            filtered.append(tag)
            continue

        if kept_counts[filename] < selected_audio[filename]:
            filtered.append(tag)
            kept_counts[filename] += 1

    sounds[:] = filtered


def _setup_menu() -> None:
    menu = mw.form.menuTools.addMenu("Huaxia Mnémotechniques")

    migrate_action = QAction("Initialiser / migrer…", mw)
    qconnect(migrate_action.triggered, migrate_collection)
    menu.addAction(migrate_action)

    preview_action = QAction("Prévisualiser la note en cours", mw)
    qconnect(preview_action.triggered, preview_current_note)
    menu.addAction(preview_action)

    apply_action = QAction("Appliquer à la note en cours…", mw)
    qconnect(apply_action.triggered, apply_current_note)
    menu.addAction(apply_action)

    menu.addSeparator()
    global_action = QAction("Synchroniser tout le modèle Yoyo…", mw)
    qconnect(global_action.triggered, synchronize_all)
    menu.addAction(global_action)


gui_hooks.editor_did_init_buttons.append(_add_editor_button)
gui_hooks.editor_did_load_note.append(_setup_image_selection_tracking)
gui_hooks.webview_did_receive_js_message.append(_receive_image_selection)
gui_hooks.reviewer_will_play_question_sounds.append(_scope_enhanced_cloze_sounds)
gui_hooks.reviewer_will_play_answer_sounds.append(_scope_enhanced_cloze_sounds)
_setup_menu()
