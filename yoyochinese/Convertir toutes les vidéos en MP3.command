#!/bin/zsh
set -u

SCRIPT_DIR="${0:A:h}"
ROOT="/Volumes/Husson/yoyo_chinese"

python3 "${SCRIPT_DIR}/video_to_mp3.py" "${ROOT}" --jobs 3
status=$?

echo
if (( status == 0 )); then
  echo "Conversion terminée sans erreur."
else
  echo "Conversion interrompue ou terminée avec des erreurs (code ${status})."
fi
echo "Appuyez sur Entrée pour fermer cette fenêtre."
read -r
exit "${status}"
