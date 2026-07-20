"""
Module de génération audio mandarin haute fidélité pour Anki.
Interroge en priorité les bases vocales de dictionnaire chinois (Youdao / Baidu)
avec traçabilité explicite de la source (Humain vs Fallback TTS).
"""

import os
import requests
import asyncio
from typing import Optional

def generate_audio_youdao(word: str, output_path: str) -> bool:
    """Télécharge l'enregistrement humain du dictionnaire Youdao."""
    try:
        url = f"http://dict.youdao.com/dictvoice?audio={word}&le=zh"
        res = requests.get(url, timeout=4)
        if res.status_code == 200 and len(res.content) > 2000:
            with open(output_path, "wb") as f:
                f.write(res.content)
            return True
    except Exception:
        pass
    return False

def generate_audio_baidu(word: str, output_path: str) -> bool:
    """Télécharge l'enregistrement de dictionnaire Baidu Fanyi."""
    try:
        url = f"https://fanyi.baidu.com/gettts?lan=zh&text={word}&spd=3&source=web"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200 and len(res.content) > 2000:
            with open(output_path, "wb") as f:
                f.write(res.content)
            return True
    except Exception:
        pass
    return False

async def _generate_edge_tts_async(word: str, output_path: str) -> bool:
    """Fallback Edge-TTS ralenti (-20%)."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(word, "zh-CN-XiaoxiaoNeural", rate="-20%")
        await communicate.save(output_path)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception:
        return False

def generate_audio_sync(word: str, output_path: str) -> Optional[str]:
    """
    Génère l'audio MP3 pour un caractère ou mot composé chinois.
    Affiche explicitement la source utilisée (Dictionnaire Youdao HD vs Fallback).
    """
    if not word:
        return None
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 1. Priorité Youdao (Enregistrement de dictionnaire humain)
    if generate_audio_youdao(word, output_path):
        print(f"  [Audio] '{word}' -> Source : Dictionnaire humain Youdao HD")
        return output_path
        
    # 2. Secondaire Baidu Dictionary
    if generate_audio_baidu(word, output_path):
        print(f"  [Audio] '{word}' -> Source : Dictionnaire Baidu Speech")
        return output_path
        
    # 3. Fallback Edge-TTS
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.run_complete(_generate_edge_tts_async(word, output_path)):
        print(f"  [Audio Fallback] '{word}' -> Source : Synthèse Edge-TTS Neural (-20%)")
        return output_path
        
    # 4. Secours ultime gTTS
    try:
        from gtts import gTTS
        tts = gTTS(text=word, lang='zh-CN', slow=True)
        tts.save(output_path)
        print(f"  [Audio Fallback] '{word}' -> Source : gTTS")
        return output_path
    except Exception as e:
        print(f"  [Audio Error] Impossible de générer l'audio pour '{word}': {e}")
        return None

if __name__ == "__main__":
    import sys
    w = sys.argv[1] if len(sys.argv) > 1 else "火山"
    out = "test_audio.mp3"
    res = generate_audio_sync(w, out)
    print("Résultat:", res)
