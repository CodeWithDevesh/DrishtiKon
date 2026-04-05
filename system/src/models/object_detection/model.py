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
            "left": {"crit": 40.0},  
            "right": {"crit": 25.0},
        }

        self.history = {
            "left": deque(maxlen=5),
            "center": deque(maxlen=5),
            "right": deque(maxlen=5),
        }

        self.last_spoken_intent = ""
        self.last_global_warning_time = 0.0  

        self.debug_mode = debug_mode
        self._last_debug_time = 0.0
        
        self._is_active = False  

        # ONLY subscribe to the ultrasonic hardware, NOT the microphone!
        shared_event_bus.subscribe("ultrasonic_data", self.on_ultrasonic_data)
        
        print("[Navigation] Obstacle Guidance Node initialized. Awaiting Orchestrator activation.")

    # --- ORCHESTRATOR COMMANDS ---
    def turn_on(self) -> str:
        if not self._is_active:
            self._is_active = True
            print("[Navigation] Object Detection ENABLED.")
            return "Object detection guidance is now on."
        return "Object detection is already on."

    def turn_off(self) -> str:
        if self._is_active:
            self._is_active = False
            print("[Navigation] Object Detection DISABLED.")
            # Clear history so old data doesn't trigger instantly when turned back on
            self.history["left"].clear()
            self.history["center"].clear()
            self.history["right"].clear()
            return "Object detection guidance is now off."
        return "Object detection is already off."

    def _is_valid(self, dist: float) -> bool:
        return 0.0 < dist < 400.0

    def on_ultrasonic_data(self, event: UltrasonicEvent):
        # Gatekeeper Check
        if not self._is_active:
            return

        # 1. Buffer History
        self.history["left"].append(event.left_cm if self._is_valid(event.left_cm) else 999.0)
        self.history["center"].append(event.center_cm if self._is_valid(event.center_cm) else 999.0)
        self.history["right"].append(event.right_cm if self._is_valid(event.right_cm) else 999.0)

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
        elif c_warn:
            if l > r + 30: 
                message = "Obstacle ahead. Veer left."
                intent_key = "warn_veer_left"
            elif r > l + 30: 
                message = "Obstacle ahead. Veer right."
                intent_key = "warn_veer_right"
            else:
                message = "Obstacle ahead. Slow down."
                intent_key = "warn_center_slow"
            cooldown = 10.0

        if not message:
            return

        current_time = time.time()
        is_critical = priority == EventPriority.HIGH

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
