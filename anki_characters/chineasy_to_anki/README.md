# Chineasy to Anki Studio

Module de traitement d'images et d'importation automatique de cartes Anki à partir de captures d'écran de l'application Chineasy.

---

## 1. Objectif & Utilité

L'objectif unique de cet outil est d'automatiser la création de cartes Anki à partir de captures d'écran de l'application mobile ou tablette **Chineasy**.

Fonctionnalités principales :

- Extraction OCR des caractères simples (ex: 人, 火, 大, 小) et des mots composés de plusieurs caractères (ex: 人人, 大人, 小人, 大小, 火山, 大火).
- Reconstitution fidèle du texte d'explication avec retours à la ligne exacts (<br>) et correction des coupures OCR.
- Détourage transparent des illustrations mnémotechniques par analyse des couleurs de fond et suppression de l'interface mobile iOS.
- Prononciation audio HD en mandarin avec respect des 4 tons via les API vocales de dictionnaire chinois (Youdao / Baidu).
- Génération automatique de 2 cartes par note Anki :
  1. Reconnaissance Visuelle : Hanzi au recto -> Verso complet (Pinyin, Son, Traduction, Explication, Image).
  2. Écoute & Écriture : Audio seul au recto + champ de saisie Pinyin + tableau blanc HTML5 (Canvas) pour dessiner les traits -> Correction au verso.
- Synchronisation AnkiConnect vers le paquet `chinois::chineasy_characters` et interface web locale (Flask).

---

## 2. Prérequis & Installation

### Prérequis

1. Python 3.10 ou version supérieure.
2. Anki Desktop ouvert avec l'extension AnkiConnect (Code extension : 2055492159).

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

### Mode Ligne de Commande (CLI)

Placez vos captures d'écran dans un sous-dossier de `captures/` (par exemple `captures/20_07_2026`), puis lancez :

```bash
python main.py captures/20_07_2026
```

### Mode Interface Web (GUI)

```bash
python app.py
```
Ouvrez votre navigateur à l'adresse : `http://127.0.0.1:5001`

---

## 4. Architecture & Fallbacks

| Composant | Bibliothèques | Fonctionnement & Fallbacks |
| :--- | :--- | :--- |
| OCR | easyocr, pypinyin, re | EasyOCR avec regroupement par coordonnées Y de ligne. Fallback : Ollama Vision (llama3.2-vision). |
| Image | Pillow, opencv-python, numpy | Échantillonnage du fond coloré 4 coins, masque de distance RGB, rognage et masquage status bar iOS. |
| Appariement | Python | 1. Mot-clé anglais. 2. Recherche histoire. 3. Séquence d'images adjacentes (N-1 -> N). |
| Audio | requests, edge-tts, gTTS | 1. Dictionnaire Youdao & Baidu Speech (voix humaines HD 4 tons). 2. Edge-TTS (-20%). 3. gTTS. |
| Export Anki | requests, genanki | 1. AnkiConnect (ports 8766 / 8765) avec dédoublonnage automatique. 2. Paquet autonome genanki (.apkg). |

---

## 5. Exemple Pratique d'Utilisation

### 1. Captures d'Écran d'Entrée (Chineasy)

| Capture Illustration (IMG_9214.PNG) | Capture Fiche Détail (IMG_9215.PNG) |
| :---: | :---: |
| ![Illustration Chineasy](docs/images/example_mnemo_adult.png) | ![Fiche Détail Chineasy](docs/images/example_detail_adult.png) |

### 2. Illustration Mnémotechnique Détourée Générée

| Image PNG Transparent Générée |
| :---: |
| ![Illustration Transparent PNG](docs/images/example_transparent_adult.png) |

### 3. Déroulement du Traitement

1. Déposer les deux fichiers dans `captures/session_adult/` :
   - `captures/session_adult/IMG_9214.PNG` (Illustration)
   - `captures/session_adult/IMG_9215.PNG` (Détail)

2. Exécuter la commande :
   ```bash
   python main.py captures/session_adult
   ```

3. Résultat obtenu dans Anki :
   - Le paquet `chinois::chineasy_characters` reçoit la note **大人**.
   - **Carte 1 (Visuelle)** : Recto avec "大人" -> Verso avec "大人", Pinyin "dà rén", Audio MP3 "audio_zh_大人.mp3", Traduction "Adult", Explication complète avec retours à la ligne exacts, et l'image transparente détourée.
   - **Carte 2 (Écoute & Écriture)** : Recto avec la lecture audio "dà rén", la case pour taper "dà rén" et le tableau blanc HTML5 pour tracer le caractère -> Verso avec la correction complète.
   - Le dossier `captures/session_adult` est automatiquement renommé en `captures/session_adult_PROCESSED`.
