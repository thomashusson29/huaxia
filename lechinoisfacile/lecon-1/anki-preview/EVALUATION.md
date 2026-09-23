# Évaluation du prototype local

**Statut : rejeté — ne pas synchroniser avec Anki.**

Les brouillons restent désactivés avec `anki_enabled: false`.

## `qwen3-vl:8b`

- structure JSON correcte lors du premier essai ;
- erreur de pinyin : `là` à la place de `nà` ;
- décomposition erronée de `人` ;
- questions répétitives ;
- images ignorées et audios utilisés sans véritable objectif d’écoute ;
- contraintes renforcées non respectées lors du second essai.

## `qwen2.5-coder:latest`

- structure JSON correcte ;
- aucune syntaxe Enhanced Cloze produite malgré la consigne ;
- images et audios mal exploités ;
- association erronée entre `人` et `shù` ;
- confusion entre la décomposition de `十` et celle de `木`.

## Conclusion

Les deux modèles installés ne sont pas assez fiables pour générer directement des
cartes publiables. La prochaine version devrait leur confier uniquement
l’extraction de faits sourcés. Les questions, clozes et associations de médias
seraient ensuite construites par des règles déterministes, avec une validation
humaine avant toute synchronisation.
