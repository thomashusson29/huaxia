# Workflow chinois — Cours, PDF, Anki, Obsidian, audio et mnémotechniques

Documentation centrale du workflow Huaxia.

Dernière vérification locale : **23 juillet 2026**.

## 1. Objectif

Ce système transforme plusieurs sources de travail en cartes Anki et en fiches
Obsidian reliées :

- cours et transcriptions ;
- PDF Yoyo Chinese ;
- captures Chineasy ;
- notes personnelles en Markdown ;
- images mnémotechniques trouvées ou créées manuellement ;
- audio original ou généré par synthèse vocale.

Il faut distinguer deux chaînes qui se rejoignent dans Anki :

```text
PDF Yoyo ─→ application locale ─→ cartes chinoises + audio dans Anki
                                      │
Images mnémotechniques ─→ bibliothèque Huaxia
                                      │
                                      ├─→ propagation vers les cartes Yoyo
                                      └─→ fiches de la base Obsidian

Transcription ─→ notes personnelles sous Obsidian/Cours
                                      │
                                      └─→ Markdown vers Anki → Q/R ou Clozes
                                                        + audio local

Toutes les cartes Anki ─→ AnkiWeb ─→ AnkiMobile
```

La bibliothèque mnémotechnique centrale se trouve **dans Anki**. La base
Obsidian `Chinois/caracteres` est actuellement une vue générée à partir des
notes Anki, et non la source principale des mnémotechniques.

## 2. État actuel des fonctions

| Fonction | Outil | État |
|---|---|---|
| Convertir un PDF Yoyo en vocabulaire et phrases | Application Flask locale | Opérationnel |
| Générer l’audio du PDF | Youdao → Baidu → Edge TTS → gTTS | Opérationnel |
| Importer les cartes Yoyo dans Anki | AnkiConnect | Opérationnel |
| Transformer des captures Chineasy | OCR et traitement d’image | Opérationnel |
| Créer des cartes depuis des notes personnelles | Markdown vers Anki | Opérationnel sous `Cours/**/*.md` |
| Ajouter une mnémotechnique centrale | Huaxia `🧠+` | Opérationnel |
| Prévisualiser une propagation | Huaxia `🧠?` | Opérationnel |
| Appliquer à une note | Huaxia `🧠✓` | Opérationnel |
| Exporter la note modifiée vers Obsidian | Huaxia | Opérationnel |
| Créer une fiche Obsidian absente | Huaxia | Opérationnel |
| Synchroniser toutes les mnémotechniques | Huaxia | Verrouillé par `trialMode: true` |
| Générer un audio avec HyperTTS sur le modèle Yoyo | HyperTTS | Opérationnel |
| Ajouter un audio local aux cartes Markdown | Markdown vers Anki | Opérationnel |
| Ajouter HyperTTS aux champs gérés par Markdown vers Anki | HyperTTS + mdanki | Non recommandé actuellement |
| Préserver les paragraphes manuels dans une fiche générée `Chinois/caracteres` | Export Huaxia | Pas encore implémenté |
| Exporter vers Obsidian après une modification HyperTTS seule | Export Huaxia | Pas encore automatique |

## 3. Dépendances

### 3.1 Anki

Configuration vérifiée :

- Anki Desktop **25.07.5** ;
- profil Anki : `Utilisateur 1` ;
- AnkiConnect sur `http://127.0.0.1:8766` ;
- add-on HyperTTS, identifiant `111623432` ;
- add-on Huaxia Mnémotechniques **0.3.0** ;
- modèle chinois `Yoyo Chinese Model v2-41f05` ;
- bibliothèque `chinois::mnemonics` ;
- modèle central `Huaxia Mnémotechnique v1`.

AnkiConnect doit rester lié à l’adresse locale. Les applications du projet
essaient le port `8766`, puis `8765` en secours.

Documentation :

- [AnkiConnect](https://github.com/amikey/anki-connect)
- [Synchronisation AnkiWeb](https://docs.ankiweb.net/syncing.html)
- [Médias Anki](https://docs.ankiweb.net/media.html)
- [Sauvegardes Anki](https://docs.ankiweb.net/backups.html)

### 3.2 Application PDF et Chineasy

Dossier :

```text
anki_characters/chineasy_to_anki
```

Environnement vérifié :

- Python 3.14.6 ;
- Flask 3.1.3 ;
- Pillow 12.3.0 ;
- OpenCV 5.0.0.93 ;
- NumPy 2.5.1 ;
- EasyOCR 1.7.2 ;
- pytesseract 0.3.13 ;
- pypinyin 0.55.0 ;
- pypdf 6.14.2 ;
- edge-tts 7.2.8 ;
- gTTS 2.5.4 ;
- requests 2.34.2 ;
- genanki 0.13.1 ;
- client Ollama 0.6.2.

Dépendances système vérifiées :

- `pdftotext` 25.09.1 ;
- Tesseract 5.5.1 ;
- client Ollama 0.12.6.

Ollama est facultatif. S’il n’est pas lancé, le parseur conserve le Markdown
qu’il a produit sans relecture par Qwen.

Le code importe `pypdf`, mais cette bibliothèque manque actuellement dans
`anki_characters/chineasy_to_anki/requirements.txt`. Elle est installée dans
l’environnement local, mais il faudra l’ajouter au fichier de dépendances avant
une réinstallation propre.

### 3.3 Obsidian et Markdown vers Anki

Configuration vérifiée :

- plugin Obsidian `Markdown vers Anki` **0.7.1** ;
- moteur `Anki/md_to_anki.py` ;
- Python 3.14.6 dans le `.venv` du coffre ;
- Markdown 3.10 ;
- PyYAML 6.0.3 ;
- fichiers sources limités à `Cours/**/*.md`.

Configuration centrale :

```text
/Users/thomashusson/Documents/Projets/Docs_internat/Anki/mdanki.yaml
```

Documentation détaillée :

```text
/Users/thomashusson/Documents/Projets/Docs_internat/Anki/WORKFLOW_MARKDOWN_VERS_ANKI.md
```

### 3.4 HyperTTS et moteur mandarin

La configuration locale contient :

- le service personnalisé `MandarinFallback` ;
- le preset `Hanzi vers Audio` ;
- la source `Hanzi` ;
- la destination `Audio` ;
- une règle associée au modèle `Yoyo Chinese Model v2-41f05` ;
- le preset `Mandarin vers Audio` pour d’autres modèles chinois.

Le service personnalisé appelle :

```text
yoyochinese/.venv/bin/python
yoyochinese/hypertts_audio_bridge.py
```

Puis essaie :

```text
Youdao → Baidu → Edge TTS → gTTS
```

Cette chaîne nécessite un accès Internet. Les chemins sont actuellement
absolus : déplacer le projet Huaxia casserait le pont HyperTTS jusqu’à la mise à
jour de ces chemins.

Documentation :

- [HyperTTS — démarrage](https://www.vocab.ai/tutorials/hypertts-getting-started)
- [HyperTTS — mode avancé et presets](https://www.vocab.ai/tips/hypertts-advanced-mode)

## 4. Préparation initiale

### 4.1 Vérifier Anki

1. Ouvrir Anki Desktop.
2. Choisir le profil `Utilisateur 1`.
3. Vérifier que les add-ons AnkiConnect, HyperTTS et Huaxia sont activés.
4. Vérifier que le modèle Yoyo contient exactement :

```text
Hanzi
Traditional
Pinyin
Anglais
Explication
MnemoAuto
Audio
AudioLent
YoyoId
Source
```

5. Ne pas recréer manuellement un deuxième modèle portant un nom proche.

### 4.2 Démarrer l’application locale

```bash
cd /Users/thomashusson/Documents/Projets/huaxia/anki_characters/chineasy_to_anki
source .venv/bin/activate
python app.py
```

Ouvrir ensuite :

```text
http://127.0.0.1:5001
```

L’interface contient :

- `Chineasy (Captures)` ;
- `Yoyo Chinese (PDF)` ;
- une console de traitement ;
- une galerie des cartes produites.

Le bouton général `Synchroniser vers Obsidian` utilise encore l’ancien
exporteur `src/anki_to_obsidian.py`, qui lit `ImageMnemo`. Ne pas l’utiliser tant
qu’il n’a pas été aligné avec `MnemoAuto`.

## 5. Workflow quotidien complet

### Étape 1 — Regarder le cours

Pendant ou après le cours :

1. conserver la vidéo, le lien ou le titre du cours ;
2. conserver le PDF ;
3. conserver la transcription originale ;
4. noter les passages incertains ;
5. ne pas considérer automatiquement l’extraction PDF comme une transcription
   parfaite.

Le PDF sert à produire le vocabulaire et les phrases structurées. La
transcription sert à comprendre le contexte et à rédiger les notes personnelles.

### Étape 2 — Transformer le PDF Yoyo

Dans l’application locale :

1. ouvrir l’onglet `Yoyo Chinese (PDF)` ;
2. glisser-déposer le PDF ou sélectionner son chemin ;
3. cliquer sur `Convertir PDF & Exporter Anki` ;
4. suivre la console.

Le pipeline :

1. extrait le texte avec `pdftotext` ;
2. utilise `pypdf` en secours ;
3. repère vocabulaire, pinyin, caractères et phrases ;
4. conserve les caractères simplifiés ;
5. produit un Markdown ;
6. essaie une relecture Qwen via Ollama si disponible ;
7. génère l’audio ;
8. crée ou met à jour les notes Anki.

Le Markdown est enregistré :

- dans `output_markdown/` ;
- à côté du PDF d’origine.

L’importeur recherche une note possédant exactement le même `Hanzi` dans le
deck cible. Une réimportation peut donc mettre à jour une note existante au lieu
d’en créer une nouvelle.

### Étape 3 — Contrôler l’import PDF

Contrôler au moins quelques notes de chaque catégorie :

- bon Hanzi ;
- bon pinyin ;
- bonne traduction ;
- bonne phrase ;
- bon découpage vocabulaire/phrase ;
- bon audio ;
- bons tags ;
- absence de doublon indésirable.

Le parseur peut associer une mauvaise colonne lorsque le PDF est inhabituel. La
relecture humaine reste nécessaire.

### Étape 4 — Comprendre les tags PDF

Tags de base :

```text
chinois::source::yoyochinese
vocabulary
sentence
```

Le module `character_tagger.py` ajoute aussi des tags correspondant aux Hanzi,
et aux pinyins :

```text
chinois::caracteres::hanzi::<caractère>
chinois::caracteres::pinyin::<syllabe>
```

Les composants ne sont jamais calculés. Huaxia exige le tag explicite :

```text
chinois::caracteres::composant::<clé>
```

### Étape 5 — Écrire les notes personnelles dans Obsidian

Les notes personnelles doivent être créées sous :

```text
/Users/thomashusson/Documents/Projets/Docs_internat/Cours/
```

Ne pas les écrire dans :

```text
/Users/thomashusson/Documents/Projets/Docs_internat/Chinois/caracteres/
```

Le dossier `Chinois/caracteres` contient des fiches générées par Huaxia. Une
future exportation peut les réécrire entièrement.

### Étape 6 — Configurer Markdown vers Anki

Dans une note située sous `Cours/` :

1. utiliser `Cmd+Shift+A` ;
2. choisir `question-answer` ou `enhanced-cloze` ;
3. choisir le deck Anki ;
4. définir les tags ;
5. activer la synchronisation.

Exemple question/réponse :

```yaml
---
tags:
  - chinois
  - yoyo
  - oral
anki_type: question-answer
anki_deck: chinois::Notes personnelles
anki_enabled: true
---
```

Exemple Enhanced Cloze :

```yaml
---
tags:
  - chinois
  - yoyo
  - grammaire
anki_type: enhanced-cloze
anki_deck: TNCD::Enhanced Cloze
anki_enabled: true
---
```

### Étape 7 — Créer une carte question/réponse

Chaque titre de niveau 4 commence une carte :

```markdown
#### Comment demander si quelqu’un a déjà mangé ?

你吃饭了吗？

Signification : « As-tu déjà mangé ? »
```

Résultat :

- modèle `Généralités (alignées à gauche 1)` ;
- `Recto` : le titre ;
- `Verso` : le contenu jusqu’au prochain titre de niveau 1 à 4.

### Étape 8 — Créer une carte Enhanced Cloze

1. Sélectionner le passage complet.
2. Utiliser `Cmd+Shift+R`.
3. Sélectionner le texte à masquer.
4. Utiliser `Cmd+R`.

Exemple :

```markdown
<!-- anki:enhanced-cloze id="UUID" -->
Pour demander « As-tu mangé ? », on dit
{{c1::你吃饭了吗？::phrase interrogative}}.
<!-- /anki:enhanced-cloze -->
```

Ne pas modifier manuellement les UUID ou les empreintes `synced`.

### Étape 9 — Analyser puis synchroniser Markdown

Toujours commencer par :

```text
Markdown vers Anki : Analyser la note active sans modifier Anki
```

Puis :

```text
Markdown vers Anki : Synchroniser la note active vers Anki
```

À la fin de la session :

```text
Markdown vers Anki : Synchroniser toutes les notes vers Anki
```

La synchronisation globale détecte aussi les notes orphelines.

Les tags sont fusionnés :

```text
tags Anki existants ∪ tags YAML ∪ tag technique _mdanki
```

Retirer un tag du YAML ne le retire pas automatiquement d’Anki.

### Étape 10 — Gérer l’audio

#### Cartes créées par le PDF

Le pipeline PDF génère déjà l’audio. Ne pas lancer HyperTTS sans vérifier le
champ `Audio`.

Si le champ contient déjà :

```text
[sound:audio_zh_....mp3]
```

HyperTTS peut ajouter un second son, car le preset actuel insère après le
contenu existant.

Utiliser HyperTTS seulement si :

- l’audio manque ;
- la prononciation est incorrecte ;
- une variante différente est volontairement souhaitée.

Procédure :

1. ouvrir la note Yoyo ;
2. vérifier `Hanzi` ;
3. vérifier `Audio` ;
4. prévisualiser avec HyperTTS ;
5. écouter attentivement les tons ;
6. appliquer seulement si le résultat est correct.

Une réimportation du PDF réécrit le champ `Audio`. Un son HyperTTS ajouté
manuellement peut donc disparaître lors d’une réimportation ultérieure.

#### Notes gérées par Markdown vers Anki

Le moteur Markdown gère :

- `Recto` et `Verso` ;
- ou `Content` pour Enhanced Cloze ;
- les images ;
- les fichiers audio locaux MP3, WAV, M4A, AAC, FLAC, OGG, Opus et WebM.

Placer le fichier dans un dossier voisin, par exemple `audio/`, puis écrire :

```markdown
Par exemple : {{c2::他 (tā)::}}

![](audio/audio_zh_他.mp3)
```

À la synchronisation, le moteur copie le fichier dans les médias Anki et
insère une balise `[sound:mdanki_....mp3]` dans `Content`. L’add-on Huaxia
associe ce son à la cloze visible qui le précède immédiatement : dans cet
exemple, le son est entendu sur `c2`. Un son placé avant la première cloze est
commun à toutes les clozes de la note.

Le fichier Markdown reste la source principale. Écrire ensuite un son HyperTTS
directement dans `Recto`, `Verso` ou `Content` modifie seulement la version
Anki et peut créer un conflit à la synchronisation suivante. Pour ces notes,
préférer donc le lien audio local dans le Markdown.

### Étape 11 — Trouver une image mnémotechnique

Pour une image trouvée sur Internet :

1. vérifier sa licence ou son autorisation d’usage ;
2. télécharger le fichier original ;
3. conserver l’URL de provenance ;
4. préférer une image lisible et simple ;
5. éviter une image contenant une information erronée.

La bibliothèque centrale possède un champ `Source`. Le bouton `🧠+` inscrit
actuellement `manuel`. Après création, ouvrir la note centrale et remplacer ou
compléter `Source` avec l’URL.

### Étape 12 — Ajouter la mnémotechnique dans Anki

Dans `Parcourir` :

1. ouvrir une note Yoyo ;
2. coller l’image dans un champ, généralement `MnemoAuto` ;
3. cliquer une fois sur l’image pour la sélectionner ;
4. cliquer sur `🧠+` ;
5. choisir le type de lien ;
6. choisir la clé ;
7. saisir une description courte ;
8. lire le nombre de notes correspondantes ;
9. confirmer.

Types de lien :

#### Caractère

```text
TypeLien = caractere
Cle = 木
```

Correspond à toute occurrence visible dans `Hanzi` ou `Traditional`.

#### Mot

```text
TypeLien = mot
Cle = 木耳
```

Correspond à la séquence exacte, même incluse dans une phrase.

#### Composant

```text
TypeLien = composant
Cle = 亻
```

Correspond uniquement aux notes portant :

```text
chinois::caracteres::composant::亻
```

Le bouton ajoute ce tag à la note courante lors de la création du composant.
Les autres notes doivent recevoir explicitement le même tag.

### Étape 13 — Bibliothèque centrale Huaxia

Chaque mnémotechnique créée devient une note dans :

```text
chinois::mnemonics
```

Champs :

```text
MnemoId
TypeLien
Cle
Contenu
Description
Source
```

Règles :

- un `MnemoId` doit rester stable ;
- chaque mnémotechnique possède un seul type et une seule clé ;
- plusieurs mnémotechniques peuvent partager la même clé ;
- ne pas modifier arbitrairement `MnemoId` ;
- une suppression centrale est répercutée à la prochaine régénération des
  notes cibles.

Les notes de `chinois::chineasy_characters` servent aussi de sources
mnémotechniques. Une image d’une note ChinEasy n’est pas recopiée sur elle-même.

### Étape 14 — Utiliser les boutons Huaxia

#### `🧠?`

Prévisualise :

- les associations trouvées ;
- les mnémotechniques à inclure ;
- les doublons évités ;
- les avertissements ;
- la nécessité ou non d’une modification.

Aucune écriture.

#### `🧠✓`

Affiche l’aperçu, demande confirmation, puis régénère seulement la zone
automatique de `MnemoAuto`.

#### `🧠+`

Réutilise l’image sélectionnée, crée la note centrale et applique le résultat à
la note ouverte.

Menu disponible :

```text
Outils → Huaxia Mnémotechniques
```

Actions :

- `Initialiser / migrer…` ;
- `Prévisualiser la note en cours` ;
- `Appliquer à la note en cours…` ;
- `Synchroniser tout le modèle Yoyo…`.

### Étape 15 — Comprendre la protection de `MnemoAuto`

Le champ peut contenir :

- du contenu manuel historique ;
- un bloc appartenant à l’importeur PDF/Chineasy ;
- un bloc appartenant à Huaxia.

Marqueurs :

```html
<!-- HUAXIA_MNEMO_IMPORT_START -->
...
<!-- HUAXIA_MNEMO_IMPORT_END -->
```

```html
<!-- HUAXIA_MNEMO_AUTO_START -->
...
<!-- HUAXIA_MNEMO_AUTO_END -->
```

L’importeur ne doit remplacer que son propre bloc. Huaxia ne doit régénérer que
son propre bloc.

La déduplication utilise :

- `MnemoId` ;
- nom du média ;
- contenu déjà affiché.

### Étape 16 — Export automatique vers Obsidian

Configuration :

```json
{
  "trialMode": true,
  "obsidianAutoExport": true,
  "obsidianCharactersDir": "/Users/thomashusson/Documents/Projets/Docs_internat/Chinois/caracteres"
}
```

Après une modification effective de `MnemoAuto` par Huaxia :

1. la note Anki est mise à jour ;
2. sa fiche Obsidian est recherchée via `anki_note_id` ;
3. la fiche est mise à jour ou créée ;
4. les images de `MnemoAuto` sont copiées vers `media/` ;
5. les sons de `Audio` sont copiés vers `media/` ;
6. Obsidian Bases actualise la vue.

Base :

```text
/Users/thomashusson/Documents/Projets/Docs_internat/Chinois/caracteres/00_Base_de_Donnees_Caracteres.md
```

Vue :

```text
00_Base_de_Donnees_Caracteres.base
```

Une nouvelle clé peut donc produire une nouvelle fiche si aucune fiche ne
correspond encore à son identifiant Anki.

Limite importante : l’exporteur Huaxia actuel reconstruit le fichier Markdown
en entier. Considérer `Chinois/caracteres` comme un dossier généré. Écrire les
notes personnelles sous `Cours/`.

Un changement effectué uniquement par HyperTTS ne déclenche pas cet export.
L’événement est actuellement lié aux écritures Huaxia dans `MnemoAuto`.

### Étape 17 — Synchronisation globale Huaxia

La synchronisation globale est encore désactivée :

```json
"trialMode": true
```

Avant de la déverrouiller, valider :

- un caractère ;
- un mot inclus dans une phrase ;
- un composant explicitement tagué ;
- deux mnémotechniques sur une même clé ;
- la modification d’une note centrale ;
- la suppression d’une note centrale ;
- la conservation du contenu manuel ;
- l’absence de doublons ;
- la création et la mise à jour Obsidian.

Une fois le mode essai désactivé, l’action globale :

1. calcule les notes modifiées ;
2. affiche leur nombre ;
3. demande confirmation ;
4. crée une sauvegarde Anki ;
5. met à jour les notes ;
6. exporte vers Obsidian uniquement les notes modifiées.

Ne jamais désactiver `trialMode` simplement pour contourner un problème
d’aperçu.

### Étape 18 — Synchroniser AnkiWeb

À la fin de la session :

1. cliquer sur `Synchroniser` dans Anki Desktop ;
2. attendre la fin de la synchronisation de la collection ;
3. attendre la fin de la synchronisation des médias ;
4. ouvrir AnkiMobile ;
5. lancer la synchronisation ;
6. vérifier une image et un son sur mobile.

Anki synchronise les médias référencés par les notes si la synchronisation des
sons et images est activée.

## 6. Les trois familles de tags

### 6.1 Tags éditoriaux Obsidian

Exemples :

```text
chinois/caracteres/hanzi/木
chinois/caracteres/pinyin/mù
chinois/source/chineasy
```

Ils organisent la base Obsidian. Markdown-to-Anki convertit automatiquement
les `/` d’Obsidian en `::` dans Anki.

### 6.2 Tags Markdown vers Anki

Les tags du YAML sont fusionnés dans Anki.

Le moteur ajoute aussi un identifiant technique :

```text
_mdanki::<vault_uuid>::<note_uuid>
```

Ne pas modifier ce tag à la main.

### 6.3 Tags Huaxia de composants

Format obligatoire :

```text
chinois::caracteres::composant::<clé>
```

Ils doivent être ajoutés uniquement lorsque le composant est réellement
présent. Huaxia ne devine jamais les composants à partir des autres tags.

## 7. Propriétaires des données

| Donnée | Source principale |
|---|---|
| Révisions, intervalles, suspensions et statistiques | Anki |
| Vocabulaire et phrases extraits du PDF | Application locale puis Anki |
| Notes personnelles de cours | Markdown sous `Cours/` |
| Cartes Q/R et Clozes personnelles | Markdown vers Anki |
| Mnémotechniques centrales | `chinois::mnemonics` dans Anki |
| Blocs propagés dans `MnemoAuto` | Huaxia |
| Fiches `Chinois/caracteres` | Export Huaxia |
| Audio Yoyo importé | Application PDF |
| Audio de remplacement manuel | HyperTTS |
| Audio des cartes Q/R et Clozes personnelles | Fichier local référencé dans le Markdown |
| Synchronisation entre appareils | AnkiWeb |

Ne pas éditer simultanément la même donnée depuis deux sources principales.

## 8. Checklist quotidienne

### Avant

- [ ] Anki Desktop est ouvert sur `Utilisateur 1`.
- [ ] AnkiConnect répond sur le port `8766`.
- [ ] Le serveur local fonctionne sur le port `5001`.
- [ ] Le PDF et la transcription sont conservés.

### Après import PDF

- [ ] Hanzi vérifiés.
- [ ] Pinyin vérifiés.
- [ ] Traductions vérifiées.
- [ ] Phrases vérifiées.
- [ ] Audio vérifié.
- [ ] Tags de cours vérifiés.
- [ ] Doublons vérifiés.

### Pour les notes Obsidian

- [ ] Fichier placé sous `Cours/`.
- [ ] `anki_enabled: true`.
- [ ] Bon `anki_type`.
- [ ] Bon `anki_deck`.
- [ ] Tags cohérents.
- [ ] Analyse sans écriture effectuée.
- [ ] Synchronisation active effectuée.

### Pour HyperTTS

- [ ] Champ `Audio` vérifié avant ajout.
- [ ] Aucun doublon sonore.
- [ ] Tons et lecture vérifiés.
- [ ] Aucun champ géré par Markdown modifié sans stratégie de conflit.

### Pour une mnémotechnique

- [ ] Image licite et source conservée.
- [ ] Image sélectionnée avant `🧠+`.
- [ ] Type de lien correct.
- [ ] Clé correcte.
- [ ] Description courte.
- [ ] Source renseignée dans la bibliothèque.
- [ ] Aperçu contrôlé.
- [ ] Une seule note appliquée en mode essai.
- [ ] Fiche Obsidian vérifiée.

### Fin de session

- [ ] Conflits Markdown traités.
- [ ] Orphelines Markdown examinées.
- [ ] Synchronisation AnkiWeb terminée.
- [ ] Synchronisation des médias terminée.
- [ ] Contrôle sur AnkiMobile.

## 9. Dépannage

### L’application locale ne démarre pas

Vérifier :

```bash
cd /Users/thomashusson/Documents/Projets/huaxia/anki_characters/chineasy_to_anki
.venv/bin/python --version
.venv/bin/python app.py
```

### AnkiConnect est indisponible

Vérifier :

1. Anki ouvert ;
2. profil `Utilisateur 1` ;
3. AnkiConnect activé ;
4. port `8766` ;
5. absence d’un autre programme occupant le port.

### Le PDF n’est pas extrait correctement

Vérifier :

```bash
pdftotext -v
```

Puis contrôler le Markdown produit dans `output_markdown`.

### Ollama ne répond pas

Ollama est facultatif. L’absence de serveur ne doit pas empêcher l’extraction.
Pour l’utiliser, lancer le serveur et vérifier que le modèle demandé par
`yoyo_parser.py` est disponible.

### Aucun audio n’est produit

Vérifier :

- connexion Internet ;
- Youdao/Baidu accessibles ;
- `edge-tts` et `gTTS` installés ;
- pont HyperTTS pointant vers le bon environnement ;
- texte chinois non vide.

### HyperTTS ajoute deux sons

Le preset actuel ajoute après le contenu. Nettoyer ou contrôler `Audio` avant
d’appliquer HyperTTS.

### Markdown vers Anki signale un conflit après HyperTTS

HyperTTS a probablement modifié `Recto`, `Verso` ou `Content`. Comparer les
versions dans le gestionnaire de conflits et conserver la bonne version. Ne pas
répéter ce workflow avant d’avoir un champ audio séparé.

### `🧠+` ne trouve aucune image

Cliquer d’abord sur une image réellement présente dans l’éditeur Anki. Le
fichier doit exister dans `collection.media`.

### Une mnémotechnique de composant ne se propage pas

Vérifier le tag exact :

```text
chinois::caracteres::composant::<clé>
```

Un tag simple comme `亻`, `racine/亻` ou `composant/亻` n’est pas suffisant.
Dans Obsidian, écrire `chinois/caracteres/composant/亻`.

### La fiche Obsidian n’est pas créée

Vérifier :

- `obsidianAutoExport: true` ;
- chemin `obsidianCharactersDir` ;
- note possédant `Hanzi` et `MnemoAuto` ;
- droits d’écriture du dossier ;
- message de confirmation Huaxia.

### Du texte manuel Obsidian a disparu

Les fiches `Chinois/caracteres` sont actuellement régénérées entièrement.
Restaurer le texte depuis l’historique du coffre, puis le déplacer sous
`Cours/` jusqu’à l’implémentation de blocs Obsidian protégés.

## 10. Limites et évolutions à prévoir

Priorités techniques :

1. préserver le contenu manuel dans les fiches Obsidian avec des marqueurs
   `HUAXIA_MNEMO_START/END` et `HUAXIA_AUDIO_START/END` ;
2. ajouter une action `Exporter la note courante vers Obsidian` indépendante
   d’une modification de `MnemoAuto` ;
3. déclencher un export après une modification HyperTTS ;
4. créer un modèle Markdown chinois avec un champ audio séparé si des usages
   futurs doivent rester indépendants du contenu Markdown ;
5. ajouter `pypdf` à `requirements.txt` ;
6. aligner ou retirer l’ancien bouton serveur `Synchroniser vers Obsidian` ;
7. remplacer les chemins HyperTTS absolus par une configuration portable ;
8. compléter la validation avant de désactiver `trialMode`.

## 11. Résumé de la bonne routine

```text
1. Ouvrir Anki.
2. Démarrer l’application locale.
3. Regarder le cours et conserver la transcription.
4. Importer le PDF.
5. Contrôler les cartes et l’audio.
6. Rédiger les notes personnelles sous Obsidian/Cours.
7. Analyser et synchroniser avec Markdown vers Anki.
8. Utiliser HyperTTS seulement si un audio Yoyo manque ou est incorrect.
9. Ajouter les images mnémotechniques avec 🧠+.
10. Prévisualiser avec 🧠?.
11. Appliquer avec 🧠✓ en mode essai.
12. Vérifier la fiche Obsidian générée.
13. Traiter les conflits éventuels.
14. Synchroniser AnkiWeb et les médias.
15. Vérifier sur AnkiMobile.
```
