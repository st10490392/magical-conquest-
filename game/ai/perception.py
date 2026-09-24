"""Lightweight, deterministic perception: distance-based detection with a
larger disengage range so enemies do not flicker in and out of combat.

Out of scope for now: stealth, line of sight, aggro tables.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from game.core.entity import Entity


@dataclass(frozen=True)
class PerceptionConfig:
    detection_range: float = 400.0  # notice a target this close
    disengage_range: float = 600.0  # once engaged, give up beyond this

    def __post_init__(self) -> None:
        if self.detection_range < 0 or self.disengage_range < self.detection_range:
            raise ValueError("need 0 <= detection_range <= disengage_range")


@dataclass(frozen=True)
class Percept:
    target: Optional[Entity]
    valid: bool  # a living target exists
    distance: float
    engaged: bool  # inside detection (or disengage range if already engaged)


NO_TARGET = Percept(None, False, math.inf, False)


def perceive(observer: Entity, target: Optional[Entity], config: PerceptionConfig, was_engaged: bool) -> Percept:
    if target is None or not target.is_alive or target is observer:
        return NO_TARGET
    distance = observer.distance_to(target)
    limit = config.disengage_range if was_engaged else config.detection_range
    return Percept(target, True, distance, distance <= limit)
