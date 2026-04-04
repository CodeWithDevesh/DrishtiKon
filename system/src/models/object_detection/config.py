from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectDetectionConfig:
    tts_router_url: str = os.getenv("SPEECH_ROUTER_URL", "http://127.0.0.1:8000")
    critical_dist: int = 20
    warning_dist: int = 40

