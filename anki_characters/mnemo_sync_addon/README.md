# Huaxia Mnémotechniques

Add-on local pour Anki 25.07.5. Il centralise les mnémotechniques reliées à un
caractère, un mot ou un composant explicite, puis génère uniquement le bloc
`HUAXIA_MNEMO_AUTO` du champ `MnemoAuto`.

La migration et toute synchronisation sont déclenchées explicitement depuis le
menu **Outils → Huaxia Mnémotechniques**. Aucune synchronisation globale n’est
lancée au démarrage.

Les notes de `chinois::chineasy_characters` sont à la fois des sources
mnémotechniques et des cibles utilisables avec les boutons de l’éditeur. Lors du
rendu d’une note ChinEasy, seule sa propre entrée source est exclue afin de ne
pas recopier son image historique sur elle-même.

Pour créer une mnémotechnique, cliquer d’abord sur une image déjà présente dans
un champ de l’éditeur Anki, puis sur `🧠+`. L’add-on réutilise directement ce
fichier média et demande seulement le type de lien, la clé et la description.

Les composants sont toujours déclarés explicitement avec
`chinois::caracteres::composant::<clé>`. Une nouvelle note de bibliothèque
reçoit également un tag dérivé de ses champs, par exemple
`chinois::mnemonique::type::caractere::cle::电`.

Le greffon filtre également l’autoplay du modèle `Enhanced Cloze 2.1 v2`.
Chaque balise `[sound:…]` du champ `Content` est associée à la Cloze qui la
précède : seule la piste de la carte courante est lue, et les répétitions
produites par les rendus internes du modèle sont supprimées. Un son placé avant
la première Cloze reste global.
