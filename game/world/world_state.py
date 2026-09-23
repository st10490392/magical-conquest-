"""Persistent world clock and active-event registry.

This is the seed of the living-world simulation. It advances purely from
``dt`` and has no knowledge of rendering, input, or which players are
online, so the same object can later run on a headless server and keep
ticking while players are offline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_DAY_LENGTH = 600.0  # seconds of world time per in-game day


@dataclass
class WorldEvent:
    """A world occurrence such as a dragon attack or a market shift.

    ``kind`` is a free-form string for now; later milestones will attach
    behaviour to specific kinds. ``duration`` of ``None`` means the event
    stays active until removed.
    """

    event_id: str
    kind: str
    name: str
    started_at: float
    duration: Optional[float] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id or not self.kind:
            raise ValueError("event_id and kind are required")
        if self.duration is not None and self.duration <= 0:
            raise ValueError("duration must be positive or None")

    def has_expired(self, world_time: float) -> bool:
        return self.duration is not None and world_time >= self.started_at + self.duration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "name": self.name,
            "started_at": self.started_at,
            "duration": self.duration,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldEvent":
        return cls(
            event_id=str(data["event_id"]),
            kind=str(data["kind"]),
            name=str(data.get("name", data["kind"])),
            started_at=float(data["started_at"]),
            duration=None if data.get("duration") is None else float(data["duration"]),
            data=dict(data.get("data", {})),
        )


class WorldState:
    def __init__(self, time: float = 0.0, day_length: float = DEFAULT_DAY_LENGTH) -> None:
        if not math.isfinite(time) or time < 0:
            raise ValueError("world time must be a non-negative finite number")
        if day_length <= 0:
            raise ValueError("day_length must be positive")
        self.time = float(time)
        self.day_length = float(day_length)
        self._events: Dict[str, WorldEvent] = {}

    # ------------------------------------------------------------------- clock
    @property
    def day(self) -> int:
        """1-based world day number."""
        return int(self.time // self.day_length) + 1

    @property
    def time_of_day(self) -> float:
        """Fraction of the current day elapsed, in ``[0, 1)``."""
        return (self.time % self.day_length) / self.day_length

    def tick(self, dt: float) -> List[WorldEvent]:
        """Advance world time and return any events that expired."""
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("dt must be a non-negative finite number")
        self.time += dt
        expired = [e for e in self._events.values() if e.has_expired(self.time)]
        for event in expired:
            del self._events[event.event_id]
        return expired

    # ------------------------------------------------------------------ events
    def start_event(
        self,
        event_id: str,
        kind: str,
        name: str = "",
        duration: Optional[float] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> WorldEvent:
        if event_id in self._events:
            raise ValueError(f"event {event_id!r} is already active")
        event = WorldEvent(event_id, kind, name or kind, self.time, duration, data or {})
        self._events[event_id] = event
        return event

    def end_event(self, event_id: str) -> Optional[WorldEvent]:
        return self._events.pop(event_id, None)

    @property
    def active_events(self) -> List[WorldEvent]:
        return list(self._events.values())

    # ------------------------------------------------------------- persistence
    def to_dict(self) -> Dict[str, Any]:
        return {
            "time": self.time,
            "day_length": self.day_length,
            "events": [e.to_dict() for e in self._events.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldState":
        if not isinstance(data, dict):
            raise TypeError("world data must be an object")
        world = cls(float(data["time"]), float(data.get("day_length", DEFAULT_DAY_LENGTH)))
        for raw in data.get("events", []):
            event = WorldEvent.from_dict(raw)
            world._events[event.event_id] = event
        return world
