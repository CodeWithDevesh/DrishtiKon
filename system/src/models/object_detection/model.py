import time
from collections import deque
import numpy as np

from src.core.events import EventPriority, ModelEvent, UltrasonicEvent
from src.core.event_bus import shared_event_bus
from src.models.object_detection.config import ObjectDetectionConfig


class ObjectDetectionNode:
    """
    Subscribes to ultrasonic hardware. Acts like a guide dog:
    Only warns about objects directly in the path, and only alerts
    on the sides if a collision is imminent.
    """

    def __init__(self, config: ObjectDetectionConfig, debug_mode: bool = False):
        self.THRESH = {
            "center": {"warn": 120.0, "crit": 50.0},
            "left": {"crit": 40.0},  # Notice: Removed the warn threshold entirely!
            "right": {"crit": 25.0},
        }

        self.history = {
            "left": deque(maxlen=5),
            "center": deque(maxlen=5),
            "right": deque(maxlen=5),
        }

        # Anti-Spam Tracking
        self.last_spoken_intent = ""
        self.last_global_warning_time = 0.0  

        self.debug_mode = debug_mode
        self._last_debug_time = 0.0
        
        # --- Voice Activation State ---
        self._is_active = False  # Starts OFF, waiting for "object detection on"

        # Subscriptions
        shared_event_bus.subscribe("ultrasonic_data", self.on_ultrasonic_data)
        shared_event_bus.subscribe("voice_command", self._on_voice_command) # Listen for voice
        
        print("[Navigation] Obstacle Guidance Node initialized. Awaiting voice activation.")

    # --- Voice Command Handler ---
    def _on_voice_command(self, data):
        """
        Listens to the event bus for specific keywords to toggle the model.
        """
        transcript = str(getattr(data, 'transcript', data)).lower().strip()
        
        if "object detection on" in transcript:
            if not self._is_active:
                self._is_active = True
                print("[Navigation] Object Detection ENABLED via voice.")
                self._announce_status("Object detection is now on.")
                
        elif "object detection of" in transcript or "object detection off" in transcript:
            if self._is_active:
                self._is_active = False
                print("[Navigation] Object Detection DISABLED via voice.")
                self._announce_status("Object detection is now off.")
                # Clear history so old data doesn't trigger instantly when turned back on
                self.history["left"].clear()
                self.history["center"].clear()
                self.history["right"].clear()

    # --- Status Announcement ---
    def _announce_status(self, message: str):
        """
        Uses the existing ModelEvent system to speak confirmation of the state change.
        """
        ev = ModelEvent(
            source="obstacle_guidance_system",
            type="system_status",
            message=message,
            priority=EventPriority.HIGH, # High priority so the user hears it immediately
            dedupe_key=f"nav_sys_{message}",
            cooldown_s=0.0
        )
        shared_event_bus.publish("speak_request", ev, run_async=True)

    def _is_valid(self, dist: float) -> bool:
        return 0.0 < dist < 400.0

    def on_ultrasonic_data(self, event: UltrasonicEvent):
        # --- Gatekeeper Check ---
        # If the model is turned off, ignore the data and do nothing
        if not self._is_active:
            return

        # 1. Buffer History
        self.history["left"].append(
            event.left_cm if self._is_valid(event.left_cm) else 999.0
        )
        self.history["center"].append(
            event.center_cm if self._is_valid(event.center_cm) else 999.0
        )
        self.history["right"].append(
            event.right_cm if self._is_valid(event.right_cm) else 999.0
        )

        if len(self.history["center"]) < 3:
            return

        # 2. Extract Smoothed Data
        l = float(np.median(self.history["left"]))
        c = float(np.median(self.history["center"]))
        r = float(np.median(self.history["right"]))

        if self.debug_mode:
            current_time = time.time()
            if current_time - self._last_debug_time > 0.5:
                print(f"[Sonar Debug] L: {l:6.1f}cm | C: {c:6.1f}cm | R: {r:6.1f}cm")
                self._last_debug_time = current_time

        # 3. Evaluate Thresholds
        l_crit = l <= self.THRESH["left"]["crit"]
        c_crit = c <= self.THRESH["center"]["crit"]
        r_crit = r <= self.THRESH["right"]["crit"]

        c_warn = c <= self.THRESH["center"]["warn"]

        message = ""
        priority = EventPriority.NORMAL
        intent_key = ""
        cooldown = 10.0

        # --- 1. CRITICAL DANGER (Immediate Action Required) ---
        if c_crit:
            message = "Path blocked. Stop."
            priority = EventPriority.HIGH
            intent_key = "crit_center"
            cooldown = 5.0
        elif l_crit and r_crit:
            message = "Tight space. Move carefully."
            priority = EventPriority.HIGH
            intent_key = "crit_both"
            cooldown = 8.0
        elif l_crit:
            message = "Step right."
            priority = EventPriority.HIGH
            intent_key = "crit_left"
            cooldown = 5.0
        elif r_crit:
            message = "Step left."
            priority = EventPriority.HIGH
            intent_key = "crit_right"
            cooldown = 5.0

        # --- 2. WARNING STAGE (Only checking the Center path!) ---
        elif c_warn:
            # If center is blocked, use left/right sensors to find the open path
            if l > r + 30:  # Left has significantly more room
                message = "Obstacle ahead. Veer left."
                intent_key = "warn_veer_left"
            elif r > l + 30:  # Right has significantly more room
                message = "Obstacle ahead. Veer right."
                intent_key = "warn_veer_right"
            else:
                message = "Obstacle ahead. Slow down."
                intent_key = "warn_center_slow"
            cooldown = 10.0

        # --- 3. SMART SPEECH TRIGGER ---
        if not message:
            return

        current_time = time.time()
        is_critical = priority == EventPriority.HIGH

        # Global Anti-Spam: Prevent switching between different warnings too fast
        if not is_critical and (current_time - self.last_global_warning_time) < 6.0:
            if intent_key != self.last_spoken_intent:
                return

        ev = ModelEvent(
            source="obstacle_guidance",
            type="navigation_alert",
            message=message,
            priority=priority,
            dedupe_key=f"nav:{intent_key}",
            cooldown_s=cooldown,
        )

        shared_event_bus.publish("speak_request", ev, run_async=True)

        self.last_spoken_intent = intent_key
        if not is_critical:
            self.last_global_warning_time = current_time


def build_default_object_node() -> ObjectDetectionNode:
    cfg = ObjectDetectionConfig()
    return ObjectDetectionNode(cfg, debug_mode=True)