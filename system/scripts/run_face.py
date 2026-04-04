import time
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
DIRECTION_API = os.getenv("DIRECTION_API")

# Ensure project root is on sys.path so `import src...` works.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# from integrated_system.scripts.run_nav import NavServerNode
from src.services.nav.nav import NavServerNode
from src.hardware.camera import CameraNode
from src.models.face_recognition.model import build_default_face_node
from src.models.weapon_detection.model import build_default_weapon_node
from src.services.cameraFeed.server import NetworkServerNode
from src.core.aggregator import AggregatorNode 

def main():
    print("=============================================")
    print("  Starting Multi-Model Vision Pipeline...    ")
    print("=============================================")

    try:
        print("\n[*] Initializing Face Recognition...")
        face_node = build_default_face_node()

        print("[*] Initializing Weapon Detection...")
        weapon_node = build_default_weapon_node()

        print("[*] Starting Navigation API Server on port 7000...")
        nav_node = NavServerNode(api_key=DIRECTION_API)
        nav_node.start();
        

        # Wire up the Central Aggregator!
        print("[*] Initializing Central Aggregator...")
        aggregator = AggregatorNode(expected_models=["FaceModel", "WeaponModel"])

        print("[*] Starting TCP Video Server...")
        server = NetworkServerNode(port=9999)
        server.start()

        print("[*] Warming up Camera Hardware...")
        camera = CameraNode(camera_index=0)
        camera.start()

        print("\n[+] System is fully operational!")
        print("[+] Waiting for client to connect to view feed...")
        print("=============================================\n")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n[-] Ctrl+C detected. Initiating graceful shutdown...")
    except Exception as e:
        print(f"\n[!] Fatal Error in main loop: {e}")
    finally:
        print("[-] Pipeline terminated.")
        os._exit(0)

if __name__ == "__main__":
    main()
