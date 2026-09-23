#!/bin/zsh

SCRIPT_DIR=${0:A:h}
cd "$SCRIPT_DIR" || exit 1

YOYO_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [[ ! -x "$YOYO_PYTHON" ]]; then
  echo "Préparation de l’environnement Python (une seule fois)…"
  python3 -m venv "$SCRIPT_DIR/.venv" || exit 1
fi
if ! "$YOYO_PYTHON" -c "import genanki" >/dev/null 2>&1; then
  echo "Installation du petit module nécessaire à la création des paquets Anki…"
  "$YOYO_PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt" || exit 1
fi

if ! security find-generic-password -a default -s fr.yoyochinese.downloader.password -w >/dev/null 2>&1; then
  echo "Aucun compte Yoyo Chinese n’est configuré dans le Trousseau."
  echo "Lancez d’abord « Configurer le compte.command » pour accéder aux cours payants."
  echo
fi

echo "Collez l’URL Yoyo Chinese (leçon, unité, cours ou /courses) :"
read -r YOYO_INPUT_URL

if [[ -z "$YOYO_INPUT_URL" ]]; then
  echo "Aucune URL fournie."
  read -k 1 "?Appuyez sur une touche pour fermer."
  exit 1
fi

YOYO_EXTRA_ARGS=()

echo
echo "Que voulez-vous faire ?"
echo "  1 — Vérifier et afficher l’inventaire, sans télécharger"
echo "  2 — Tout exporter : vidéos, PDF et Anki"
echo "  3 — Exporter seulement les vidéos et PDF"
echo "  4 — Exporter seulement les flashcards Anki"
read -r "YOYO_MODE?Votre choix [1] : "
YOYO_MODE=${YOYO_MODE:-1}
case "$YOYO_MODE" in
  1) YOYO_EXTRA_ARGS+=(--dry-run) ;;
  2) ;;
  3) YOYO_EXTRA_ARGS+=(--no-anki) ;;
  4) YOYO_EXTRA_ARGS+=(--no-videos --no-pdfs) ;;
  *)
    echo "Choix invalide."
    read -k 1 "?Appuyez sur une touche pour fermer."
    exit 1
    ;;
esac

if [[ "$YOYO_INPUT_URL" == "https://yoyochinese.com/courses" || "$YOYO_INPUT_URL" == "https://yoyochinese.com/courses/" ]]; then
  echo "Le catalogue complet contient de nombreuses leçons. Tapez OUI pour confirmer :"
  read -r YOYO_CONFIRMATION
  if [[ "$YOYO_CONFIRMATION" != "OUI" ]]; then
    echo "Annulé."
    read -k 1 "?Appuyez sur une touche pour fermer."
    exit 1
  fi
  YOYO_EXTRA_ARGS+=(--all-courses)
fi

"$YOYO_PYTHON" "$SCRIPT_DIR/download_yoyo.py" "$YOYO_INPUT_URL" "${YOYO_EXTRA_ARGS[@]}"
YOYO_STATUS=$?

echo
if [[ $YOYO_STATUS -eq 0 ]]; then
  echo "Téléchargement terminé."
else
  echo "Le téléchargeur s’est terminé avec une erreur (code $YOYO_STATUS)."
fi
read -k 1 "?Appuyez sur une touche pour fermer."
exit $YOYO_STATUS
