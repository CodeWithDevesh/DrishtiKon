from __future__ import annotations

import os
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pygame
from piper import PiperVoice

from src.services.tts.base import TTSProvider


@dataclass(frozen=True)
class PiperVoiceConfig:
    model_path: Path
    config_path: Path


def default_piper_voice_config() -> PiperVoiceConfig:
    model = os.getenv("PIPER_MODEL_PATH", "assets/tts_models/en_US-lessac-medium.onnx")
    cfg = os.getenv("PIPER_CONFIG_PATH", "assets/tts_models/en_US-lessac-medium.onnx.json")
    return PiperVoiceConfig(model_path=Path(model), config_path=Path(cfg))


class PiperTTSProvider(TTSProvider):
    """Low-latency local TTS provider based on Piper + pygame."""

    def __init__(self, voice_cfg: PiperVoiceConfig, tmp_wav: Path) -> None:
        self.voice_cfg = voice_cfg
        self.tmp_wav = tmp_wav
        self._voice: Optional[PiperVoice] = None
        self._voice_lock = threading.Lock()
        self._audio_inited = False
        self._audio_lock = threading.Lock()
        
        # NEW: The kill switch for preemption
        self._stop_event = threading.Event()

    def _get_voice(self) -> PiperVoice:
        with self._voice_lock:
            if self._voice is None:
                self._voice = PiperVoice.load(str(self.voice_cfg.model_path), str(self.voice_cfg.config_path))
            return self._voice

    def speak(
        self,
        text: str,
        *,
        timestamp: Optional[float] = None,
        voice_id: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        # Reset the kill switch before we start
        self._stop_event.clear()
        
        _ = (voice_id, language)
        voice = self._get_voice()

        # 1. Synthesize the Audio (Blocking, but fast)
        with wave.open(str(self.tmp_wav), "wb") as wf:
            voice.synthesize_wav(text, wf, set_wav_format=True)

        # PREEMPTION CHECK: Did a HIGH priority event arrive while we were synthesizing?
        # If so, abort immediately without playing the audio!
        if self._stop_event.is_set():
            return

        # 2. Init Audio Hardware
        with self._audio_lock:
            if not self._audio_inited:
                pygame.mixer.init()
                self._audio_inited = True

        # 3. Start Playback
        pygame.mixer.music.load(str(self.tmp_wav))
        pygame.mixer.music.play()
        
        # 4. Wait for audio to finish, UNLESS the stop event is triggered
        while pygame.mixer.music.get_busy() and not self._stop_event.is_set():
            pygame.time.Clock().tick(10)
            
        pygame.mixer.music.unload()

    def stop(self) -> None:
        """Instantly halts audio playback and breaks the speak loop."""
        # Signal the while loop and synthesis checks to abort
        self._stop_event.set()
        
        # Force pygame to stop pushing audio to the speaker
        with self._audio_lock:
            if self._audio_inited and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
