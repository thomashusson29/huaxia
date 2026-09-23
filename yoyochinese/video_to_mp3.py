#!/usr/bin/env python3
"""Create a verified MP3 sibling for every video below a directory."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi"}
MIN_MP3_BYTES = 1_000


@dataclass(frozen=True)
class ConversionResult:
    video: str
    mp3: str
    status: str
    seconds: float
    mp3_bytes: int = 0
    error: str | None = None


def find_videos(root: Path) -> list[Path]:
    videos = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in VIDEO_EXTENSIONS
        and not path.name.startswith("._")
    ]
    return sorted(videos, key=lambda path: str(path).casefold())


def mp3_is_valid(path: Path, ffprobe: str) -> bool:
    if not path.is_file() or path.stat().st_size < MIN_MP3_BYTES:
        return False
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return bool(streams) and streams[0].get("codec_name") == "mp3" and duration > 0


def convert_one(video: Path, ffmpeg: str, ffprobe: str, overwrite: bool) -> ConversionResult:
    started = time.monotonic()
    output = video.with_suffix(".mp3")
    temporary = output.with_name(f"{output.stem}.part.mp3")
    if not overwrite and mp3_is_valid(output, ffprobe):
        return ConversionResult(
            video=str(video),
            mp3=str(output),
            status="skipped",
            seconds=time.monotonic() - started,
            mp3_bytes=output.stat().st_size,
        )

    temporary.unlink(missing_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-map",
        "0:a:0",
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        "-map_metadata",
        "0",
        "-id3v2_version",
        "3",
        "-metadata",
        f"title={video.stem}",
        "-f",
        "mp3",
        str(temporary),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "FFmpeg a échoué").strip()
            raise RuntimeError(message[-2_000:])
        if not mp3_is_valid(temporary, ffprobe):
            raise RuntimeError("le MP3 produit n’a pas passé la vérification FFprobe")
        os.replace(temporary, output)
        source_stat = video.stat()
        os.utime(output, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
        return ConversionResult(
            video=str(video),
            mp3=str(output),
            status="created",
            seconds=time.monotonic() - started,
            mp3_bytes=output.stat().st_size,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        temporary.unlink(missing_ok=True)
        return ConversionResult(
            video=str(video),
            mp3=str(output),
            status="error",
            seconds=time.monotonic() - started,
            error=str(exc),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Créer un MP3 vérifié à côté de chaque vidéo. Les MP3 valides "
            "existants sont ignorés, ce qui permet de reprendre le traitement."
        )
    )
    parser.add_argument("root", type=Path, help="dossier racine à parcourir")
    parser.add_argument(
        "--jobs",
        type=int,
        default=3,
        help="nombre de conversions FFmpeg simultanées (défaut : 3)",
    )
    parser.add_argument("--limit", type=int, help="ne traiter que les N premières vidéos")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="recréer aussi les MP3 déjà valides",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="chemin du rapport JSON (défaut : ROOT/video_to_mp3_report.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"Erreur : dossier introuvable : {root}", file=sys.stderr)
        return 2
    if args.jobs < 1:
        print("Erreur : --jobs doit être supérieur à zéro.", file=sys.stderr)
        return 2
    if args.limit is not None and args.limit < 1:
        print("Erreur : --limit doit être supérieur à zéro.", file=sys.stderr)
        return 2

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        print("Erreur : FFmpeg et FFprobe doivent être installés.", file=sys.stderr)
        return 2

    videos = find_videos(root)
    if args.limit:
        videos = videos[: args.limit]
    total = len(videos)
    print(f"{total} vidéo(s) à examiner sous {root}", flush=True)
    if not videos:
        return 0

    lock = threading.Lock()
    completed = 0
    results: list[ConversionResult] = []
    started_at = datetime.now(timezone.utc)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {
            executor.submit(convert_one, video, ffmpeg, ffprobe, args.overwrite): video
            for video in videos
        }
        try:
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                with lock:
                    completed += 1
                    results.append(result)
                    relative = Path(result.video).relative_to(root)
                    if result.status == "error":
                        print(
                            f"[{completed}/{total}] ERREUR {relative} — {result.error}",
                            flush=True,
                        )
                    else:
                        print(
                            f"[{completed}/{total}] {result.status.upper()} "
                            f"{relative} ({result.mp3_bytes / 1_000_000:.1f} Mo)",
                            flush=True,
                        )
        except KeyboardInterrupt:
            print("\nInterruption demandée : arrêt des nouvelles conversions…", file=sys.stderr)
            for future in futures:
                future.cancel()
            return 130

    results.sort(key=lambda result: result.video.casefold())
    counts = {
        status: sum(result.status == status for result in results)
        for status in ("created", "skipped", "error")
    }
    report = {
        "root": str(root),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "video_count": total,
        "counts": counts,
        "mp3_bytes_created_or_found": sum(result.mp3_bytes for result in results),
        "results": [asdict(result) for result in results],
    }
    report_path = (args.report or root / "video_to_mp3_report.json").resolve()
    temporary_report = report_path.with_name(report_path.name + ".part")
    temporary_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_report, report_path)
    print(
        f"Terminé : {counts['created']} créé(s), {counts['skipped']} déjà valide(s), "
        f"{counts['error']} erreur(s).",
        flush=True,
    )
    print(f"Rapport : {report_path}", flush=True)
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
