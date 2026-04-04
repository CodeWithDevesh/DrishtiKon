from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from src.core.events import EventPriority, ModelEvent


@dataclass(order=True)
class _QueuedItem:
    priority: int
    created_at: float = field(compare=False)
    event: ModelEvent = field(compare=False)


class SpeechRouter:
    """In-memory router with priority queue + dedupe/cooldowns."""

    def __init__(self) -> None:
        self._q: "queue.PriorityQueue[_QueuedItem]" = queue.PriorityQueue()
        # Dedupe should apply at ingest time (not after playback),
        # otherwise repeated events queue up before the first is spoken.
        self._last_accepted_at: dict[str, float] = {}
        self._lock = threading.Lock()

    def should_accept(self, event: ModelEvent) -> tuple[bool, Optional[str]]:
        key = event.dedupe_key
        if not key:
            return True, None

        now = time.time()
        with self._lock:
            last = self._last_accepted_at.get(key)
            if last is None:
                return True, None
            if (now - last) < float(event.cooldown_s):
                return False, "cooldown"
        return True, None

    def enqueue(self, event: ModelEvent) -> None:
        key = event.dedupe_key
        if key:
            with self._lock:
                self._last_accepted_at[key] = time.time()
        item = _QueuedItem(priority=int(event.priority), created_at=time.time(), event=event)
        self._q.put(item)

    def get_next(self, timeout_s: float = 0.25) -> Optional[ModelEvent]:
        try:
            item = self._q.get(timeout=timeout_s)
        except queue.Empty:
            return None
        try:
            return item.event
        finally:
            self._q.task_done()

    @staticmethod
    def from_text(text: str, priority: EventPriority = EventPriority.NORMAL) -> ModelEvent:
        return ModelEvent(source="legacy", type="speak", message=text, priority=priority)

