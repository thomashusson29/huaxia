# Génération locale de brouillons Anki

## Interface de téléchargement des leçons

Pour télécharger une nouvelle leçon sans passer par le terminal, double-cliquer
sur `Lancer le téléchargeur.command` à la racine du dossier `lechinoisfacile`.
La page locale permet de coller l’URL, lance le téléchargeur sécurisé, crée le
lien symbolique dans Obsidian et affiche le Markdown obtenu.

L’interface écoute uniquement sur `127.0.0.1:5050`. Elle ne lit ni ne stocke les
identifiants : le script de téléchargement les récupère directement dans le
Trousseau macOS.

## Cartes Anki expérimentales

`generate_anki_preview.py` utilise un modèle Ollama local pour produire deux
brouillons relisibles à partir d’une leçon téléchargée :

- `questions.md` pour le workflow question/réponse ;
- `cloze.md` pour Enhanced Cloze ;
- `cards.json` comme résultat structuré et traçable.

Le script ne contacte jamais AnkiConnect. Les brouillons portent toujours
`anki_enabled: false` afin d’empêcher une synchronisation accidentelle.

## Utilisation

Depuis le dossier `huaxia` :

```bash
python3 lechinoisfacile/tools/generate_anki_preview.py \
  lechinoisfacile/lecon-1 \
  --model qwen3-vl:8b
```

Par défaut, les résultats sont écrits dans `lecon-1/anki-preview/`. Le modèle,
l’URL Ollama et le dossier de sortie peuvent être changés par les options de la
commande.
