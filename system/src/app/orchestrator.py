from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Callable

from src.app.unified_vision import run_unified, should_use_unified
from src.models.face_recognition.model import build_default_face_model
from src.models.weapon_detection.model import build_default_weapon_model

from src.core.voice_assistant import VoiceAssistant


@dataclass(frozen=True)
class OrchestratorConfig:
    enabled_models: list[str]

    @staticmethod
    def from_env() -> "OrchestratorConfig":
        # Added 'voice_assistant' as a default enabled module
        raw = os.getenv("ENABLED_MODELS", "voice_assistant,face_recognition")
        enabled = [m.strip() for m in raw.split(",") if m.strip()]
        return OrchestratorConfig(enabled_models=enabled)


class Orchestrator:
    def __init__(self, cfg: OrchestratorConfig) -> None:
        self.cfg = cfg
        self.voice_assistant = None

    def run(self) -> None:
        enabled = self.cfg.enabled_models

        # 1. Start the Voice Assistant in the background if enabled
        if "voice_assistant" in enabled:
            print("[Orchestrator] Starting Voice Assistant...")
            self.voice_assistant = VoiceAssistant()
            self.voice_assistant.start()

        # 2. Integration decision: one camera + one window when both vision models run.
        if should_use_unified(enabled):
            try:
                run_unified(enabled)
            finally:
                # Clean up Voice Assistant when unified window closes
                if self.voice_assistant:
                    self.voice_assistant.stop()
            return

        # 3. Handle standalone threaded models
        runners: list[Callable[[], None]] = []

        if "face_recognition" in enabled:
            model = build_default_face_model()
            runners.append(lambda: model.run(list_cameras=False))

        if "weapon_detection" in enabled:
            model = build_default_weapon_model()
            runners.append(model.run)

        if not runners and "voice_assistant" not in enabled:
            raise RuntimeError(
                "No models enabled. Set ENABLED_MODELS=face_recognition,weapon_detection,..."
            )

        # 4. Start vision threads
        threads: list[threading.Thread] = []
        for fn in runners:
            t = threading.Thread(target=fn, daemon=False)
            t.start()
            threads.append(t)

        # 5. Wait for all threads to finish gracefully
        try:
            for t in threads:
                # Joining with a timeout allows KeyboardInterrupts (Ctrl+C) to be caught
                while t.is_alive():
                    t.join(timeout=1.0)
        except KeyboardInterrupt:
            print("\n[Orchestrator] Shutting down...")
        finally:
            if self.voice_assistant:
                self.voice_assistant.stop()
