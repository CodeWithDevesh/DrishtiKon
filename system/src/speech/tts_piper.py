"""
Compatibility bridge for legacy imports.

Integrated implementation now lives in src.services.tts.piper_provider.
"""

from pathlib import Path

from src.services.tts.piper_provider import PiperTTSProvider, PiperVoiceConfig, default_piper_voice_config


class PiperTTS(PiperTTSProvider):
    # Keep old call signature so legacy callers still work.
    def speak(self, text: str, tmp_wav: Path | None = None) -> None:  # type: ignore[override]
        if tmp_wav is not None:
            self.tmp_wav = tmp_wav
        super().speak(text)

