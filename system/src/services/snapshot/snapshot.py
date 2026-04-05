import os
import cv2
import io
import time
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

# Project-specific imports
from src.core.event_bus import shared_event_bus
from src.core.events import SpeakRequest, EventPriority

load_dotenv()

class SnapshotNode:
    def __init__(self):
        # Configure Cloudinary
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
            api_key=os.getenv("CLOUDINARY_API_KEY"),
            api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            secure=True
        )
        
        self._latest_frame = None
        
        # Subscribe to camera and voice
        shared_event_bus.subscribe("raw_frame", self._on_raw_frame)
        shared_event_bus.subscribe("voice_command", self._on_voice_command)
        print("[Snapshot] ✅ Node initialized. Listening for 'snap' command.", flush=True)

    def _on_raw_frame(self, event):
        """Update the local cache with the most recent camera frame."""
        self._latest_frame = event.frame

    def _on_voice_command(self, transcript: str):
        """React only if 'snap' is in the voice command."""
        if "snap" in transcript.lower():
            print(f"[Snapshot] 📸 Keyword detected! Capturing frame...", flush=True)
            self._take_and_upload_snap()

    def _take_and_upload_snap(self):
        if self._latest_frame is None:
            self._notify_user("I cannot see anything to snap right now.")
            return

        self._notify_user("Taking a snapshot.")

        # 1. Encode to JPG in memory
        success, buffer = cv2.imencode(".jpg", self._latest_frame)
        if not success:
            print("[Snapshot] ❌ Encoding error.", flush=True)
            return
            
        # 2. Wrap in BytesIO for Cloudinary
        img_stream = io.BytesIO(buffer)

        try:
            # Create a unique name based on the current time
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            public_id = f"snap_{timestamp}"

            print(f"[Snapshot] ☁️ Uploading to 'snap' folder...", flush=True)
            
            upload_result = cloudinary.uploader.upload(
                img_stream,
                public_id=public_id,
                folder="snap",  # <--- Specifically for the 'snap' folder
                resource_type="image"
            )
            
            print(f"✅ Saved to Cloudinary: {upload_result['secure_url']}", flush=True)
            self._notify_user("Snapshot saved to your cloud storage.")

        except Exception as e:
            print(f"❌ Upload Error: {e}", flush=True)
            self._notify_user("Failed to save the snapshot.")

    def _notify_user(self, text: str):
        """Send feedback to the user via the SpeechNode."""
        event = SpeakRequest(
            text=text, 
            priority=EventPriority.NORMAL,
            dedupe_key=f"snap_{int(time.time())}" # Unique key for router
        )
        shared_event_bus.publish("speak_request", event)