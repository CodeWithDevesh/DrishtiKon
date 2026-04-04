from __future__ import annotations

import os
from typing import Optional

from src.core.events import ModelEvent, SpeakRequest
from src.core.event_bus import shared_event_bus
from src.speech.router import SpeechRouter


class SpeechClient:
    """Send events to the speech router natively over the Event Bus."""

    def __init__(self, base_url: Optional[str] = None, timeout_s: float = 2.0) -> None:
        # We keep these arguments so older code that initializes SpeechClient doesn't break,
        # but we don't actually need them for the event bus!
        pass

    def post_event(self, event: ModelEvent) -> bool:
        # Publish natively via RAM! run_async=True is fine here since it's just text
        shared_event_bus.publish("speak_request", event, run_async=True)
        return True

    def speak_text(self, text: str) -> bool:
        req = SpeakRequest(text=text)
        # Convert simple text to a ModelEvent using your existing router logic
        event = SpeechRouter.from_text(req.text, priority=req.priority)
        if req.voice_id:
            event.voice_id = req.voice_id
        if req.language:
            event.language = req.language
        if req.timestamp is not None:
            event.metadata["timestamp"] = req.timestamp
            
        shared_event_bus.publish("speak_request", event, run_async=True)
        return True
