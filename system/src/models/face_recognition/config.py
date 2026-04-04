from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class FaceRecognitionConfig:
    face_db_path: str = os.getenv("FACE_DB_PATH", "./assets/faces")
    tts_router_url: str = os.getenv("SPEECH_ROUTER_URL", "http://127.0.0.1:8000")
    camera_index: int = int(os.getenv("CAMERA_INDEX", "0"))
    max_camera_index: int = int(os.getenv("MAX_CAMERA_INDEX", "10"))
