"""Formula-based XP/level progression.

No lookup tables: the XP needed for the next level is computed from a
configurable curve, so very high level caps cost nothing in memory. The
default curve is a placeholder and is not balanced for late game.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProgressionCurve:
    """``xp_to_next(level) = base * level ** exponent`` (rounded, at least 1)."""

    base: float = 100.0
    exponent: float = 1.5
    max_level: Optional[int] = None

    def __post_init__(self) -> None:
        if self.base <= 0 or self.exponent < 0:
            raise ValueError("base must be > 0 and exponent >= 0")
        if self.max_level is not None and self.max_level < 1:
            raise ValueError("max_level must be >= 1")

    def xp_to_next(self, level: int) -> int:
        if level < 1:
            raise ValueError("level must be >= 1")
        return max(1, round(self.base * level ** self.exponent))

    def is_capped(self, level: int) -> bool:
        return self.max_level is not None and level >= self.max_level


@dataclass(frozen=True)
class LevelUpResult:
    old_level: int
    new_level: int
    xp: int

    @property
    def levels_gained(self) -> int:
        return self.new_level - self.old_level


class Experience:
    """XP carried towards the next level. The level itself is passed in and
    returned so it can live on the owning entity without duplication."""

    def __init__(self, xp: int = 0, curve: Optional[ProgressionCurve] = None) -> None:
        if isinstance(xp, bool) or not isinstance(xp, int) or xp < 0:
            raise ValueError(f"xp must be a non-negative integer, got {xp!r}")
        self.xp = xp
        self.curve = curve or ProgressionCurve()

    def add(self, level: int, amount: int) -> LevelUpResult:
        """Add XP, rolling over as many level thresholds as it covers."""
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ValueError(f"xp amount must be a non-negative integer, got {amount!r}")
        old_level = level
        self.xp += amount
        while not self.curve.is_capped(level) and self.xp >= self.curve.xp_to_next(level):
            self.xp -= self.curve.xp_to_next(level)
            level += 1
        if self.curve.is_capped(level):
            self.xp = 0
        return LevelUpResult(old_level, level, self.xp)
