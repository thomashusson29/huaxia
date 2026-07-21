# Chineasy & Yoyo Chinese to Anki Studio

Module de traitement d'images OCR (Chineasy) et de conversion de cours PDF (Yoyo Chinese) pour la création et la synchronisation automatique de cartes Anki interactives avec audio HD natif.

---

## 1. Objectif & Utilité

Cet outil permet d'automatiser l'apprentissage du chinois Mandarin sur Anki via deux sources d'apprentissage majeures :

1. **Captures d'écran Chineasy** (Deck `chinois::chineasy_characters`) :
   - Traitement des illustrations mnémotechniques, détourage PNG transparent, analyse OCR 100% dynamique et génération de 2 cartes Anki par note.
2. **Fiches de cours PDF Yoyo Chinese** (Deck `chinois::yoyo_chinese`) :
   - Conversion automatique des PDF de leçons Yoyo Chinese en Markdown.
   - Extraction des paires Vocabulaire + Phrases d'exemple en Chinois Simplifié.
   - Génération audio HD Mandarin native et création de 2 cartes par note dans le deck dédié `chinois::yoyo_chinese`.

---

## 2. Prérequis & Installation

### Prérequis

1. Python 3.10 ou version supérieure.
2. macOS (avec support GPU Metal MPS) ou Linux / Windows.
3. Anki Desktop ouvert avec l'extension AnkiConnect (Code : 2055492159).

### Installation

```bash
# 1. Accéder au dossier du projet
cd anki_characters/chineasy_to_anki

# 2. Créer et activer l'environnement virtuel Python
python3 -m venv .venv
source .venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt
```

---

## 3. Utilisation

### Mode Interface Web (GUI)

```bash
python app.py
```

Ouvrez votre navigateur à l'adresse : `http://127.0.0.1:5001`

- **Onglet Chineasy** : Sélectionnez un dossier de captures d'écran et lancez l'extraction.
- **Onglet Yoyo Chinese** : Glissez-déposez un fichier PDF de cours Yoyo Chinese (ou sélectionnez un fichier dans `pdf_input/`) pour convertir le PDF en Markdown et importer automatiquement le vocabulaire et les phrases dans Anki.

### Mode Ligne de Commande (CLI)

- **Traitement Chineasy** :
  ```bash
  python main.py captures/20_07_2026
  ```

- **Traitement Yoyo Chinese PDF** :
  ```bash
  python src/yoyo_parser.py /chemin/vers/votre/cours.pdf
  ```

---

## 4. Architecture & Modèles Anki

| Source | Deck Anki Cible | Modèle de Note | Cartes Générées par Note |
| :--- | :--- | :--- | :--- |
| **Chineasy Captures** | `chinois::chineasy_characters` | `Chineasy Character Model v3` | 1. Reconnaissance Visuelle<br>2. Écoute Audio & Écriture (Canvas + Input) |
| **Yoyo Chinese PDF** | `chinois::yoyo_chinese` | `Yoyo Chinese Model` | 1. Reconnaissance Visuelle<br>2. Écoute Audio & Écriture (Canvas + Input) |

---

## 5. Exemple Pratique d'Utilisation

### Carte Anki Générée (Recto vs Verso pour le caractère 人)

| RECTO (Front) : Caractère Seul | VERSO (Back) : Fiche Complète avec Illustration |
| :---: | :---: |
| ![Carte Anki Recto 人](docs/images/card_recto_person.png) | ![Carte Anki Verso 人](docs/images/anki_card1_verso_person.png) |
