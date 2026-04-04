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
    RenderedFrameEvent,
)
from src.core.event_bus import shared_event_bus
from src.models.face_recognition.config import FaceRecognitionConfig
from src.speech.client import SpeechClient


@dataclass
class PersonTracker:
    """Tracks a unique body ID provided by YOLO."""

    yolo_id: int
    name: str = "Scanning..."
    history: deque = field(default_factory=lambda: deque(maxlen=20))
    last_announced_state: str = "none"
    last_event_time: float = 0.0
    is_active: bool = True
    has_announced_entrance: bool = False


class FaceModelNode:
    """
    Subscribes to raw frames via the shared bus, runs YOLO + Face Recognition,
    calculates intent, triggers voice events, and publishes drawing coordinates.
    """

    def __init__(self, cfg: FaceRecognitionConfig, speech: SpeechClient):
        self.cfg = cfg
        self.speech = speech

        print("[Vision] Loading YOLOv8 Nano...")
        self._yolo_model = YOLO("yolov8n.pt")
        self._known_face_encodings: list = []
        self._known_face_names: list = []

        self._executor = ThreadPoolExecutor(max_workers=1)
        self._is_recognizing = False
        self._trackers: dict[int, PersonTracker] = {}

        # Load known faces on boot
        self._load_known_faces()

        # Subscribe to internal vision bus and external voice bus
        shared_event_bus.subscribe("raw_frame", self.on_raw_frame)
        shared_event_bus.subscribe("voice_command", self._on_voice_command)

    def _load_known_faces(self) -> None:
        if not os.path.exists(self.cfg.face_db_path):
            print(f"[Warning] Face database path not found: {self.cfg.face_db_path}")
            return

        print("[Vision] Loading known faces into memory...")
        for filename in os.listdir(self.cfg.face_db_path):
            if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                filepath = os.path.join(self.cfg.face_db_path, filename)
                name = os.path.splitext(filename)[0]
                try:
                    image = face_recognition.load_image_file(filepath)
                    encodings = face_recognition.face_encodings(image)
                    if encodings:
                        self._known_face_encodings.append(encodings[0])
                        self._known_face_names.append(name.replace("_", " "))
                        print(f"Loaded: {name}")
                except Exception as e:
                    print(f"[Error] Failed to load {filename}: {e}")

    def _on_voice_command(self, transcript: str):
        if "who" in transcript or "people" in transcript or "describe" in transcript:
            print("[Vision] Intercepted relevant voice command!")
            response = self.describe_scene()
            self.speech.speak_text(response)

    def describe_scene(self) -> str:
        active_people = []
        for tracker in self._trackers.values():
            if (
                tracker.is_active
                and tracker.has_announced_entrance
                and tracker.name != "Scanning..."
            ):
                state = tracker.last_announced_state.replace("_", " ")

                if state in ["stationary", "entered", "none"]:
                    action = "standing nearby"
                elif state == "very_close":
                    action = "right in front of you"
                elif state == "approaching":
                    action = "approaching you"
                elif state == "leaving":
                    action = "walking away"
                else:
                    action = state

                display_name = (
                    "someone I don't recognize"
                    if tracker.name == "Unknown person"
                    else tracker.name
                )
                active_people.append(f"{display_name} {action}")

        if not active_people:
            return "I don't see anyone around right now."
        if len(active_people) == 1:
            return f"I see {active_people[0]}."
        if len(active_people) == 2:
            return f"I see {active_people[0]} and {active_people[1]}."

        return f"I see {', '.join(active_people[:-1])}, and {active_people[-1]}."

    def _recognize_faces_worker(self, pending_identifications: list) -> None:
        """Takes a list of tuples: (yolo_id, rgb_image_crop)"""
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

    def _get_spatial_description(self, cx: float, frame_width: int) -> str:
        third = frame_width / 3
        if cx < third:
            return "on your left"
        elif cx > 2 * third:
            return "on your right"
        return "in front of you"

    def _analyze_and_announce_intent(self, frame_width: int):
        current_time = time.time()
        for yolo_id, tracker in list(self._trackers.items()):
            name = tracker.name

            # 1. EXPIRATION
            if not tracker.is_active:
                if len(tracker.history) > 0 and (
                    current_time - tracker.history[-1][0] > 10.0
                ):
                    del self._trackers[yolo_id]
                continue

            # 2. FLICKER IGNORE
            if name == "Scanning..." or len(tracker.history) < 10:
                continue

            newest_cx = tracker.history[-1][2]
            direction = self._get_spatial_description(newest_cx, frame_width)

            # 3. ENTRANCE
            if not tracker.has_announced_entrance:
                tracker.has_announced_entrance = True
                tracker.last_announced_state = "entered"
                if name != "Unknown person":
                    ev = ModelEvent(
                        source="vision_tracking",
                        type="person_entered",
                        message=f"{name} is here, {direction}.",
                        priority=EventPriority.NORMAL,
                        dedupe_key=f"entered:{name}",
                        cooldown_s=30.0,
                    )
                    self.speech.post_event(ev)
                    tracker.last_event_time = current_time
                continue

            # 4. INTENT SMOOTHING
            history_list = list(tracker.history)
            old_heights = sorted([h for _, h, _ in history_list[:5]])
            new_heights = sorted([h for _, h, _ in history_list[-5:]])

            oldest_h = old_heights[len(old_heights) // 2]
            newest_h = new_heights[len(new_heights) // 2]
            height_diff = newest_h - oldest_h
            threshold = max(80, oldest_h * 0.20)

            current_state = "stationary"
            if newest_h > 400:
                current_state = "very_close"
            elif height_diff > threshold:
                current_state = "approaching"
            elif height_diff < -threshold:
                current_state = "leaving"

            # 5. ANNOUNCEMENTS
            time_since_last_event = current_time - tracker.last_event_time
            state_changed = current_state != tracker.last_announced_state

            if state_changed and time_since_last_event > 5.0:
                message = ""
                priority = EventPriority.NORMAL

                if current_state == "approaching":
                    message = f"{name} is approaching."
                elif current_state == "leaving":
                    message = f"{name} is walking away."
                elif current_state == "very_close":
                    message = f"{name} is right in front of you."
                    priority = EventPriority.HIGH

                if message and name != "Unknown person":
                    ev = ModelEvent(
                        source="vision_tracking",
                        type="person_intent",
                        message=message,
                        priority=priority,
                        dedupe_key=f"intent:{name}:{current_state}",
                        cooldown_s=15.0,
                    )
                    self.speech.post_event(ev)

                tracker.last_announced_state = current_state
                tracker.last_event_time = current_time

    def on_raw_frame(self, event: RawFrameEvent) -> None:
        frame = event.frame
        frame_width = frame.shape[1]
        current_time = time.time()

        # 1. RUN YOLO
        results = self._yolo_model.track(
            frame, classes=[0], persist=True, verbose=False
        )

        for tracker in self._trackers.values():
            tracker.is_active = False

        pending_identifications = []
        drawing_data = []  # Data sent to Aggregator

        # 2. PROCESS TRACKS
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

                # Bundle visual data to send to the drawing node
                tracker_state = (
                    tracker.last_announced_state
                    if tracker.has_announced_entrance
                    else ""
                )
                drawing_data.append(
                    {
                        "box": (x1, y1, x2, y2),
                        "label": f"{tracker.name} ({tracker_state})",
                    }
                )

                if tracker.name == "Scanning...":
                    pad = 20
                    y1_pad = max(0, y1 - pad)
                    y2_pad = min(frame.shape[0], y2 + pad)
                    x1_pad = max(0, x1 - pad)
                    x2_pad = min(frame.shape[1], x2 + pad)

                    full_body_crop = frame[y1_pad:y2_pad, x1_pad:x2_pad]
                    if full_body_crop.shape[0] > 0 and full_body_crop.shape[1] > 0:
                        rgb_crop = cv2.cvtColor(full_body_crop, cv2.COLOR_BGR2RGB)
                        pending_identifications.append((track_id, rgb_crop))

        # 3. ANALYSIS & BG RECOGNITION
        self._analyze_and_announce_intent(frame_width)

        if not self._is_recognizing and len(pending_identifications) > 0:
            self._is_recognizing = True
            self._executor.submit(self._recognize_faces_worker, pending_identifications)

        # 4. PUBLISH RESULTS FOR DRAWING
        # CRITICAL: run_async=False prevents thread exhaustion for video frames!
        shared_event_bus.publish(
            "model_result",
            ModelResultEvent(event.frame_id, "FaceModel", drawing_data),
            run_async=False,
        )



# Utility function to easily boot this specific module from main.py
def build_default_face_node() -> FaceModelNode:
    cfg = FaceRecognitionConfig()
    speech = SpeechClient(base_url=cfg.tts_router_url)
    
    return FaceModelNode(cfg, speech)
