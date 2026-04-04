from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Optional

import pygame
import requests

from src.services.tts.base import TTSProvider
from src.services.tts.piper_provider import PiperTTSProvider


class HybridTTSProvider(TTSProvider):
    """
    Integrated provider inspired by Hackbyte's service:
    - prefers ElevenLabs when internet + key are available
    - safely falls back to local Piper for reliability
    """

    def __init__(self, fallback: PiperTTSProvider) -> None:
        self._fallback = fallback
        self._last_check = 0.0
        self._internet_ok = True
        self._check_interval_s = float(os.getenv("INTERNET_CHECK_INTERVAL_S", "5"))
        self._eleven_api_key = os.getenv("ELEVENLABS_API_KEY")
        self._eleven_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
        self._eleven_model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

    def _is_internet_available(self) -> bool:
        now = time.time()
        if (now - self._last_check) < self._check_interval_s:
            return self._internet_ok
        try:
            requests.get("https://www.google.com", timeout=2)
            self._internet_ok = True
        except Exception:
            self._internet_ok = False
        self._last_check = now
        return self._internet_ok

    def _try_elevenlabs(self, text: str, voice_id: Optional[str] = None) -> bool:
        if not self._eleven_api_key or not self._is_internet_available():
            return False

        headers = {
            "xi-api-key": self._eleven_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self._eleven_model_id,
        }
        target_voice = voice_id or self._eleven_voice_id
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{target_voice}"

        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code != 200:
            return False

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(response.content)
            mp3_path = Path(f.name)
        try:
            pygame.mixer.music.load(str(mp3_path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()
            return True
        finally:
            try:
                if mp3_path.exists():
                    mp3_path.unlink()
            except Exception:
                pass

    def speak(
        self,
        text: str,
        *,
        timestamp: Optional[float] = None,
        voice_id: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        _ = (timestamp, language)
        try:
            if self._try_elevenlabs(text, voice_id=voice_id):
                return
        except Exception:
            # Integration decision: keep speech path resilient by failing back to Piper.
            pass
        self._fallback.speak(text, timestamp=timestamp, voice_id=voice_id, language=language)
