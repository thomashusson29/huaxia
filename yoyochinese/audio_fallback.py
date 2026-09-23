#!/usr/bin/env python3
"""Fallback Mandarin audio providers used when Yoyo has no source file."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


MIN_AUDIO_BYTES = 1_000
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"


def _download(url: str, output_path: Path, *, timeout: int = 15) -> bool:
    temporary = output_path.with_name(output_path.name + ".fallback.part")
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "audio/*,*/*"})
        with urlopen(request, timeout=timeout) as response:
            content = response.read()
        if len(content) < MIN_AUDIO_BYTES:
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(content)
        os.replace(temporary, output_path)
        return True
    except (HTTPError, URLError, TimeoutError, OSError):
        return False
    finally:
        if temporary.exists():
            temporary.unlink()


def generate_youdao(text: str, output_path: Path) -> bool:
    url = f"https://dict.youdao.com/dictvoice?audio={quote(text)}&le=zh"
    return _download(url, output_path)


def generate_baidu(text: str, output_path: Path) -> bool:
    url = (
        "https://fanyi.baidu.com/gettts?lan=zh&spd=3&source=web&text="
        + quote(text)
    )
    return _download(url, output_path)


async def _generate_edge_async(text: str, output_path: Path) -> bool:
    try:
        import edge_tts

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(output_path.name + ".fallback.part")
        communicate = edge_tts.Communicate(
            text,
            "zh-CN-XiaoxiaoNeural",
            rate="-20%",
        )
        await communicate.save(str(temporary))
        if temporary.is_file() and temporary.stat().st_size >= MIN_AUDIO_BYTES:
            os.replace(temporary, output_path)
            return True
    except Exception:
        pass
    finally:
        temporary = output_path.with_name(output_path.name + ".fallback.part")
        if temporary.exists():
            temporary.unlink()
    return False


def generate_edge_tts(text: str, output_path: Path) -> bool:
    try:
        return asyncio.run(_generate_edge_async(text, output_path))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_generate_edge_async(text, output_path))
        finally:
            loop.close()


def generate_gtts(text: str, output_path: Path) -> bool:
    temporary = output_path.with_name(output_path.name + ".fallback.part")
    try:
        from gtts import gTTS

        output_path.parent.mkdir(parents=True, exist_ok=True)
        gTTS(text=text, lang="zh-CN", slow=False).save(str(temporary))
        if temporary.is_file() and temporary.stat().st_size >= MIN_AUDIO_BYTES:
            os.replace(temporary, output_path)
            return True
    except Exception:
        return False
    finally:
        if temporary.exists():
            temporary.unlink()
    return False


PROVIDERS: tuple[tuple[str, Callable[[str, Path], bool]], ...] = (
    ("youdao", generate_youdao),
    ("baidu", generate_baidu),
    ("edge_tts", generate_edge_tts),
    ("gtts", generate_gtts),
)


def generate_fallback_audio(text: str, output_path: str | Path) -> str | None:
    """Return the first successful provider name, in the required order."""
    text = text.strip()
    path = Path(output_path)
    if not text:
        return None
    for provider, generator in PROVIDERS:
        if generator(text, path):
            return provider
    return None
