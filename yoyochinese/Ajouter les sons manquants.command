#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Préparation de l’environnement Python…"
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi

OUTPUT_DIR="$SCRIPT_DIR/generated_anki_audio"
if [[ -d "/Volumes/Husson/yoyo_chinese" ]]; then
  OUTPUT_DIR="/Volumes/Husson/yoyo_chinese/Generated Anki Audio"
fi

echo "Analyse des cartes du deck chinois…"
.venv/bin/python fill_missing_anki_audio.py --deck chinois --output-dir "$OUTPUT_DIR"
echo
read "REPLY?Ajouter les sons indiqués ci-dessus ? [o/N] "
echo
if [[ "$REPLY" != [oOyY]* ]]; then
  echo "Aucune modification effectuée."
  exit 0
fi

.venv/bin/python fill_missing_anki_audio.py \
  --deck chinois \
  --output-dir "$OUTPUT_DIR" \
  --apply
echo
echo "Terminé. Vous pouvez fermer cette fenêtre."
read -k 1 "REPLY?Appuyez sur une touche pour quitter…"
echo
