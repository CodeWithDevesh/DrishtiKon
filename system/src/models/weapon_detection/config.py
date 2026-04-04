from __future__ import annotations

import os
from dataclasses import dataclass

@dataclass(frozen=True)
class WeaponDetectionConfig:
    # Pulls the path from your .env file
    model_path: str = os.getenv("WEAPON_MODEL_PATH", "./assets/weapon_detection/best_ncnn_model")
    confidence_threshold: float = float(os.getenv("WEAPON_CONFIDENCE", "0.4"))
    
    # Camera settings
    camera_index: int = int(os.getenv("CAMERA_INDEX", "0"))
    max_camera_index: int = int(os.getenv("MAX_CAMERA_INDEX", "10"))
    
    # System routing (optional, if you want the system to announce weapons)
    tts_router_url: str = os.getenv("SPEECH_ROUTER_URL", "http://127.0.0.1:8000")
