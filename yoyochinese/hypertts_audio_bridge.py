#!/usr/bin/env python3
"""Return fallback Mandarin MP3 bytes on stdout for the HyperTTS service."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from audio_fallback import generate_fallback_audio


def main() -> int:
    text = sys.stdin.read().strip()
    if not text:
        print("empty_text", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="hypertts-mandarin-") as temporary:
        output_path = Path(temporary) / "audio.mp3"
        provider = generate_fallback_audio(text, output_path)
        if provider is None or not output_path.is_file():
            print("no_provider", file=sys.stderr)
            return 3
        print(provider, file=sys.stderr)
        sys.stdout.buffer.write(output_path.read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
