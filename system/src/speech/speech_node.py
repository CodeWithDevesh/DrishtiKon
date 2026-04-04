from __future__ import annotations

import os
import threading
import time

from src.core.events import ModelEvent, EventPriority
from src.core.event_bus import shared_event_bus
from src.services.tts import build_tts_provider
from src.speech.router import SpeechRouter

class SpeechNode:
    """Listens to the event bus, manages the queue, and forcefully interrupts low-priority speech."""
    
    def __init__(self):
        self.router = SpeechRouter()
        self._tts = None
        
        # Track what is currently coming out of the speaker
        self.currently_playing_priority: int | None = None
        self._state_lock = threading.Lock()
        
        shared_event_bus.subscribe("speak_request", self.on_speak_request)
        
        if os.getenv("SPEECH_DISABLE_PLAYBACK", "0") != "1":
            threading.Thread(target=self._playback_worker, daemon=True).start()
            
        print("[Audio Router] Preemptive Speech Node Initialized.")

    def on_speak_request(self, event: ModelEvent) -> None:
        ok, reason = self.router.should_accept(event)
        if not ok:
            return

        # 1. Enqueue the event
        self.router.enqueue(event)
        
        # 2. PREEMPTION CHECK: Should we interrupt what is currently playing?
        with self._state_lock:
            if self.currently_playing_priority is not None:
                # Lower integer means HIGHER priority (0 is High, 5 is Normal, 9 is Low)
                if event.priority.value < self.currently_playing_priority:
                    print(f"⚠️ [PREEMPTION TRIGGERED] Interrupting audio for: '{event.message}'")
                    if self._tts is not None and hasattr(self._tts, "stop"):
                        self._tts.stop() # Kill the current audio!

    def _playback_worker(self) -> None:
        while True:
            # 1. Get the highest priority item from the queue
            event = self.router.get_next(timeout_s=0.25)
            if event is None:
                continue
                
            try:
                if self._tts is None:
                    self._tts = build_tts_provider()
                
                # 2. Lock the state so the listener knows what priority is currently playing
                with self._state_lock:
                    self.currently_playing_priority = event.priority.value
                
                print(f"📢 [TTS SPEAKING] (Pri:{event.priority.value}): {event.message}")
                
                # 3. This is a blocking call. 
                # If on_speak_request calls self._tts.stop(), this will abort early!
                self._tts.speak(
                    event.message,
                    timestamp=event.metadata.get("timestamp"),
                    voice_id=event.voice_id,
                    language=event.language,
                )
                
            except Exception as e:
                print(f"[SpeechNode] Playback error: {e}")
            finally:
                # 4. Clear the playing state so the system knows the speaker is free
                with self._state_lock:
                    self.currently_playing_priority = None
