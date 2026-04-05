from __future__ import annotations

import os
import tempfile
import time
import threading
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
    - natively supports preemption (kill switches) for high-priority events
    """

    def __init__(self, fallback: PiperTTSProvider) -> None:
        self._fallback = fallback
        self._last_check = 0.0
        self._internet_ok = True
        self._check_interval_s = float(os.getenv("INTERNET_CHECK_INTERVAL_S", "5"))
        self._eleven_api_key = os.getenv("ELEVENLABS_API_KEY")
        self._eleven_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "cgSgspJ2msm6clMCkdW9")
        self._eleven_model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
        
        # Preemption kill switch
        self._stop_event = threading.Event()
        
        print(f"[*] TTS Hybrid: Initialized. Fallback provider is '{type(fallback).__name__}'.")
        if not self._eleven_api_key:
            print("[!] TTS Hybrid: Missing ELEVENLABS_API_KEY. Cloud synthesis will be disabled.")

    def _is_internet_available(self) -> bool:
        now = time.time()
        if (now - self._last_check) < self._check_interval_s:
            return self._internet_ok
            
        print("[*] TTS Hybrid: Pinging google.com for connectivity check...")
        try:
            requests.get("https://www.google.com", timeout=2)
            if not self._internet_ok:
                print("[+] TTS Hybrid: Internet connectivity restored.")
            self._internet_ok = True
        except Exception:
            if self._internet_ok:
                print("[!] TTS Hybrid: Internet connectivity lost. Forcing local fallback.")
            self._internet_ok = False
            
        self._last_check = now
        return self._internet_ok

    def _try_elevenlabs(self, text: str, voice_id: Optional[str] = None) -> bool:
        if not self._eleven_api_key:
            return False
            
        if not self._is_internet_available():
            print("[-] TTS Hybrid: Skipping cloud synthesis (Offline).")
            return False

        # Abort before network request if preemption triggered
        if self._stop_event.is_set():
            print("[!] TTS Hybrid: Preempted before cloud request could fire.")
            return True 

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

        # Truncate text for cleaner console logs
        log_text = text if len(text) <= 40 else text[:37] + "..."
        print(f"[*] TTS Hybrid: Requesting cloud voice for: '{log_text}'")

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            if response.status_code != 200:
                print(f"[!] TTS Hybrid: ElevenLabs API Error (Code: {response.status_code}). Response: {response.text}")
                return False
        except requests.RequestException as e:
            print(f"[!] TTS Hybrid: Cloud request timed out or failed: {e}")
            return False

        # Abort before saving/playing if preemption triggered during network request
        if self._stop_event.is_set():
            print("[!] TTS Hybrid: Preempted while downloading cloud audio. Discarding file.")
            return True

        print("[+] TTS Hybrid: Cloud audio received successfully. Playing...")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(response.content)
            mp3_path = Path(f.name)
            
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
                
            pygame.mixer.music.load(str(mp3_path))
            pygame.mixer.music.play()
            
            # Wait for audio to finish, UNLESS the stop event is triggered
            while pygame.mixer.music.get_busy() and not self._stop_event.is_set():
                pygame.time.Clock().tick(10)
                
            pygame.mixer.music.unload()
            
            if self._stop_event.is_set():
                print("⚠️ [TTS Hybrid] Cloud audio forcefully stopped by kill switch!")
                
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
        self._stop_event.clear()
        
        try:
            if self._try_elevenlabs(text, voice_id=voice_id):
                return
        except Exception as e:
            print(f"[!] TTS Hybrid: Unexpected error in cloud pipeline: {e}")
            
        # If we reach here, ElevenLabs failed or internet was down. Hand off to Piper.
        print("[*] TTS Hybrid: Handing off text to local Piper fallback.")
        self._fallback.speak(text, timestamp=timestamp, voice_id=voice_id, language=language)

    def stop(self) -> None:
        """Instantly halts audio playback for both ElevenLabs and Piper fallback."""
        self._stop_event.set()
        
        # Stop ElevenLabs playback if it's currently active
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            
        # Pass the stop command down to the local fallback provider
        self._fallback.stop()
