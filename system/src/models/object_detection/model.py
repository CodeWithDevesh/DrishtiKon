import time
from collections import deque
import numpy as np

from src.core.events import EventPriority, ModelEvent, UltrasonicEvent
from src.core.event_bus import shared_event_bus
from src.models.object_detection.config import ObjectDetectionConfig


class ObjectDetectionNode:
    """
    Subscribes to ultrasonic hardware data. Uses median filtering to ignore
    hardware noise, and issues conversational voice commands to guide the user.
    """

    def __init__(self, config: ObjectDetectionConfig, debug_mode: bool = True):
        # --- HARDWARE-SPECIFIC CALIBRATION ---
        self.THRESH = {
            "center": {"warn": 120.0, "crit": 50.0},
            "left": {"warn": 80.0, "crit": 40.0},
            "right": {"warn": 40.0, "crit": 25.0},
        }

        self.debug_mode = debug_mode
        self.last_debug_time = 0.0

        # --- NOISE FILTERING ---
        # Store the last 5 readings to filter out acoustic ghosts/spikes
        self.history = {
            "left": deque(maxlen=5),
            "center": deque(maxlen=5),
            "right": deque(maxlen=5),
        }

        # Cooldown tracking
        self.last_spoken_intent = ""
        self.last_speech_time = 0.0

        # Subscribe to the hardware bus
        shared_event_bus.subscribe("ultrasonic_data", self.on_ultrasonic_data)
        print("[Navigation] Obstacle Guidance Node active with Median Filtering.")

    def _is_valid(self, dist: float) -> bool:
        """Filters out hardware timeouts (-1.0) and unrealistic spikes."""
        return 0.0 < dist < 400.0

    def on_ultrasonic_data(self, event: UltrasonicEvent):
        # 1. Add newest raw data to history buffers
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

        # 2. Extract smoothed (median) distances to ignore acoustic spikes
        l = float(np.median(self.history["left"]))
        c = float(np.median(self.history["center"]))
        r = float(np.median(self.history["right"]))

        if self.debug_mode:
            current_time = time.time()
            if current_time - self._last_debug_time > 0.5: # Print twice a second
                print(f"[Sonar Debug] L: {l:6.1f}cm | C: {c:6.1f}cm | R: {r:6.1f}cm")
                self._last_debug_time = current_time

        l_crit = l <= self.THRESH["left"]["crit"]
        c_crit = c <= self.THRESH["center"]["crit"]
        r_crit = r <= self.THRESH["right"]["crit"]

        l_warn = l <= self.THRESH["left"]["warn"]
        c_warn = c <= self.THRESH["center"]["warn"]
        r_warn = r <= self.THRESH["right"]["warn"]

        # FIX: Do NOT reset the last_spoken_intent to "clear" here!
        # Just return silently and let the cooldown timers do their job.
        if not any([l_crit, c_crit, r_crit, l_warn, c_warn, r_warn]):
            return

        message = ""
        priority = EventPriority.NORMAL
        intent_key = ""
        cooldown = 10.0  # Default cooldown increased

        # --- 1. CRITICAL DANGER (Immediate Stop Required) ---
        if c_crit:
            message = "Path blocked directly ahead. Please stop."
            priority = EventPriority.HIGH
            intent_key = "crit_center"
            cooldown = 8.0
        elif l_crit and r_crit:
            message = "Tight space. Obstacles on both sides."
            priority = EventPriority.HIGH
            intent_key = "crit_both"
            cooldown = 8.0
        elif l_crit:
            message = "Careful, obstacle very close on your left."
            priority = EventPriority.HIGH
            intent_key = "crit_left"
            cooldown = 8.0
        elif r_crit:
            message = "Careful, obstacle very close on your right."
            priority = EventPriority.HIGH
            intent_key = "crit_right"
            cooldown = 8.0

        # --- 2. WARNING STAGE (Navigation Advice) ---
        elif c_warn:
            if not l_warn:
                message = "Obstacle ahead. Veer left to pass."
                intent_key = "warn_center_go_left"
                cooldown = 12.0
            elif not r_warn:
                message = "Obstacle ahead. Veer right to pass."
                intent_key = "warn_center_go_right"
                cooldown = 12.0
            else:
                message = "Approaching an obstacle, please slow down."
                intent_key = "warn_center_slow"
                cooldown = 12.0
        elif l_warn:
            message = "Passing an object on your left."
            intent_key = "warn_left"
            cooldown = 15.0  # Increased heavily to prevent wall-walking spam
        elif r_warn:
            message = "Passing an object on your right."
            intent_key = "warn_right"
            cooldown = 15.0

        # --- 3. TRIGGER SPEECH ---
        if message:
            current_time = time.time()
            time_since_last = current_time - self.last_speech_time

            if intent_key != self.last_spoken_intent or time_since_last > cooldown:
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
                self.last_speech_time = current_time


def build_default_object_node() -> ObjectDetectionNode:
    cfg = ObjectDetectionConfig()
    return ObjectDetectionNode(cfg)
