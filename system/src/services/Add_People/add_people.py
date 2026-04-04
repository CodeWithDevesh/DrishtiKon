import os
import cv2
import io # NEW: For stable memory-to-cloud upload
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

from src.core.event_bus import shared_event_bus
from src.core.events import SpeakRequest, EventPriority

load_dotenv()

class PeopleRegistrar:
    def __init__(self):
        print("[Registrar] 🚀 Initializing PeopleRegistrar...", flush=True)
        
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
            api_key=os.getenv("CLOUDINARY_API_KEY"),
            api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            secure=True
        )
        self.latest_frame = None
        
        # Subscriptions
        shared_event_bus.subscribe("raw_frame", self._on_new_frame)
        shared_event_bus.subscribe("registration_request", self.register_person)
        print("[Registrar] ✅ Listening for 'registration_request'...", flush=True)

    def _on_new_frame(self, event):
        self.latest_frame = event.frame

    def register_person(self, name: str):
        # This MUST print if the VoiceAssistant sends the signal
        print(f"[Registrar] 🔔 Signal Received! Registering: {name}", flush=True)

        if self.latest_frame is None:
            print("[Registrar] ❌ Error: latest_frame is empty!", flush=True)
            self._notify_user("I cannot see anyone right now.")
            return

        self._notify_user(f"Capturing face for {name}. Please hold still.")

        # Encode to memory
        success, buffer = cv2.imencode(".jpg", self.latest_frame)
        if not success:
            print("[Registrar] ❌ Image encoding failed", flush=True)
            return
            
        # Convert buffer to a file-like object for Cloudinary
        img_stream = io.BytesIO(buffer)

        try:
            print(f"[Registrar] ☁️ Uploading {name} to Cloudinary...", flush=True)
            upload_result = cloudinary.uploader.upload(
                img_stream,
                public_id=name.replace(" ", "_"),
                folder="blind_nav_faces",
                overwrite=True,
                resource_type="image"
            )
            
            print(f"✅ Upload Complete: {upload_result['secure_url']}", flush=True)
            self._notify_user(f"{name} has been added to my memory.")
            shared_event_bus.publish("reload_faces", data=None)

        except Exception as e:
            print(f"❌ Cloudinary Error: {e}", flush=True)
            self._notify_user("I had trouble saving the face data.")

    def _notify_user(self, text: str):
        event = SpeakRequest(text=text, priority=EventPriority.NORMAL)
        shared_event_bus.publish("speak_request", event)