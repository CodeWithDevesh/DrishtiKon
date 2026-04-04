import time
import os

import sys
from pathlib import Path

# Ensure project root is on sys.path so `import src...` works.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import our decoupled nodes
from src.hardware.camera import CameraNode
from src.models.weapon_detection.model import build_default_weapon_node
from src.services.cameraFeed.server import NetworkServerNode
from src.core.aggregator import AggregatorNode


def main():
    print("=============================================")
    print("  Testing ISOLATED Weapon Detection...       ")
    print("=============================================")

    try:
        # 1. Initialize ONLY the Weapon Detection Node
        print("[*] Initializing Weapon Detection...")
        weapon_node = build_default_weapon_node()

        # 2. Tell the Aggregator to ONLY expect the Weapon Model
        # This prevents it from waiting forever for the Face Model
        print("[*] Initializing Central Aggregator...")
        aggregator = AggregatorNode(expected_models=["WeaponModel"])

        # 3. Start the Network Server
        print("[*] Starting TCP Video Server...")
        server = NetworkServerNode(port=9999)
        server.start()

        # 4. Start the Camera
        print("[*] Warming up Camera Hardware...")
        camera = CameraNode(camera_index=0)
        camera.start()

        print("\n[+] Weapon Detection is fully operational!")
        print("[+] Waiting for client to connect to view feed...")
        print("=============================================\n")

        # Keep main thread alive
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
