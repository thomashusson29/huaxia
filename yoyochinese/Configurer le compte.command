#!/bin/zsh

SCRIPT_DIR=${0:A:h}
cd "$SCRIPT_DIR" || exit 1

python3 "$SCRIPT_DIR/configure_keychain.py"
YOYO_STATUS=$?

echo
if [[ $YOYO_STATUS -eq 0 ]]; then
  echo "Le compte est configuré. Le téléchargeur se connectera automatiquement."
else
  echo "La configuration a échoué."
fi
read -k 1 "?Appuyez sur une touche pour fermer."
exit $YOYO_STATUS
