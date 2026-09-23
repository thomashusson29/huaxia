#!/usr/bin/env python3
"""Minimal local Flask interface for downloading Le Chinois Facile lessons."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from flask import Flask, render_template_string, request


DOWNLOADER = Path(
    "/Users/thomashusson/.codex/skills/download-chinois-facile/scripts/download_lesson.py"
)
OUTPUT_ROOT = Path(
    "/Users/thomashusson/Documents/Projets/huaxia/lechinoisfacile"
)
OBSIDIAN_ROOT = Path(
    "/Users/thomashusson/Documents/Projets/Docs_internat/Chinois/chinois_facile"
)

app = Flask(__name__)

PAGE = """<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Télécharger une leçon de chinois</title>
</head>
<body>
  <h1>Télécharger une leçon</h1>

  <form method="post">
    <label for="url">URL de la leçon</label><br>
    <input
      id="url"
      name="url"
      type="url"
      size="90"
      required
      autofocus
      placeholder="https://www.lechinoisfacile.fr/cours/.../lecon/.../"
      value="{{ url }}"
    >
    <button type="submit">Télécharger</button>
  </form>

  {% if error %}
    <h2>Erreur</h2>
    <pre>{{ error }}</pre>
  {% endif %}

  {% if result %}
    <h2>Téléchargement terminé</h2>
    <p>Markdown : {{ result.lesson }}</p>
    <p>Obsidian : {{ result.obsidian_lesson }}</p>
    <p>Archive ZIP : {{ result.archive }}</p>
    <p>Images : {{ result.images }} — Audios : {{ result.audio }}</p>

    <h2>Contenu du fichier Markdown</h2>
    <pre>{{ markdown_content }}</pre>
  {% endif %}
</body>
</html>
"""


class InterfaceError(RuntimeError):
    pass


def _read_summary(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise InterfaceError("Le téléchargeur n’a retourné aucun résultat.")
    try:
        summary = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise InterfaceError("Le résultat du téléchargeur est illisible.") from exc
    if not isinstance(summary, dict):
        raise InterfaceError("Le résultat du téléchargeur est invalide.")
    return summary


def _lesson_path(summary: dict[str, Any]) -> Path:
    raw_path = summary.get("lesson")
    if not isinstance(raw_path, str) or not raw_path:
        raise InterfaceError("Le chemin du Markdown est absent du résultat.")
    lesson = Path(raw_path).expanduser().resolve()
    output_root = OUTPUT_ROOT.expanduser().resolve()
    if not lesson.is_relative_to(output_root):
        raise InterfaceError("Le Markdown retourné se trouve hors du dossier autorisé.")
    if not lesson.is_file():
        raise InterfaceError(f"Le Markdown créé est introuvable : {lesson}")
    return lesson


def download_lesson(url: str) -> tuple[dict[str, Any], str]:
    if not DOWNLOADER.is_file():
        raise InterfaceError(f"Téléchargeur introuvable : {DOWNLOADER}")
    command = [
        sys.executable,
        str(DOWNLOADER),
        url,
        "--output-root",
        str(OUTPUT_ROOT),
        "--obsidian-root",
        str(OBSIDIAN_ROOT),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise InterfaceError("Le téléchargement a dépassé 15 minutes.") from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or "Le téléchargement a échoué."
        raise InterfaceError(message)
    summary = _read_summary(completed.stdout)
    markdown_path = _lesson_path(summary)
    try:
        markdown_content = markdown_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InterfaceError(f"Impossible de lire le Markdown créé : {exc}") from exc
    return summary, markdown_content


@app.route("/", methods=["GET", "POST"])
def index():
    url = ""
    result = None
    markdown_content = ""
    error = ""
    if request.method == "POST":
        url = request.form.get("url", "").strip()
        if not url:
            error = "Collez l’URL complète d’une leçon."
        else:
            try:
                result, markdown_content = download_lesson(url)
            except InterfaceError as exc:
                error = str(exc)
    return render_template_string(
        PAGE,
        url=url,
        result=result,
        markdown_content=markdown_content,
        error=error,
    )


if __name__ == "__main__":
    port = int(os.environ.get("LCF_PORT", "5050"))
    app.run(host="127.0.0.1", port=port, debug=False)
