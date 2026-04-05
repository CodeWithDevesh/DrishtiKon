from __future__ import annotations

import os
from pathlib import Path

from src.services.tts.base import TTSProvider
from src.services.tts.hybrid_provider import HybridTTSProvider
from src.services.tts.piper_provider import PiperTTSProvider, default_piper_voice_config


def build_tts_provider() -> TTSProvider:
    """
    TTS_BACKEND selection:
    - piper  : local-only baseline (system default behavior)
    - hybrid : ElevenLabs when available, otherwise Piper fallback
    - auto   : hybrid if ELEVENLABS_API_KEY exists else piper
    """
    tmp_wav = Path(os.getenv("SPEECH_TMP_WAV", "temp_speech.wav"))
    piper = PiperTTSProvider(default_piper_voice_config(), tmp_wav=tmp_wav)

    backend = os.getenv("TTS_BACKEND", "auto").strip().lower()
    print(f"[*] Resolving TTS provider for backend mode: '{backend}'")
    
    if backend == "piper":
        print("[+] TTS Factory: Selected 'piper' (Local-only Piper Voice).")
        return piper
        
    if backend == "hybrid":
        print("[+] TTS Factory: Selected 'hybrid' (ElevenLabs with Piper Fallback).")
        return HybridTTSProvider(fallback=piper)
        
    if backend == "auto":
        has_key = bool(os.getenv("ELEVENLABS_API_KEY"))
        if has_key:
            print("[+] TTS Factory: Auto-mode detected ElevenLabs API key. Using Hybrid provider.")
            return HybridTTSProvider(fallback=piper)
        else:
            print("[+] TTS Factory: Auto-mode found no API key. Defaulting to local Piper provider.")
            return piper
            
    print(f"[!] TTS Factory Error: Invalid TTS_BACKEND configuration: '{backend}'")
    raise ValueError(f"Unsupported TTS_BACKEND={backend!r}. Use piper, hybrid, or auto.")
