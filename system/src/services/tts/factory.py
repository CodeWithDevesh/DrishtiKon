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

    backend = os.getenv("TTS_BACKEND", "piper").strip().lower()
    if backend == "piper":
        return piper
    if backend == "hybrid":
        return HybridTTSProvider(fallback=piper)
    if backend == "auto":
        has_key = bool(os.getenv("ELEVENLABS_API_KEY"))
        return HybridTTSProvider(fallback=piper) if has_key else piper
    raise ValueError(f"Unsupported TTS_BACKEND={backend!r}. Use piper, hybrid, or auto.")
