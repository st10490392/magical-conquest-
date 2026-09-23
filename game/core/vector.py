"""Tiny 2D vector used for positions and movement in the prototype.

Kept independent of ``pygame.math.Vector2`` so rules and tests do not need
Pygame, and so a future engine can map its own vector type onto this one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Vec2:
    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def distance_to(self, other: "Vec2") -> float:
        return (other - self).length()

    def normalized(self) -> "Vec2":
        length = self.length()
        if length == 0:
            return Vec2()
        return Vec2(self.x / length, self.y / length)

    def clamped(self, min_x: float, min_y: float, max_x: float, max_y: float) -> "Vec2":
        return Vec2(min(max(self.x, min_x), max_x), min(max(self.y, min_y), max_y))
