from __future__ import annotations

import os
import threading

import uvicorn
from fastapi import FastAPI

from src.core.events import EventIngestResponse, ModelEvent, SpeakRequest
from src.services.tts import build_tts_provider
from src.speech.router import SpeechRouter


app = FastAPI(title="Speech Router (Offline TTS)")

router = SpeechRouter()
_tts = None


def _playback_worker() -> None:
    global _tts
    while True:
        event = router.get_next(timeout_s=0.25)
        if event is None:
            continue
        try:
            if _tts is None:
                _tts = build_tts_provider()
            # Integration decision: route all speech through provider strategy,
            # so Hackbyte and System TTS implementations stay modular.
            _tts.speak(
                event.message,
                timestamp=event.metadata.get("timestamp"),
                voice_id=event.voice_id,
                language=event.language,
            )
        except Exception as e:
            # Keep worker alive even if playback fails.
            print(f"[SpeechRouter] playback error: {e}")


if os.getenv("SPEECH_DISABLE_PLAYBACK", "0") != "1":
    threading.Thread(target=_playback_worker, daemon=True).start()


@app.post("/event", response_model=EventIngestResponse)
def ingest_event(event: ModelEvent) -> EventIngestResponse:
    ok, reason = router.should_accept(event)
    if not ok:
        return EventIngestResponse(accepted=False, reason=reason, queued=False)

    router.enqueue(event)
    return EventIngestResponse(accepted=True, queued=True)


@app.post("/speak", response_model=EventIngestResponse)
def speak(req: SpeakRequest) -> EventIngestResponse:
    event = SpeechRouter.from_text(req.text, priority=req.priority)
    event.voice_id = req.voice_id
    event.language = req.language
    if req.timestamp is not None:
        event.metadata["timestamp"] = req.timestamp
    router.enqueue(event)
    return EventIngestResponse(accepted=True, queued=True)


def main() -> None:
    host = os.getenv("SPEECH_HOST", "0.0.0.0")
    port = int(os.getenv("SPEECH_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

