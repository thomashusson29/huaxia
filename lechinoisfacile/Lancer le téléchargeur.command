#!/bin/zsh
set -eu

APP_DIR="/Users/thomashusson/Documents/Projets/huaxia/lechinoisfacile"
VENV_DIR="$APP_DIR/.venv"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi

if ! "$VENV_DIR/bin/python" -c "import flask" >/dev/null 2>&1; then
  "$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
fi

(
  sleep 1
  open "http://127.0.0.1:5050"
) &

exec "$VENV_DIR/bin/python" "$APP_DIR/app.py"
