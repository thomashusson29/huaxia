# Exporteur complet Yoyo Chinese

Ce script récupère les vidéos MP4, les fiches PDF et les flashcards avec leurs
sons normal et lent. Il fabrique ensuite un paquet Anki par cours. Il
accepte l’URL d’une leçon, d’une unité, d’un cours ou du catalogue complet.
Si Anki est ouvert avec AnkiConnect, les cartes sont également synchronisées
dans le deck unique `chinois::ychinese::bulk export`.

Avec un compte payant configuré dans le Trousseau macOS, il se connecte à
Yoyo Chinese avant de parcourir le catalogue. Il ne devine jamais les URL :
une leçon ou une unité encore marquée comme verrouillée pour la session est
ignorée.

## Configurer le compte payant

Double-cliquer sur `Configurer le compte.command`, puis saisir l’adresse e-mail
et le mot de passe dans la fenêtre Terminal. La saisie du mot de passe est
masquée et les deux valeurs sont enregistrées directement dans le Trousseau
macOS sous les services `fr.yoyochinese.downloader.*`.

Ne pas écrire les identifiants dans ce dossier, dans une commande ou dans un
fichier `.env`. Une fois le Trousseau configuré, le téléchargeur se connecte
automatiquement à chaque lancement.

Le double-clic sur `Lancer le téléchargeur.command` prépare automatiquement un
petit environnement Python local lors de la première utilisation. Rien n’est
installé globalement sur le Mac.

## Leçon testée

```bash
cd "/Users/thomashusson/Documents/Projets/huaxia/yoyochinese"
.venv/bin/python download_yoyo.py \
  "https://yoyochinese.com/lesson/beginner-conversational-unit-14-lesson-1-Something-to-Drink-Part-1/flashcards"
```

Le résultat est organisé ainsi :

```text
downloads/
  Courses/
    Beginner Conversational/
      Level 02/
        Unit 014 - Drinking/
          Lesson 01 - Something to Drink - Part 1/
            BCC-014-01.mp4
            Beg-Unit-014-Lesson-01-LN.pdf
            lesson.json
            Flashcards/
              flashcards.json
              audio/
                BCC-014-01-001-N.mp3
                BCC-014-01-001-S.mp3
                ...
      Anki/
        Beginner Conversational.apkg
    Chinese Characters/
      ...
      Anki/
        Chinese Characters.apkg
  manifest.json
```

Chaque cours produit un seul deck, par exemple
`chinois::yoyo_chinese::Beginner Conversational`. Les cartes sont différenciées
par un chemin hiérarchique complet, par exemple :

```text
chinois::source::yoyochinese::cours::beginner_conversational::niveau::02::unite::014::lecon::01
```

Une carte Yoyo réutilisée dans plusieurs leçons n’est créée qu’une fois et
cumule un chemin complet par leçon.

## Synchronisation AnkiConnect

La synchronisation est automatique lorsque l’application Anki et AnkiConnect
sont disponibles sur le Mac. Toutes les cartes sont alors réunies dans :

```text
chinois::ychinese::bulk export
```

La synchronisation importe les paquets `.apkg` complets par AnkiConnect, puis
replace toutes les cartes identifiées par le champ `YoyoId` dans le deck bulk
export. Le GUID Anki stable dérivé de l’identifiant Yoyo évite les doublons lors
des exécutions suivantes. Deux cartes Yoyo distinctes peuvent conserver le même
Hanzi sans être fusionnées.

Si Anki est fermé, l’export ne s’arrête pas : les fichiers `.apkg` sont créés
normalement et le manifeste indique simplement qu’AnkiConnect était
indisponible. Aucune synchronisation n’est réalisée pendant `--dry-run`.

## Télécharger une unité ou un cours

```bash
.venv/bin/python download_yoyo.py \
  "https://yoyochinese.com/unit/beginner-conversational-unit-1-Getting-Started"

.venv/bin/python download_yoyo.py \
  "https://yoyochinese.com/courses/beginner-conversational-chinese"
```

Pour tout le catalogue, la confirmation explicite est obligatoire car cela
représente 1 272 leçons au moment du test et peut donc demander énormément de
temps, de données et d’espace disque :

```bash
.venv/bin/python download_yoyo.py "https://yoyochinese.com/courses" --all-courses
```

Options utiles :

- `--dry-run` : découvre et affiche les fichiers sans les télécharger ;
- `--limit 5` : limite le test aux cinq premières leçons ;
- `--workers 3` : règle le nombre de téléchargements parallèles ;
- `--overwrite` : remplace les fichiers déjà présents ;
- `--no-videos` : exporte sans les MP4 ;
- `--no-pdfs` : exporte sans les fiches PDF ;
- `--no-anki` : exporte sans les flashcards ni leurs sons ;
- `--no-anki-connect` : crée les `.apkg` sans synchroniser la collection ouverte ;
- `--anki-connect-deck NOM` : remplace le deck bulk export par un autre nom ;
- `--anki-audio normal|slow|both` : choisit les sons intégrés ;
- `-o DOSSIER` : choisit le dossier de destination ;
- `--cookie-file cookies.txt` : utilise des cookies Netscape exportés depuis
  une session Yoyo Chinese autorisée ;
- `--no-keychain` : désactive volontairement la connexion par le Trousseau.

Les téléchargements interrompus restent en `.part` et reprennent au prochain
lancement. Les fichiers terminés sont conservés et ignorés par défaut. Une
erreur sur un média n’interrompt pas les autres leçons : elle est inscrite dans
`manifest.json`.

Pour l’audio des flashcards, le script tente d’abord le fichier original Yoyo
et réessaie automatiquement les erreurs réseau temporaires. Si Yoyo refuse ou
n’expose pas le son, il génère le fichier avec la première source disponible,
dans cet ordre : Youdao, Baidu, Edge TTS, puis gTTS. Le manifeste conserve le
fournisseur utilisé et l’erreur Yoyo d’origine dans un avertissement, sans
marquer la leçon comme partielle si le remplacement a réussi.

## Vérifier sans télécharger

Avant un téléchargement massif, faire un inventaire limité :

```bash
.venv/bin/python download_yoyo.py \
  "https://yoyochinese.com/courses/beginner-conversational-chinese" \
  --dry-run --limit 5
```

Le mode `--dry-run` charge seulement les petites pages HTML et les métadonnées
JSON des flashcards. Il ne télécharge aucun MP4, PDF ou MP3 et ne crée aucun
paquet Anki.

Pour tester uniquement les flashcards d’une leçon sans vidéo ni PDF :

```bash
.venv/bin/python download_yoyo.py \
  "URL_DE_LA_LECON" \
  --no-videos --no-pdfs
```

Un export limité par `--limit`, une leçon ou une unité produit un paquet nommé
`Cours - sélection.apkg`. Un export complet du cours remplace ensuite cette
sélection par `Cours.apkg`. Les identifiants stables Yoyo empêchent les
doublons lors de l’import successif dans Anki.

## Compléter les sons manquants dans Anki

Le script `fill_missing_anki_audio.py` analyse le deck racine `chinois` et ses
sous-decks. Il ne sélectionne que les notes qui remplissent toutes ces
conditions : aucun champ ne contient déjà de balise `[sound:…]`, le modèle
possède un champ audio reconnu, ce champ est vide et un champ Hanzi/Mandarin
contient bien du texte chinois.

Lancer un aperçu sans rien modifier :

```bash
.venv/bin/python fill_missing_anki_audio.py --deck chinois
```

Appliquer ensuite les ajouts :

```bash
.venv/bin/python fill_missing_anki_audio.py --deck chinois --apply
```

La génération suit toujours l’ordre Youdao, Baidu, Edge TTS, puis gTTS. Les MP3
sont conservés dans `generated_anki_audio`, envoyés dans la médiathèque Anki et
référencés dans le champ `Audio`. Le tag
`chinois::audio::source::FOURNISSEUR` permet de retrouver les notes
modifiées et leur fournisseur. Le fichier `last_run.json` contient le rapport
de la dernière exécution.

Le lanceur `Ajouter les sons manquants.command` fournit la même opération par
double-clic, avec un aperçu et une confirmation avant toute modification.
