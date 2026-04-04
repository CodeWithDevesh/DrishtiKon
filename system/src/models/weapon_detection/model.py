from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
from ultralytics import YOLO

# Imported from your existing project structure
from src.core.events import (
    EventPriority,
    ModelEvent,
    RawFrameEvent,
    ModelResultEvent,
    UltrasonicEvent,  # <-- NEW: Import the hardware event
)
from src.core.event_bus import shared_event_bus
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
    """Subscribes to raw frames and ultrasonic data for Sensor Fused weapon tracking."""

    def __init__(self, cfg: WeaponDetectionConfig):
        self.cfg = cfg

        print(f"[Vision] Loading YOLO Weapon model from: {self.cfg.model_path}")
        self._model = YOLO(self.cfg.model_path)

        self._current_weapon_data: list = []

        # Threading and Throttling
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._is_detecting = False
        self._last_detection_time = 0.0

        # Intelligent Spatial Tracking
        self._trackers: dict[str, WeaponTracker] = {}
        self._tracker_id_counter = 0

        # --- NEW: Ultrasonic State Cache ---
        self._latest_sonar = {"left": 999.0, "center": 999.0, "right": 999.0}

        # Subscribe to both the camera and the hardware array!
        shared_event_bus.subscribe("raw_frame", self.on_raw_frame)
        shared_event_bus.subscribe("ultrasonic_data", self.on_ultrasonic_data)

    # --- NEW: Catch Ultrasonic Updates ---
    def on_ultrasonic_data(self, event: UltrasonicEvent):
        """Silently caches the latest physical distances to cross-reference with vision."""

        def clean(val):
            return val if 0.0 < val < 400.0 else 999.0

        self._latest_sonar["left"] = clean(event.left_cm)
        self._latest_sonar["center"] = clean(event.center_cm)
        self._latest_sonar["right"] = clean(event.right_cm)

    def _get_spatial_description(self, cx: float, frame_width: int) -> tuple[str, str]:
        """Returns (Conversational Direction, Sonar Hardware Key)"""
        third = frame_width / 3
        if cx < third:
            return "on your left", "left"
        elif cx > 2 * third:
            return "on your right", "right"
        return "directly ahead", "center"

    def _detect_weapons_worker(self, frame_copy: np.ndarray) -> None:
        """Runs in the background thread."""
        try:
            new_weapon_data = []
            results = self._model.predict(
                frame_copy, conf=self.cfg.confidence_threshold, verbose=False
            )

            if len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])

                    name = "weapon"

                    x, y, w, h = int(x1), int(y1), int(x2 - x1), int(y2 - y1)
                    new_weapon_data.append(((x, y, w, h), name, conf))

            self._current_weapon_data = new_weapon_data

        except Exception as e:
            print(f"\n[AI THREAD CRASHED]: {e}\n")

        finally:
            self._is_detecting = False

    def _analyze_and_alert(self, frame_width: int, frame_height: int):
        current_time = time.time()

        for tracker_id, tracker in list(self._trackers.items()):
            # 1. Handle Expiration
            if not tracker.is_active:
                if len(tracker.history) > 0 and (
                    current_time - tracker.history[-1][0] > 1.5
                ):
                    del self._trackers[tracker_id]
                continue

            if len(tracker.history) < 3:
                continue

            # Extract spatial data
            newest_cx = tracker.history[-1][2]
            direction, sonar_key = self._get_spatial_description(newest_cx, frame_width)

            # FIX: ALWAYS calculate physical distance at the top of the loop!
            physical_dist_cm = self._latest_sonar[sonar_key]

            message = ""
            priority = EventPriority.HIGH
            cooldown = 15.0

            # 2. First-Time Entrance Alert
            if not tracker.has_announced_entrance:
                tracker.has_announced_entrance = True
                tracker.last_announced_state = "spotted"

                message = f"Danger. Weapon spotted {direction}."

            # 3. Intent Tracking (Sensor Fusion)
            else:
                history_list = list(tracker.history)
                old_heights = sorted([h for _, h, _, _ in history_list[:3]])
                new_heights = sorted([h for _, h, _, _ in history_list[-3:]])

                oldest_h = old_heights[len(old_heights) // 2]
                newest_h = new_heights[len(new_heights) // 2]

                height_diff = newest_h - oldest_h
                growth_threshold = max(40, oldest_h * 0.20)

                current_state = "stationary"

                # Absolute Proximity
                if newest_h > (frame_height * 0.40) or (
                    physical_dist_cm < 100.0 and newest_h > frame_height * 0.10
                ):
                    current_state = "very_close"
                # Approaching
                elif height_diff > growth_threshold:
                    current_state = "approaching"
                # Retreating
                elif height_diff < -growth_threshold:
                    current_state = "leaving"

                time_since_last = current_time - tracker.last_event_time
                state_changed = current_state != tracker.last_announced_state

                if state_changed and time_since_last > 4.0:
                    if current_state == "very_close":
                        message = (
                            f"Immediate danger! Weapon extremely close {direction}!"
                        )
                        cooldown = 10.0
                    elif current_state == "approaching":
                        message = f"Weapon approaching {direction}!"
                        cooldown = 12.0
                    elif current_state == "leaving":
                        message = f"Weapon is moving away {direction}."
                        cooldown = 20.0

                if message:
                    tracker.last_announced_state = current_state

            # 4. Trigger Preemptive Speech Node
            if message:
                ev = ModelEvent(
                    source="weapon_detection",
                    type="weapon_alert",
                    message=message,
                    priority=priority,
                    dedupe_key=f"weapon_{tracker_id}_{tracker.last_announced_state}",
                    cooldown_s=cooldown,
                )

                shared_event_bus.publish("speak_request", ev, run_async=True)
                # FIX: physical_dist_cm is now safely accessible here
                print(
                    f"🚨 [WEAPON FUSION ALERT] {message} (Sonar: {physical_dist_cm}cm)"
                )
                tracker.last_event_time = current_time

    def on_raw_frame(self, event: RawFrameEvent) -> None:
        frame = event.frame
        current_time = time.time()

        # We need height now for the fusion math!
        frame_height, frame_width = frame.shape[:2]

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

            x1, y1 = ox, oy
            x2, y2 = ox + ow, oy + oh
            drawing_data.append(
                {
                    "box": (x1, y1, x2, y2),
                    "label": f"Weapon {conf:.2f}",
                    "color": (0, 0, 255),
                }
            )

        # 2. RUN ALERTS
        self._analyze_and_alert(frame_width, frame_height)

        # 3. ASYNC INFERENCE THROTTLING
        if not self._is_detecting and (current_time - self._last_detection_time > 0.1):
            self._is_detecting = True
            self._last_detection_time = current_time
            self._executor.submit(self._detect_weapons_worker, frame.copy())

        # 4. PUBLISH RESULTS FOR CENTRAL DRAWING
        shared_event_bus.publish(
            "model_result",
            ModelResultEvent(event.frame_id, "WeaponModel", drawing_data),
            run_async=False,
        )


def build_default_weapon_node() -> WeaponModelNode:
    cfg = WeaponDetectionConfig()
    return WeaponModelNode(cfg=cfg)
