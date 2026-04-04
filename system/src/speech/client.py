from __future__ import annotations

import os
from typing import Optional

import requests

from src.core.events import ModelEvent, SpeakRequest


class SpeechClient:
    """Send events to the speech router over HTTP."""

    def __init__(self, base_url: Optional[str] = None, timeout_s: float = 2.0) -> None:
        self.base_url = (base_url or os.getenv("SPEECH_ROUTER_URL", "http://127.0.0.1:8000")).rstrip(
            "/"
        )
        self.timeout_s = timeout_s

    def post_event(self, event: ModelEvent) -> bool:
        try:
            resp = requests.post(
                f"{self.base_url}/event",
                json=event.model_dump(),
                timeout=self.timeout_s,
            )
            return resp.ok
        except requests.exceptions.RequestException:
            return False

    def speak_text(self, text: str) -> bool:
        try:
            req = SpeakRequest(text=text)
            resp = requests.post(
                f"{self.base_url}/speak",
                json=req.model_dump(),
                timeout=self.timeout_s,
            )
            return resp.ok
        except requests.exceptions.RequestException:
            return False

