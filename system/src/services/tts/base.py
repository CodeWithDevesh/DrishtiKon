from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class TTSProvider(ABC):
    """Abstract TTS interface used by the speech server."""

    @abstractmethod
    def speak(
        self,
        text: str,
        *,
        timestamp: Optional[float] = None,
        voice_id: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        raise NotImplementedError
