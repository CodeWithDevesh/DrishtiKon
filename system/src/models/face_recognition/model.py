from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from concurrent.futures import ThreadPoolExecutor
import threading

import cv2
import numpy as np
import face_recognition
from ultralytics import YOLO

# Project-specific imports
from src.core.events import (
    EventPriority,
    ModelEvent,
    RawFrameEvent,
    ModelResultEvent,
    SpeakRequest,
    UltrasonicEvent,  # <-- NEW IMPORT
)
from src.core.event_bus import shared_event_bus
from src.models.face_recognition.config import FaceRecognitionConfig


@dataclass
class PersonTracker:
    yolo_id: int
    name: str = "Scanning..."
    history: deque = field(default_factory=lambda: deque(maxlen=30))
    last_announced_state: str = "none"
    last_event_time: float = 0.0
    first_seen_time: float = field(default_factory=time.time)
    is_active: bool = True
    has_announced_entrance: bool = False


class FaceModelNode:
    """
    Subscribes to raw frames and ultrasonic data.
    Uses Sensor Fusion (Camera + Sonar) to accurately determine intent.
    """

    def __init__(self, cfg: FaceRecognitionConfig):
        self.cfg = cfg

        print("[Vision] Loading YOLOv8 Face Tracking with Sensor Fusion...")
        self._yolo_model = YOLO("yolov8n_ncnn_model")
        self._known_face_encodings: list = []
        self._known_face_names: list = []

        self._executor = ThreadPoolExecutor(max_workers=1)
        self._is_recognizing = False
        self._trackers: dict[int, PersonTracker] = {}

        self._frame_count = 0
        self._process_every_n_frames = 3

        # --- Ultrasonic State Cache ---
        self._latest_sonar = {"left": 999.0, "center": 999.0, "right": 999.0}

        self._load_known_faces()

        # Native Event Bus Subscriptions
        shared_event_bus.subscribe("raw_frame", self.on_raw_frame)
        shared_event_bus.subscribe("voice_command", self._on_voice_command)
        shared_event_bus.subscribe(
            "ultrasonic_data", self.on_ultrasonic_data
        )  # <-- SENSOR FUSION

    def _load_known_faces(self) -> None:
        if not os.path.exists(self.cfg.face_db_path):
            print(f"[Warning] Face database path not found: {self.cfg.face_db_path}")
            return

        print("[Vision] Loading known faces into memory...")
        for filename in os.listdir(self.cfg.face_db_path):
            if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                filepath = os.path.join(self.cfg.face_db_path, filename)
                name = os.path.splitext(filename)[0].replace("_", " ")
                try:
                    image = face_recognition.load_image_file(filepath)
                    encodings = face_recognition.face_encodings(image)
                    if encodings:
                        self._known_face_encodings.append(encodings[0])
                        self._known_face_names.append(name)
                        print(f"Loaded: {name}")
                except Exception as e:
                    print(f"[Error] Failed to load {filename}: {e}")

    # --- Catch Ultrasonic Updates ---
    def on_ultrasonic_data(self, event: UltrasonicEvent):
        """Silently caches the latest physical distances to cross-reference with vision."""

        def clean(val):
            return val if 0.0 < val < 400.0 else 999.0

        self._latest_sonar["left"] = clean(event.left_cm)
        self._latest_sonar["center"] = clean(event.center_cm)
        self._latest_sonar["right"] = clean(event.right_cm)

    def _on_voice_command(self, transcript: str):
        if "who" in transcript or "people" in transcript or "describe" in transcript:
            response = self.describe_scene()
            event = (
                SpeechRouter.from_text(response, priority=EventPriority.NORMAL)
                if "SpeechRouter" in globals()
                else SpeakRequest(text=response)
            )
            shared_event_bus.publish("speak_request", event, run_async=True)

    def describe_scene(self) -> str:
        active_people = []
        for tracker in self._trackers.values():
            if tracker.is_active and tracker.name != "Scanning...":
                state = tracker.last_announced_state
                name = tracker.name

                if state in ["stationary", "entered", "none"]:
                    action = "standing nearby"
                elif state == "very_close":
                    action = "right in front of you"
                elif state == "approaching":
                    action = "coming towards you"
                elif state == "leaving":
                    action = "walking away"
                else:
                    action = state

                display_name = (
                    "Someone I don't recognize" if name == "Unknown person" else name
                )
                active_people.append(f"{display_name} is {action}")

        if not active_people:
            return "I don't see anyone around right now."
        if len(active_people) == 1:
            return f"I see {active_people[0]}."

        return "I see a few people: " + ", and ".join(active_people)

    def _recognize_faces_worker(self, pending_identifications: list) -> None:
        for yolo_id, face_crop_rgb in pending_identifications:
            if yolo_id not in self._trackers:
                continue

            try:
                encodings = face_recognition.face_encodings(face_crop_rgb)
                if encodings and len(self._known_face_encodings) > 0:
                    face_distances = face_recognition.face_distance(
                        self._known_face_encodings, encodings[0]
                    )
                    best_idx = np.argmin(face_distances)

                    if face_distances[best_idx] < 0.6:
                        self._trackers[yolo_id].name = self._known_face_names[best_idx]
                    else:
                        self._trackers[yolo_id].name = "Unknown person"
            except Exception:
                pass

        self._is_recognizing = False

    def _get_spatial_description(self, cx: float, frame_width: int) -> tuple[str, str]:
        """Returns (Conversational Direction, Sonar Key)"""
        third = frame_width / 3
        if cx < third:
            return "on your left", "left"
        elif cx > 2 * third:
            return "on your right", "right"
        return "directly ahead", "center"

    def _analyze_and_announce_intent(self, frame_width: int, frame_height: int):
        current_time = time.time()

        for yolo_id, tracker in list(self._trackers.items()):
            name = tracker.name

            # 1. Tracker Expiration
            if not tracker.is_active:
                if len(tracker.history) > 0 and (
                    current_time - tracker.history[-1][0] > 5.0
                ):
                    del self._trackers[yolo_id]
                continue

            # 2. Scanning Timeout
            if name == "Scanning..." and (current_time - tracker.first_seen_time > 2.0):
                tracker.name = "Unknown person"
                name = "Unknown person"

            # --- THE FIX: ONLY ANNOUNCE FAMILIAR FACES ---
            # If we don't know who they are, or we haven't seen them long enough, stay silent!
            if name in ["Scanning...", "Unknown person"] or len(tracker.history) < 8:
                continue

            # (From here down, we are guaranteed that 'name' is a recognized friend)

            newest_cx = tracker.history[-1][2]
            direction, sonar_key = self._get_spatial_description(newest_cx, frame_width)

            message = ""
            priority = EventPriority.NORMAL
            cooldown = 15.0

            # 3. Entrance Announcement
            if not tracker.has_announced_entrance:
                tracker.has_announced_entrance = True
                tracker.last_announced_state = "entered"
                message = f"I see {name} {direction}."
                cooldown = 30.0

            # 4. Intent & Sensor Fusion
            else:
                history_list = list(tracker.history)
                old_h_avg = np.mean([h for _, h, _ in history_list[:3]])
                new_h_avg = np.mean([h for _, h, _ in history_list[-3:]])
                height_diff = new_h_avg - old_h_avg
                growth_threshold = max(30, old_h_avg * 0.15)

                physical_dist_cm = self._latest_sonar[sonar_key]
                current_state = "stationary"

                if new_h_avg > (frame_height * 0.70) or physical_dist_cm < 80.0:
                    current_state = "very_close"
                elif height_diff > growth_threshold:
                    current_state = "approaching"
                elif height_diff < -growth_threshold:
                    current_state = "leaving"

                time_since_last_event = current_time - tracker.last_event_time
                state_changed = current_state != tracker.last_announced_state

                if state_changed and time_since_last_event > 4.0:
                    if current_state == "very_close":
                        message = f"{name} is right in front of you."
                        priority = EventPriority.HIGH
                        cooldown = 8.0
                    elif current_state == "approaching":
                        message = f"{name} is approaching {direction}."
                        cooldown = 12.0
                    elif current_state == "leaving":
                        message = f"{name} is walking away."
                        cooldown = 20.0

                if message:
                    tracker.last_announced_state = current_state

            # 5. Trigger Speech
            if message:
                ev = ModelEvent(
                    source="vision_tracking",
                    type="person_intent",
                    message=message,
                    priority=priority,
                    dedupe_key=f"intent:{name}:{tracker.last_announced_state}",
                    cooldown_s=cooldown,
                )
                shared_event_bus.publish("speak_request", ev, run_async=True)
                tracker.last_event_time = current_time

    def on_raw_frame(self, event: RawFrameEvent) -> None:
        self._frame_count += 1
        if self._frame_count % self._process_every_n_frames != 0:
            return

        frame = event.frame
        frame_height, frame_width = frame.shape[:2]
        current_time = time.time()

        results = self._yolo_model.track(
            frame, classes=[0], persist=True, verbose=False
        )

        for tracker in self._trackers.values():
            tracker.is_active = False

        pending_identifications = []
        drawing_data = []

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()

            for box, track_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = map(int, box)
                w, h = x2 - x1, y2 - y1
                cx = x1 + (w / 2)

                if track_id not in self._trackers:
                    self._trackers[track_id] = PersonTracker(yolo_id=track_id)

                tracker = self._trackers[track_id]
                tracker.is_active = True
                tracker.history.append((current_time, h, cx))

                tracker_state = (
                    tracker.last_announced_state
                    if tracker.has_announced_entrance
                    else ""
                )
                drawing_data.append(
                    {
                        "box": (x1, y1, x2, y2),
                        "label": f"{tracker.name} ({tracker_state})",
                        "color": (255, 165, 0),
                    }
                )

                if tracker.name == "Scanning...":
                    pad = 20
                    y1_pad = max(0, y1 - pad)
                    y2_pad = min(frame_height, y2 + pad)
                    x1_pad = max(0, x1 - pad)
                    x2_pad = min(frame_width, x2 + pad)

                    full_body_crop = frame[y1_pad:y2_pad, x1_pad:x2_pad]
                    if full_body_crop.shape[0] > 0 and full_body_crop.shape[1] > 0:
                        rgb_crop = cv2.cvtColor(full_body_crop, cv2.COLOR_BGR2RGB)
                        pending_identifications.append((track_id, rgb_crop))

        self._analyze_and_announce_intent(frame_width, frame_height)

        if not self._is_recognizing and len(pending_identifications) > 0:
            self._is_recognizing = True
            self._executor.submit(self._recognize_faces_worker, pending_identifications)

        shared_event_bus.publish(
            "model_result",
            ModelResultEvent(event.frame_id, "FaceModel", drawing_data),
            run_async=False,
        )


def build_default_face_node() -> FaceModelNode:
    cfg = FaceRecognitionConfig()
    return FaceModelNode(cfg)