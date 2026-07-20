# Chineasy to Anki Studio 🇨🇳🎴

Module d'importation et de création automatique de cartes Anki haute qualité à partir de captures d'écran de l'application **Chineasy**.

---

## 1. Utilité

Ce projet automatise entièrement la création de cartes mémoire Anki pour l'apprentissage du chinois mandarin :

- 🔍 **Extraction OCR intelligente** : Reconnaît les caractères simples (`人`, `火`, `大`, `小`) ainsi que les **mots composés de plusieurs caractères** (`人人`, `大人`, `小人`, `大小`, `火山`, `大火`).
- 📝 **Restitution exacte du texte** : Conserve la mise en page originale, les retours à la ligne (`<br>`) et répare les coupures de phrase ou typos OCR.
- 🎨 **Détourage transparent automatique** : Supprime le fond coloré des illustrations mnémotechniques Chineasy, applique un lissage anti-aliasing et masque les barres d'interface iOS.
- 🔊 **Audio Mandarin HD (Respect des 4 tons)** : Récupère les enregistrements vocaux humains officiels de dictionnaire mandarin (Youdao / Baidu) pour une prononciation claire et distincte de chaque ton.
- 🎴 **Génération automatique de 2 types de cartes Anki par note** :
  1. **Reconnaissance Visuelle** : Hanzi ➔ Verso complet (Pinyin, Son, Traduction, Explication, Illustration).
  2. **Écoute & Écriture** : Son Audio seul ➔ Champ de saisie Pinyin (`{{type:Pinyin}}`) + Tableau blanc interactif HTML5 (`<canvas>`) pour tracer le caractère au doigt/souris ➔ Correction complète au verso.
- 🚀 **Synchronisation AnkiConnect & Sécurité** : Envoi direct vers le deck `chinois::chineasy_characters`, gestion intelligente des doublons, réparation automatique des sons et renommage des dossiers traités (`_PROCESSED`).
- 🖥️ **Interface Web locale épurée** : Console en direct et galerie de prévisualisation via Flask (`app.py`).

---

## 2. Tutoriel & Guide de Démarrage

### Prérequis

1. **Python 3.10+** installé sur votre machine.
2. **Anki Desktop** ouvert en arrière-plan avec l'extension **AnkiConnect** (Code de l'extension : `2055492159`).
   - *Note : AnkiConnect écoute sur le port 8766 (ou 8765).*

### Installation

```bash
# 1. Cloner ou se placer dans le dossier du projet
cd anki_characters

# 2. Créer et activer l'environnement virtuel Python
python3 -m venv .venv
source .venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt
```

### Utilisation en Ligne de Commande (CLI)

```bash
# Placer vos screenshots dans un sous-dossier de captures/ (ex: captures/20_07_2026)
python main.py captures/20_07_2026
```

### Utilisation via l'Interface Web (GUI)

```bash
# Démarrer le serveur web local
python app.py
```
Ouvrez votre navigateur à l'adresse : **`http://127.0.0.1:5001`**

---

## 3. Architecture & Fonctionnement Technique

```
anki_characters/
├── main.py                    # Script d'exécution principal CLI
├── app.py                     # Serveur Web Flask (Interface graphique locale)
├── requirements.txt           # Dépendances Python
├── src/
│   ├── ocr_extractor.py       # Extraction du texte & classification des cartes
│   ├── image_processor.py     # Détourage fond transparent & rognage OpenCV
│   ├── card_matcher.py        # Appariement (Détail <-> Mnémotechnique)
│   ├── audio_generator.py     # Génération audio mandarin HD
│   └── anki_exporter.py       # Synchronisation AnkiConnect & fallback genanki
├── templates/
│   └── index.html             # Interface Web natif One Dark Pro
└── captures/                  # Dossiers de captures d'écran
```

### Modules & Mécanismes de Fallback

| Module | Librairies Principales | Rôle & Mécanisme de Fallback |
| :--- | :--- | :--- |
| **OCR & Extraction** | `easyocr`, `pypinyin`, `re` | **Principal** : EasyOCR avec regroupement vertical des boîtes par coordonnées Y pour conserver les retours à la ligne.<br>**Fallback** : Modèle de vision local Ollama (`llama3.2-vision`). |
| **Pinyin & Tons** | `pypinyin` | Génération déterministe et exacte des accents tonaux Pinyin pour caractères simples et mots composés (`rén rén`, `dà huǒ`, `huǒ shān`). |
| **Traitement d'Image** | `Pillow`, `opencv-python`, `numpy` | Détection de la couleur de fond par échantillonnage des 4 coins, masque de distance RGB, anti-aliasing GaussianBlur sur canal Alpha, masquage status bar iOS (haut 16%, bas 12%). |
| **Appariement** | Algorithmes Python | **Tier 1** : Mot-clé anglais exact.<br>**Tier 2** : Recherche dans le texte de l'histoire.<br>**Tier 3 (Fallback)** : Séquence d'images adjacentes (`Image N-1` ➔ `Image N`). |
| **Audio Mandarin** | `requests`, `edge-tts`, `gTTS` | **Priorité 1** : Dictionnaire Youdao (`dictvoice`) & Baidu Speech (voix humaines HD articulant les 4 tons).<br>**Fallback 1** : `edge-tts` ralenti (`-20%`).<br>**Fallback 2** : `gTTS`. |
| **Export Anki** | `requests`, `genanki` | **Priorité 1** : AnkiConnect API sur port `8766` ou `8765`. Traitement note par note avec mise à jour des notes existantes.<br>**Fallback** : Génération d'un fichier autonome `.apkg` via `genanki`. |

---

## 📄 Licence
Projet sous licence MIT - Libre d'utilisation et d'adaptation.
