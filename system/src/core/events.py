from __future__ import annotations

from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel, Field
import numpy as np
from dataclasses import dataclass


class EventPriority(IntEnum):
    HIGH = 0
    NORMAL = 5
    LOW = 9


class ModelEvent(BaseModel):
    """Structured event emitted by a model."""

    source: str = Field(..., description="Model/plugin name, e.g. 'face_recognition'")
    type: str = Field(..., description="Event type, e.g. 'person_distance'")
    message: str = Field(..., description="Human-facing message to speak/log")

    priority: EventPriority = Field(default=EventPriority.NORMAL)
    dedupe_key: Optional[str] = Field(
        default=None,
        description="Events with same key may be suppressed within cooldown_s.",
    )
    cooldown_s: float = Field(default=2.0, ge=0.0)

    voice_id: Optional[str] = Field(default=None, description="Voice/model id hint")
    language: Optional[str] = Field(
        default=None, description="Language hint, e.g. en/hi"
    )

    metadata: dict[str, Any] = Field(default_factory=dict)


class SpeakRequest(BaseModel):
    text: str
    priority: EventPriority = Field(default=EventPriority.NORMAL)
    voice_id: Optional[str] = None
    timestamp: Optional[float] = None
    language: Optional[str] = None


class EventIngestResponse(BaseModel):
    accepted: bool
    reason: Optional[str] = None
    queued: bool = False
    spoken_immediately: bool = False


@dataclass
class RawFrameEvent:
    frame_id: int
    frame: np.ndarray


@dataclass
class ModelResultEvent:
    frame_id: int
    model_name: str
    data: list


@dataclass
class RenderedFrameEvent:
    frame_id: int
    frame: np.ndarray

@dataclass
class UltrasonicEvent:
    left_cm: float
    center_cm: float
    right_cm: float
