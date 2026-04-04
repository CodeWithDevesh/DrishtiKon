from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
from ultralytics import YOLO

# Imported from your existing project structure
from src.core.events import EventPriority, ModelEvent, RawFrameEvent, ModelResultEvent
from src.core.event_bus import shared_event_bus
from src.speech.client import SpeechClient
from src.models.weapon_detection.config import WeaponDetectionConfig

@dataclass
class WeaponTracker:
    """Helper class to track a weapon's movement over time."""
    history: deque = field(default_factory=lambda: deque(maxlen=20))
    last_announced_state: str = "none"
    last_event_time: float = 0.0
    is_active: bool = True
    has_announced_entrance: bool = False
    confidence: float = 0.0


class WeaponModelNode:
    """Subscribes to raw frames, runs background YOLO inference, tracks spatially, and publishes results."""
    
    def __init__(self, cfg: WeaponDetectionConfig, speech: SpeechClient):
        self.cfg = cfg
        self.speech = speech
        
        print(f"[Vision] Loading YOLO model from: {self.cfg.model_path}")
        self._model = YOLO(self.cfg.model_path)
        
        self._current_weapon_data: list = []
        
        # Threading and Throttling (3 workers to prevent starvation)
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._is_detecting = False
        self._last_detection_time = 0.0

        # Intelligent Spatial Tracking
        self._trackers: dict[str, WeaponTracker] = {}
        self._tracker_id_counter = 0

        # Subscribe to the shared video bus
        shared_event_bus.subscribe("raw_frame", self.on_raw_frame)

    def _detect_weapons_worker(self, frame_copy: np.ndarray) -> None:
        """Runs in the background thread. Catches errors so they don't fail silently."""
        try:
            new_weapon_data = []
            results = self._model.predict(
                frame_copy, 
                conf=self.cfg.confidence_threshold, 
                verbose=False
            )
            
            if len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    
                    # Ignore the specific class name and generalize to "weapon"
                    name = "weapon" 
                    
                    x, y, w, h = int(x1), int(y1), int(x2 - x1), int(y2 - y1)
                    new_weapon_data.append(((x, y, w, h), name, conf))

            self._current_weapon_data = new_weapon_data

        except Exception as e:
            print(f"\n[AI THREAD CRASHED]: {e}\n")
            
        finally:
            self._is_detecting = False

    def _analyze_and_alert(self, frame_width: int):
        current_time = time.time()

        for tracker_id, tracker in list(self._trackers.items()):
            # 1. Handle Expiration
            if not tracker.is_active:
                if len(tracker.history) > 0 and (current_time - tracker.history[-1][0] > 1.5):
                    del self._trackers[tracker_id]
                continue

            # 2. Handle Entrance & Alerting
            if not tracker.has_announced_entrance and len(tracker.history) > 3:
                tracker.has_announced_entrance = True
                tracker.last_announced_state = "entered"
                
                alert_message = "Warning. Weapon detected."
                
                # Create the event object
                ev = ModelEvent(
                    source="weapon_detection",
                    type="weapon_spotted",
                    message=alert_message,
                    priority=EventPriority.HIGH,  
                    dedupe_key="weapon_alert",
                    cooldown_s=15.0, 
                )
                
                # Send the network alert in the background thread to prevent camera freeze
                self._executor.submit(self.speech.post_event, ev)
                print(f"[HIGH PRIORITY ALERT] {alert_message}")
                
                tracker.last_event_time = current_time

    def on_raw_frame(self, event: RawFrameEvent) -> None:
        frame = event.frame
        current_time = time.time()
        frame_width = frame.shape[1]

        for tracker in self._trackers.values():
            tracker.is_active = False

        drawing_data = []

        # 1. SMART SPATIAL TRACKING
        for (ox, oy, ow, oh), name, conf in self._current_weapon_data:
            cx, cy = ox + ow / 2, oy + oh / 2
            best_id = None
            min_dist = float("inf")

            for tracker_id, tracker in self._trackers.items():
                if tracker_id.startswith(name) and len(tracker.history) > 0:
                    _, _, last_cx, last_cy = tracker.history[-1]
                    spatial_dist = ((cx - last_cx) ** 2 + (cy - last_cy) ** 2) ** 0.5
                    if spatial_dist < (ow * 1.5) and spatial_dist < min_dist:
                        min_dist = spatial_dist
                        best_id = tracker_id

            if best_id is None:
                self._tracker_id_counter += 1
                best_id = f"{name}_{self._tracker_id_counter}"
                self._trackers[best_id] = WeaponTracker()

            self._trackers[best_id].is_active = True
            self._trackers[best_id].confidence = conf
            self._trackers[best_id].history.append((current_time, oh, cx, cy))
            
            # Package visual data for the Central Aggregator
            x1, y1 = ox, oy
            x2, y2 = ox + ow, oy + oh
            drawing_data.append({
                "box": (x1, y1, x2, y2),
                "label": f"Weapon {conf:.2f}",
                "color": (0, 0, 255) # RED for weapons
            })

        # 2. RUN ALERTS
        self._analyze_and_alert(frame_width)

        # 3. ASYNC INFERENCE THROTTLING
        if not self._is_detecting and (current_time - self._last_detection_time > 0.1):
            self._is_detecting = True
            self._last_detection_time = current_time
            self._executor.submit(self._detect_weapons_worker, frame.copy())

        # 4. PUBLISH RESULTS FOR CENTRAL DRAWING
        shared_event_bus.publish(
            "model_result",
            ModelResultEvent(event.frame_id, "WeaponModel", drawing_data),
            run_async=False
        )


def build_default_weapon_node() -> WeaponModelNode:
    cfg = WeaponDetectionConfig()
    speech = SpeechClient(base_url=cfg.tts_router_url)
    return WeaponModelNode(cfg=cfg, speech=speech)
