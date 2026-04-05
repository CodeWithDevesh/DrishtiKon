import os
import cv2
import io
import time
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

from src.core.event_bus import shared_event_bus

load_dotenv()

class SnapshotNode:
    """Passively caches frames and handles Cloudinary uploads when commanded."""
    def __init__(self):
        # Configure Cloudinary
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
            api_key=os.getenv("CLOUDINARY_API_KEY"),
            api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            secure=True
        )
        
        self._latest_frame = None
        
        # ONLY subscribe to the camera, NOT voice commands
        shared_event_bus.subscribe("raw_frame", self._on_raw_frame)
        print("[Snapshot] ✅ Node initialized. Ready to upload snaps.", flush=True)

    def _on_raw_frame(self, event):
        """Update the local cache with the most recent camera frame."""
        self._latest_frame = event.frame

    def take_and_upload_snap(self) -> str:
        """Called by the Orchestrator. Returns a spoken status string."""
        if self._latest_frame is None:
            return "I cannot see anything to snap right now."

        # 1. Encode to JPG in memory
        success, buffer = cv2.imencode(".jpg", self._latest_frame)
        if not success:
            print("[Snapshot] ❌ Encoding error.", flush=True)
            return "Failed to encode the image."
            
        # 2. Wrap in BytesIO for Cloudinary
        img_stream = io.BytesIO(buffer)

        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            public_id = f"snap_{timestamp}"

            print(f"[Snapshot] ☁️ Uploading to 'snap' folder...", flush=True)
            
            upload_result = cloudinary.uploader.upload(
                img_stream,
                public_id=public_id,
                folder="snap",
                resource_type="image"
            )
            
            print(f"✅ Saved to Cloudinary: {upload_result['secure_url']}", flush=True)
            return "Snapshot successfully saved to your cloud storage."

        except Exception as e:
            print(f"❌ Upload Error: {e}", flush=True)
            return "I encountered an error while saving the snapshot."
