from __future__ import annotations
import base64
import requests
import threading
from typing import Optional
import cv2
import numpy as np

# Internal Imports
from src.core.events import RawFrameEvent
from src.core.event_bus import shared_event_bus
from src.speech.client import SpeechClient
from src.models.face_recognition.config import FaceRecognitionConfig

class OCRModelNode:
    def __init__(self, cfg: FaceRecognitionConfig, speech: SpeechClient):
        self.cfg = cfg
        self.speech = speech
        self.api_key = 'K89475582588957'
        self.api_url = "https://api.ocr.space/parse/image"
        
        self._last_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._processing_ocr = False

        shared_event_bus.subscribe("raw_frame", self._on_raw_frame)
        shared_event_bus.subscribe("voice_command", self._on_voice_command)
        print("[OCR SYSTEM] Node successfully initialized.")

    def _on_raw_frame(self, event: RawFrameEvent) -> None:
        with self._frame_lock:
            self._last_frame = event.frame.copy()

    def _on_voice_command(self, data):
        """
        Modified to debug exactly what is arriving from the EventBus.
        """
        # 1. Convert whatever data arrives into a string
        # Handle objects or raw strings
        transcript = str(getattr(data, 'transcript', data)).lower().strip()

        # 2. DEBUG PRINT: This will show up in your terminal every time you speak
        print(f"[EVENT BUS DEBUG] OCR Node heard: '{transcript}'")

        # 3. Flexible Keyword Check
        keywords = ["read", "scan", "what does this say", "reading"]
        if any(word in transcript for word in keywords):
            if self._processing_ocr:
                print("[OCR] API is busy, please wait...")
                return
            
            print(f"[OCR] MATCH FOUND! Starting OCR for: '{transcript}'")
            threading.Thread(target=self._perform_ocr_request, daemon=True).start()

    def _perform_ocr_request(self) -> None:
        self._processing_ocr = True
        with self._frame_lock:
            frame = self._last_frame

        if frame is None:
            print("[OCR] ERROR: No frame available.")
            self._processing_ocr = False
            return

        try:
            print("[OCR] Sending image to Cloud API...")
            _, buffer = cv2.imencode('.jpg', frame)
            base64_image = base64.b64encode(buffer).decode('utf-8')

            payload = {
                'apikey': self.api_key,
                'base64Image': f"data:image/jpg;base64,{base64_image}",
                'language': 'eng',
                'OCREngine': 2 
            }

            response = requests.post(self.api_url, data=payload, timeout=10)
            result = response.json()

            if result.get('ParsedResults'):
                text = result['ParsedResults'][0].get('ParsedText').strip()
                if text:
                    print(f"\n[OCR SUCCESS] Detected: {text}\n")
                    self.speech.speak_text(f"The text says: {text}")
                else:
                    print("[OCR] No text found.")
                    self.speech.speak_text("I couldn't find any text.")
            else:
                print(f"[OCR] API Error: {result.get('ErrorMessage')}")
        except Exception as e:
            print(f"[OCR] Failed: {e}")
        finally:
            self._processing_ocr = False

# --- THIS IS THE MISSING FUNCTION THAT WAS CAUSING THE ERROR ---
def build_default_ocr_node() -> OCRModelNode:
    """
    Helper function to create the OCR node with default config and speech client.
    """
    cfg = FaceRecognitionConfig()
    # Ensure SpeechClient is initialized with the correct TTS URL
    speech = SpeechClient(base_url=cfg.tts_router_url)
    return OCRModelNode(cfg, speech)