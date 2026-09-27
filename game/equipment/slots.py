"""Equipment slots and reversible stat modifiers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Mapping, Tuple

from game.core.stats import ATTRIBUTE_NAMES


class EquipSlot(str, Enum):
    MAIN_HAND = "main_hand"  # the weapon slot
    HEAD = "head"
    CHEST = "chest"
    HANDS = "hands"
    LEGS = "legs"
    FEET = "feet"


ARMOR_SLOTS = (EquipSlot.HEAD, EquipSlot.CHEST, EquipSlot.HANDS, EquipSlot.LEGS, EquipSlot.FEET)

# Modifiers only touch attributes, never pool maximums, so equipping can never
# leave current health/mana/stamina above a maximum. (Pool modifiers deferred.)
MODIFIABLE_STATS = ATTRIBUTE_NAMES


@dataclass(frozen=True)
class StatModifiers:
    """Flat, non-negative attribute bonuses, e.g. ``{"durability": 4}``."""

    values: Tuple[Tuple[str, float], ...] = ()

    @classmethod
    def of(cls, **bonuses: float) -> "StatModifiers":
        return cls(tuple(sorted(bonuses.items())))

    def __post_init__(self) -> None:
        for name, value in self.values:
            if name not in MODIFIABLE_STATS:
                raise ValueError(f"cannot modify {name!r}; allowed: {MODIFIABLE_STATS}")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"modifier {name} must be a finite number >= 0")

    def as_dict(self) -> Dict[str, float]:
        return dict(self.values)

    @staticmethod
    def total(modifiers: Iterable["StatModifiers"]) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for modifier in modifiers:
            for name, value in modifier.values:
                totals[name] = totals.get(name, 0.0) + value
        return totals


NO_MODIFIERS = StatModifiers()


def describe(modifiers: Mapping[str, float]) -> str:
    return ", ".join(f"+{value:g} {name.replace('_', ' ')}" for name, value in sorted(modifiers.items())) or "none"
