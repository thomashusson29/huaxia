"""
Module de génération audio automatique pour la prononciation exacte des tons mandarins.
Utilise en priorité les dictionnaires audio chinois (Youdao / Baidu) spécialement conçus 
pour la déclinaison exacte des 4 tons mandarins, avec repli sur Edge-TTS (-20% vitesse) et gTTS.
"""

import os
import asyncio
import requests
from typing import Optional

def fetch_youdao_dictionary_audio(text: str, output_path: str) -> bool:
    """
    Récupère la prononciation du dictionnaire chinois Youdao (distinction exacte des 4 tons).
    """
    try:
        url = f"https://dict.youdao.com/dictvoice?audio={text}&le=zh"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200 and len(response.content) > 2000:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
    except Exception as e:
        print(f"[Audio Youdao] Erreur pour '{text}': {e}")
    return False

def fetch_baidu_speech_audio(text: str, output_path: str) -> bool:
    """
    Récupère la prononciation du dictionnaire Baidu avec vitesse d'apprentissage contrôlée (spd=3).
    """
    try:
        url = f"https://fanyi.baidu.com/gettts?lan=zh&text={text}&spd=3&source=web"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200 and len(response.content) > 2000:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
    except Exception as e:
        print(f"[Audio Baidu] Erreur pour '{text}': {e}")
    return False

def generate_edge_tts_slow(text: str, output_path: str) -> bool:
    """
    Génère un audio Edge-TTS avec un débit ralenti (-20%) pour laisser le ton mandarin s'exprimer pleinement.
    """
    try:
        import edge_tts
        
        async def _async_generate():
            # Voice masculine Yunjian ou Yunxi à vitesse ralentie pour bien marquer le ton
            communicate = edge_tts.Communicate(text, 'zh-CN-YunjianNeural', rate='-20%')
            await communicate.save(output_path)
            
        asyncio.run(_async_generate())
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        print(f"[Audio Edge-TTS] Erreur pour '{text}': {e}")
    return False

def generate_audio_sync(text: str, output_path: str) -> Optional[str]:
    """
    Génère la prononciation audio MP3 avec respect strict des 4 tons mandarins.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 1. Dictionnaire Youdao (Prononciation humaine de dictionnaire)
    if fetch_youdao_dictionary_audio(text, output_path):
        return output_path
        
    # 2. Dictionnaire Baidu (Vitesse d'apprentissage spd=3)
    if fetch_baidu_speech_audio(text, output_path):
        return output_path
        
    # 3. Edge-TTS ralenti (-20%)
    if generate_edge_tts_slow(text, output_path):
        return output_path

    # 4. Secours gTTS
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang='zh-CN')
        tts.save(output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    except Exception as e:
        print(f"[Audio gTTS] Échec final pour '{text}': {e}")

    return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        res = generate_audio_sync(sys.argv[1], sys.argv[2])
        print(f"Audio généré : {res}")
