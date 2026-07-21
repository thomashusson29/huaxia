# Chineasy & Yoyo Chinese to Anki Studio

Module complet d'extraction OCR (Chineasy), de conversion de leçons PDF (Yoyo Chinese) et de génération automatique de cartes Anki interactives avec prononciation audio HD native, rendu adaptatif (Light/Dark mode) et synchronisation instantanée.

---

## 1. Objectif & Utilité

L'objectif de cet outil est d'automatiser à 100% la création de cartes de révision Anki interactives et enrichies pour le Chinois Mandarin à partir de deux sources de cours majeures :

### 1. Captures d'écran Chineasy (Deck `chinois::chineasy_characters`)
- **Paires de captures classiques** : Illustration mnémotechnique + Fiche de détail lexicographique (Pinyin, composition, traduction, phrase).
- **Cartes "Word of the Day" (Capture unique combinée)** : 1 seule capture contenant l'illustration en haut et la fiche de détail en bas.

### 2. Cours PDF Yoyo Chinese (Deck `chinois::yoyo_chinese`)
- **Conversion PDF vers Markdown** : Génération automatique d'un document Markdown structuré avec des tableaux comparatifs (Vocabulaire et Phrases).
- **Conservation exclusive du Chinois Simplifié** : Traitement et élimination automatique des caractères traditionnels doublons.
- **Sauvegarde adjacente au PDF** : Enregistrement du fichier Markdown `.md` directement dans le dossier d'origine du fichier PDF.

---

## 2. Fonctionnalités Principales

- **Extraction 100% Dynamique (EasyOCR)** : Analyse automatique du texte sans dictionnaire statique ni liste codée en dur.
- **Accélération Matérielle Apple Silicon (MPS GPU)** : Exploitation du processeur graphique Metal (GPU M1/M2/M3/M4) pour une vitesse d'extraction OCR optimisée (25x plus rapide que le CPU).
- **Détourage Transparent d'Illustration** : Masquage automatique du fond coloré et détourage PNG transparent des illustrations mnémotechniques.
- **Prononciation Audio HD Native & Chaine de Fallback** :
  1. *Dictionnaire Youdao HD* : Voix humaines natives de studio avec respect strict des 4 tons.
  2. *Baidu Speech API* : Prononciation fluide des phrases et expressions.
  3. *Microsoft Edge-TTS* : Synthèse vocale HD naturelle (`zh-CN-XiaoxiaoNeural`).
  4. *Google gTTS* : Fallback universel.
- **Auto-Play Audio Forcé** : Lecture automatique de l'audio dès l'ouverture des cartes Anki (Recto/Verso).
- **Génération Automatique de 2 Cartes par Note Anki** :
  - **Carte 1 (Reconnaissance Visuelle)** : Hanzi au recto ➔ Verso complet (Pinyin, Son HD, Traduction, Explication, Illustration).
  - **Carte 2 (Écoute & Écriture)** : Lecture audio seule au recto + zone de saisie (Pinyin ou Hanzi) + tableau blanc HTML5 (Canvas) pour dessiner les traits ➔ Correction automatique au verso.
- **Rendu Adaptatif Light & Dark Mode** : Support natif du mode nuit (`#2c2c2c`) sur Anki Desktop et AnkiMobile.
- **Système de Tagging Automatique Hiérarchisé** :
  - Chineasy : `chinois`, `chineasy`
  - Yoyo Chinese : `chinois`, `yoyochinese`, `unit1`, `lesson1`, `vocabulary`, `sentence`

---

## 3. Prérequis & Installation

### Prérequis

1. Python 3.10 ou version supérieure.
2. macOS (avec support natif Apple Silicon GPU via Metal MPS) ou Linux / Windows.
3. Anki Desktop ouvert avec l'extension AnkiConnect (Code d'extension Anki : `2055492159`).

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

## 4. Utilisation

### Mode Interface Web (GUI)

```bash
python app.py
```

Ouvrez votre navigateur à l'adresse : `http://127.0.0.1:5001`

- **Onglet Chineasy (Captures)** : Sélectionnez un sous-dossier de `captures/` et lancez le traitement automatique.
- **Onglet Yoyo Chinese (PDF)** : Glissez-déposez un fichier PDF de cours Yoyo Chinese dans la zone de dépôt (ou sélectionnez-en un dans la liste) pour générer le Markdown et importer les cartes dans Anki.

### Mode Ligne de Commande (CLI)

- **Traitement de captures Chineasy** :
  ```bash
  python main.py captures/20_07_2026
  ```

- **Parsing et conversion de cours PDF Yoyo Chinese** :
  ```bash
  python src/yoyo_parser.py /chemin/vers/votre/cours.pdf
  ```

---

## 5. Architecture & Chaîne de Fallback

| Composant | Bibliothèques & Outils | Fonctionnement & Fallbacks |
| :--- | :--- | :--- |
| **Accélération GPU** | PyTorch (MPS / Metal) | GPU Apple Silicon (M1/M2/M3/M4) via `PYTORCH_ENABLE_MPS_FALLBACK=1` (25.14x plus rapide que CPU). Fallback : CUDA / CPU. |
| **OCR & NLP** | easyocr, pypinyin, re | Extraction par lignes Y. Fusion CJK adjacente. Génération Pinyin automatique. |
| **Traitement d'Image** | Pillow, opencv-python, numpy | Échantillonnage de couleur de fond (4 coins), masque de distance RGB, masquage UI iOS et recadrage adaptatif. |
| **Appariement Chineasy** | Python (`card_matcher.py`) | 1. Cartes Word of the Day combinées. 2. Séquence d'images adjacentes (N-1). 3. Mot-clé anglais avec auto-correction. |
| **Parsing PDF Yoyo** | pypdf, pdftotext, requests | Extraction de texte, conversion Markdown avec tableaux comparatifs, filtrage 100% Simplifié, embellissement Qwen (Ollama). |
| **Audio HD Native** | requests, edge-tts, gTTS | 1. Dictionnaire Youdao HD (voix humaines studio). 2. Baidu Speech API. 3. Edge-TTS (`zh-CN-XiaoxiaoNeural`). 4. gTTS. |
| **Export & Sync Anki** | requests, genanki, AnkiConnect | 1. AnkiConnect (ports 8766/8765) avec dédoublonnage strict et tagging direct. 2. Paquet autonome genanki (`.apkg`). |

---

## 6. Exemples Pratiques d'Utilisation

### Carte Anki Générée (Recto vs Verso pour le caractère 人)

| RECTO (Front) : Caractère Seul | VERSO (Back) : Fiche Complète avec Illustration |
| :---: | :---: |
| ![Carte Anki Recto 人](docs/images/card_recto_person.png) | ![Carte Anki Verso 人](docs/images/anki_card1_verso_person.png) |

### Déroulement du Traitement

1. **Captures Chineasy** :
   - Déposer les captures dans `captures/20_07_2026/`.
   - Exécuter `python main.py captures/20_07_2026` ou utiliser l'interface Web.
   - Les cartes sont créées dans le deck `chinois::chineasy_characters` avec les tags `chinois` et `chineasy`.

2. **Cours PDF Yoyo Chinese** :
   - Glisser-déposer le fichier PDF dans l'interface Web (ex: `Beg-Unit-001-Lesson-01-LN.pdf`).
   - Le fichier Markdown structuré avec tableaux est enregistré à côté du PDF.
   - Les cartes (vocabulaire et phrases) sont créées dans le deck `chinois::yoyo_chinese` avec les tags `chinois`, `yoyochinese`, `unit1`, `lesson1`, `vocabulary` / `sentence`.
