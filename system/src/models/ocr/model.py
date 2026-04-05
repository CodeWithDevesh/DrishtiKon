import base64
import requests
import threading
from typing import Optional
import cv2
import numpy as np

# Internal Imports
from src.core.events import RawFrameEvent
from src.core.event_bus import shared_event_bus

class OCRModelNode:
    """Passively caches frames and performs OCR when commanded by the Orchestrator."""
    def __init__(self):
        self.api_key = 'K89475582588957'
        self.api_url = "https://api.ocr.space/parse/image"
        
        self._last_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

        # ONLY subscribe to the camera
        shared_event_bus.subscribe("raw_frame", self._on_raw_frame)
        print("[OCR SYSTEM] Node successfully initialized.")

    def _on_raw_frame(self, event: RawFrameEvent) -> None:
        with self._frame_lock:
            self._last_frame = event.frame.copy()

    def perform_ocr(self) -> str:
        """Called by the Orchestrator. Returns the read text as a string."""
        with self._frame_lock:
            frame = self._last_frame

        if frame is None:
            return "I cannot see anything to read right now."

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

            response = requests.post(self.api_url, data=payload, timeout=15)
            result = response.json()

            if result.get('ParsedResults'):
                text = result['ParsedResults'][0].get('ParsedText').strip()
                if text:
                    print(f"\n[OCR SUCCESS] Detected: {text}\n")
                    return f"The text says: {text}"
                    
            print("[OCR] No text found.")
            return "I couldn't find any readable text."
            
        except Exception as e:
            print(f"[OCR] Failed: {e}")
            return "I encountered an error while trying to read the text."

def build_default_ocr_node() -> OCRModelNode:
    return OCRModelNode()
