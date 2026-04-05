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
import urllib.request
import cloudinary
import cloudinary.api
from dotenv import load_dotenv

load_dotenv()

# Project-specific imports
from src.core.events import (
    EventPriority,
    ModelEvent,
    RawFrameEvent,
    ModelResultEvent,
    UltrasonicEvent,
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
    Acts as a Hardware Helper for the Orchestrator's describe_scene tool.
    """

    def __init__(self, cfg: FaceRecognitionConfig):
        self.cfg = cfg

        # 1. Cloudinary Configuration
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
            api_key=os.getenv("CLOUDINARY_API_KEY"),
            api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            secure=True,
        )

        # 2. Tracking and Encodings
        self._loaded_public_ids = set()
        self._known_face_encodings: list = []
        self._known_face_names: list = []

        # 3. Model Initialization
        print("[Vision] Loading YOLOv8 Face Tracking with Sensor Fusion...")
        self._yolo_model = YOLO("yolov8n_ncnn_model")
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._is_recognizing = False
        self._trackers: dict[int, PersonTracker] = {}
        self._frame_count = 0
        self._process_every_n_frames = 3

        # --- Ultrasonic State Cache ---
        self._latest_sonar = {"left": 999.0, "center": 999.0, "right": 999.0}

        # 5. Initial Sync from Cloudinary
        self._load_known_faces()

        # 6. Event Bus Subscriptions (Removed voice_command!)
        shared_event_bus.subscribe("reload_faces", self._load_known_faces)
        shared_event_bus.subscribe("raw_frame", self.on_raw_frame)
        shared_event_bus.subscribe("ultrasonic_data", self.on_ultrasonic_data)

    def _load_known_faces(self, event_data=None) -> None:
        """Downloads new faces from Cloudinary and generates encodings."""
        print("[Vision] Syncing faces from Cloudinary folder: blind_nav_faces/ ...")

        try:
            resources = cloudinary.api.resources(
                type="upload", prefix="blind_nav_faces/", max_results=100
            )

            new_faces_count = 0
            for asset in resources.get("resources", []):
                public_id = asset["public_id"]

                if public_id not in self._loaded_public_ids:
                    url = asset["secure_url"]
                    print(f"[Vision] Found new face in cloud: {public_id}")

                    with urllib.request.urlopen(url) as response:
                        img_array = np.asarray(
                            bytearray(response.read()), dtype=np.uint8
                        )
                        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        if image is None:
                            continue

                        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

                    encodings = face_recognition.face_encodings(rgb_image)
                    if encodings:
                        clean_name = public_id.split("/")[-1].replace("_", " ")

                        self._known_face_encodings.append(encodings[0])
                        self._known_face_names.append(clean_name)
                        self._loaded_public_ids.add(public_id)
                        new_faces_count += 1
                        print(f"✅ Successfully encoded: {clean_name}")

            if new_faces_count > 0:
                print(f"[Vision] Sync complete. Added {new_faces_count} new faces.")
            else:
                print("[Vision] Cloudinary sync complete. No new faces found.")

        except Exception as e:
            print(f"❌ Cloudinary Sync Error: {e}")

    def on_ultrasonic_data(self, event: UltrasonicEvent):
        """Silently caches the latest physical distances to cross-reference with vision."""

        def clean(val):
            return val if 0.0 < val < 400.0 else 999.0

        self._latest_sonar["left"] = clean(event.left_cm)
        self._latest_sonar["center"] = clean(event.center_cm)
        self._latest_sonar["right"] = clean(event.right_cm)

    # --- CALLED BY ORCHESTRATOR ---
    def describe_scene(self) -> str:
        """Passive tool method used by the LLM / Fast-Path Router"""
        known_people = []
        unknown_count = 0

        for tracker in self._trackers.values():
            if not tracker.is_active or tracker.name == "Scanning...":
                continue

            if tracker.name == "Unknown person":
                unknown_count += 1
                continue

            # Process recognized friends
            state = tracker.last_announced_state

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

            # Note: Deliberately omitting "is" for better TTS flow
            # e.g., "Devesh standing nearby" rather than "Devesh is standing nearby"
            known_people.append(f"{tracker.name} {action}")

        # 1. Nobody is visible
        if not known_people and unknown_count == 0:
            return "I don't see anyone around right now."

        # 2. Format the unknown count
        if unknown_count == 0:
            unknown_str = ""
        elif unknown_count == 1:
            unknown_str = "one person I don't recognize"
        else:
            unknown_str = f"{unknown_count} people I don't recognize"

        # 3. Only unknown people are visible
        if not known_people:
            return f"I see {unknown_str}."

        # 4. Format the known people using natural list grammar
        if len(known_people) == 1:
            known_str = known_people[0]
        elif len(known_people) == 2:
            known_str = " and ".join(known_people)
        else:
            known_str = ", ".join(known_people[:-1]) + ", and " + known_people[-1]

        # 5. Combine known and unknown dynamically
        if unknown_count > 0:
            return f"I see {known_str}, along with {unknown_str}."

        return f"I see {known_str}."

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
        third = frame_width / 3
        if cx < third:
            return "on your left", "left"
        elif cx > 2 * third:
            return "on your right", "right"
        return "directly ahead", "center"

    def _analyze_and_announce_intent(self, frame_width: int, frame_height: int):
        """Proactively monitors safety and publishes background alerts."""
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

            # 3. Only Announce Familiar Faces
            if name in ["Scanning...", "Unknown person"] or len(tracker.history) < 8:
                continue

            newest_cx = tracker.history[-1][2]
            direction, sonar_key = self._get_spatial_description(newest_cx, frame_width)

            message = ""
            priority = EventPriority.NORMAL
            cooldown = 15.0

            # 4. Entrance Announcement
            if not tracker.has_announced_entrance:
                tracker.has_announced_entrance = True
                tracker.last_announced_state = "entered"
                message = f"I see {name} {direction}."
                cooldown = 30.0

            # 5. Intent & Sensor Fusion
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

            # 6. Trigger Proactive Speech (Does NOT go through LLM)
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

