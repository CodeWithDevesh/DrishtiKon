import sys
import cv2
import threading
from src.core.event_bus import shared_event_bus  # <-- Your shared bus
from src.core.events import RawFrameEvent  # <-- Your updated events


def _capture_backends() -> list[int]:
    backends: list[int] = []
    if sys.platform == "win32":
        for attr in ("CAP_DSHOW", "CAP_MSMF", "CAP_ANY"):
            if hasattr(cv2, attr):
                b = int(getattr(cv2, attr))
                if b not in backends:
                    backends.append(b)
        if 0 not in backends:
            backends.append(0)
        return backends
    if hasattr(cv2, "CAP_V4L2"):
        backends.append(int(cv2.CAP_V4L2))
    if 0 not in backends:
        backends.append(0)
    return backends


def open_camera(index: int) -> cv2.VideoCapture:
    tried = []
    for api in _capture_backends():
        tried.append(api)
        cap = cv2.VideoCapture(index, api)
        if cap.isOpened():
            return cap
        cap.release()
    raise RuntimeError(f"Could not open camera index {index}.")


class CameraNode(threading.Thread):
    def __init__(self, camera_index: int = 0):
        super().__init__(daemon=True)
        self.camera_index = camera_index
        self.frame_count = 0

    def run(self):
        print(f"[Camera] Initializing hardware (Index {self.camera_index})...")
        cap = open_camera(self.camera_index)
        print("[Camera] Hardware active. Streaming frames...")

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                self.frame_count += 1

                # CRITICAL: run_async=False prevents thread thrashing!
                shared_event_bus.publish(
                    "raw_frame", RawFrameEvent(self.frame_count, frame), run_async=False
                )
        finally:
            cap.release()
            print("[Camera] Shutting down.")
