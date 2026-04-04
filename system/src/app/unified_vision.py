"""
Single camera capture + one OpenCV window; frames are fed through each enabled
vision processor in order. Processors draw on the shared frame in place.
"""

from __future__ import annotations

import os

import cv2

from src.models.face_recognition.camera import open_camera, probe_cameras
from src.models.face_recognition.model import build_default_face_model
from src.models.weapon_detection.model import build_default_weapon_model


UNIFIED_WINDOW = "Unified Vision"


def run_unified(enabled_models: list[str]) -> None:
    enabled = {m.strip() for m in enabled_models if m.strip()}
    if "face_recognition" not in enabled or "weapon_detection" not in enabled:
        raise RuntimeError(
            "run_unified requires both face_recognition and weapon_detection in ENABLED_MODELS"
        )

    try:
        if hasattr(cv2, "setLogLevel") and hasattr(cv2, "LOG_LEVEL_ERROR"):
            cv2.setLogLevel(cv2.LOG_LEVEL_ERROR)
    except Exception:
        pass

    face = build_default_face_model()
    weapon = build_default_weapon_model()
    face.ensure_vision_resources()
    weapon.ensure_yolo()

    face_cfg = face.cfg
    camera_cycle = probe_cameras(max_index=face_cfg.max_camera_index) or [face_cfg.camera_index]
    if face_cfg.camera_index in camera_cycle:
        cam_pos = camera_cycle.index(face_cfg.camera_index)
    else:
        camera_cycle = [face_cfg.camera_index] + camera_cycle
        cam_pos = 0

    current_index = camera_cycle[cam_pos]
    video_capture = open_camera(current_index)

    print("Unified vision: one camera, one window. Keys: q=quit, c=switch camera (if multiple).")

    while True:
        ret, frame = video_capture.read()
        if not ret:
            break

        # Face first (green overlays), then weapon (red) — order avoids hiding critical alerts.
        face.process_frame(frame, draw_camera_hint=False)
        weapon.process_frame(frame, draw_ui_hint=False)

        cv2.putText(
            frame,
            f"Unified | cam {current_index} | c=switch q=quit",
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2,
        )

        cv2.imshow(UNIFIED_WINDOW, frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("c") and len(camera_cycle) > 1:
            cam_pos = (cam_pos + 1) % len(camera_cycle)
            next_index = camera_cycle[cam_pos]
            try:
                video_capture.release()
            except Exception:
                pass
            try:
                video_capture = open_camera(next_index)
                current_index = next_index
                print(f"Switched to camera index {current_index}")
            except Exception as e:
                print(f"[Warning] Failed to switch to camera {next_index}: {e}")
                try:
                    video_capture = open_camera(current_index)
                except Exception:
                    break

    video_capture.release()
    cv2.destroyAllWindows()


def should_use_unified(enabled_models: list[str]) -> bool:
    if os.getenv("UNIFIED_CAMERA", "1").strip().lower() in ("0", "false", "no"):
        return False
    e = {m.strip() for m in enabled_models if m.strip()}
    return "face_recognition" in e and "weapon_detection" in e
