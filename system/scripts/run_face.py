import time
import os
import sys
import subprocess
from pathlib import Path

# Ensure project root is on sys.path so `import src...` works.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.hardware.camera import CameraNode
from src.models.face_recognition.model import build_default_face_node
from src.models.weapon_detection.model import build_default_weapon_node
from src.services.cameraFeed.server import NetworkServerNode
from src.core.aggregator import AggregatorNode
from src.hardware.ultrasonic import UltrasonicNode
from src.speech.speech_node import SpeechNode
from src.models.object_detection.model import build_default_object_node


def main():
    print("=============================================")
    print("  Starting Integrated Robotics Pipeline...   ")
    print("=============================================")

    try:
        print("[*] Initializing Smart Audio Router...")
        speech_node = SpeechNode()

        print("\n[*] Initializing Vision Models...")
        face_node = build_default_face_node()
        weapon_node = build_default_weapon_node()
        aggregator = AggregatorNode(expected_models=["FaceModel", "WeaponModel"])

        print("[*] Starting TCP Video Server...")
        server = NetworkServerNode(port=9999)
        server.start()

        print("[*] Launching Local Video Viewer in the background...")
        time.sleep(2) # Give the server 2 seconds to open the port
        viewer_process = subprocess.Popen([sys.executable, "viewer.py"])

        print("[*] Warming up Hardware Sensors...")
        # Update these pin tuples to match your physical Pi wiring: (TRIG, ECHO)
        ultrasonic = UltrasonicNode(
            left_pins=(17, 18), center_pins=(27, 23), right_pins=(22, 24)
        )
        ultrasonic.start()

        print("[*] Initializing Guidance Systems...")
        obstacle_guidance = build_default_object_node()

        print("[*] Warming up Camera Hardware...")
        camera = CameraNode(camera_index=0)
        camera.start()

        print("\n[+] System is fully operational!")
        print("=============================================\n")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n[-] Ctrl+C detected. Initiating graceful shutdown...")
    except Exception as e:
        print(f"\n[!] Fatal Error in main loop: {e}")
    finally:
        print("[-] Pipeline terminated.")

        try:
            if 'viewer_process' in locals():
                viewer_process.terminate()
        except: pass

        # Cleanup GPIO safely before shutting down
        try:
            import RPi.GPIO as GPIO

            GPIO.cleanup()
        except:
            pass

        os._exit(0)


if __name__ == "__main__":
    main()
