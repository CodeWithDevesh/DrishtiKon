import time
import os
import sys
import threading
import cv2
from pathlib import Path
from dotenv import load_dotenv
import threading

# # Load Environment Variables
load_dotenv()
DIRECTION_API = os.getenv("DIRECTION_API")

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# --- IMPORTS ---
# Core & Logic
from src.core.event_bus import shared_event_bus
from src.core.aggregator import AggregatorNode
from src.core.voice_assistant import VoiceAssistant
from src.core.aggregator import AggregatorNode
from src.speech.speech_node import SpeechNode

# Services & Networking
from src.services.cameraFeed.server import NetworkServerNode
from src.services.nav.nav import NavServerNode
from src.services.streamer import start_http_streamer

# Hardware
from src.hardware.camera import CameraNode
from src.hardware.ultrasonic import UltrasonicNode

# Models
from src.models.weapon_detection.model import build_default_weapon_node
from src.models.ocr.model import build_default_ocr_node
from src.models.face_recognition.model import build_default_face_node
from src.models.object_detection.model import build_default_object_node
from src.services.Add_People.add_people import PeopleRegistrar
from src.services.snapshot.snapshot import SnapshotNode

from src.services.llm.orchestrator import LLMOrchestratorNode, SystemTools
from src.speech.client import SpeechClient


def main():
    print("=============================================")
    print("   DRISHTIKON: FULLY INTEGRATED ROBOTICS     ")
    print("   (Vision + Voice + Nav + Sensors + Web)    ")
    print("=============================================")

    try:
        # 1. Initialize Vision Models & Guidance
        print("[*] Initializing AI Models (Weapon, OCR, Objects)...")
        face_node = build_default_face_node()
        weapon_node = build_default_weapon_node()
        ocr_node = build_default_ocr_node()
        obstacle_guidance = build_default_object_node()

        # 2. Initialize Central Logic & Audio
        print("[*] Initializing Central Aggregator & Audio Systems...")
        # Listening for all key vision outputs (FaceModel removed)
        aggregator = AggregatorNode(
            expected_models=["FaceModel", "WeaponModel", "OCRModel", "ObjectModel"]
        )
        speech_node = SpeechNode()
        assistant = VoiceAssistant()
        assistant.start()

        # 3. Start Networking Services
        print("[*] Starting Navigation API Server...")
        nav_node = NavServerNode(api_key=DIRECTION_API)
        nav_node.start()

        print("[*] Starting TCP Video Server (Port 9999)...")
        tcp_server = NetworkServerNode(port=9999)
        tcp_server.start()

        register_node = PeopleRegistrar()

        snap_node = SnapshotNode()

        print("[*] Starting React Native Video Stream on Port 8000...")
        stream_thread = threading.Thread(
            target=start_http_streamer, args=(8002,), daemon=True
        )
        stream_thread.start()

        # 4. Start Hardware Sensors
        print("[*] Warming up Ultrasonic Sensors (GPIO Mode)...")
        # Ensure pins match your Physical Pi layout: (TRIG, ECHO)
        ultrasonic = UltrasonicNode(
            left_pins=(17, 18), center_pins=(27, 23), right_pins=(22, 24)
        )
        ultrasonic.start()

        print("[*] Starting the voice assistant")
        speechClient = SpeechClient()
        systemTools = SystemTools(face_node, ultrasonic, snap_node, ocr_node, obstacle_guidance)
        LLMOrchestratorNode(speechClient, systemTools)

        print("[*] Warming up Camera Hardware...")
        camera = CameraNode(camera_index=0)
        camera.start()

        print("\n[+] ALL SYSTEMS GREEN - FULLY OPERATIONAL")
        print("[+] Monitor active on Local Display and Ports 8000/9999")
        print("=============================================\n")

        # 5. Management Loop
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n[-] Shutdown initiated by user...")
    except Exception as e:
        print(f"\n[!] Fatal System Error: {e}")
    finally:
        print("[-] Cleaning up resources and GPIO...")

        # Stop Voice Assistant
        if "assistant" in locals():
            assistant.stop()

        # Cleanup GPIO for Raspberry Pi
        try:
            import RPi.GPIO as GPIO

            GPIO.cleanup()
        except ImportError:
            print("[!] RPi.GPIO not found, skipping hardware cleanup.")
        except Exception as e:
            print(f"[!] GPIO cleanup failed: {e}")

        cv2.destroyAllWindows()
        print("[-] Pipeline terminated.")
        os._exit(0)


if __name__ == "__main__":
    main()
