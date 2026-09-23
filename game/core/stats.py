"""Reusable stat block shared by players, monsters and NPCs.

Nothing here knows about players, levels or rendering. A ``Stats`` object is a
set of resource pools (health, mana, stamina) plus combat attributes, with
validated mutation helpers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Any, Dict

POOL_NAMES = ("health", "mana", "stamina")
ATTRIBUTE_NAMES = (
    "physical_strength",
    "magic_power",
    "magic_resistance",
    "durability",
    "speed",
    "agility",
)


def _check_number(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if value < 0:
        raise ValueError(f"{name} must not be negative, got {value!r}")
    return float(value)


@dataclass
class Stats:
    """Resource pools and attributes for any living entity.

    Pools (``health``, ``mana``, ``stamina``) always stay within
    ``0..max_<pool>``. Attributes are non-negative numbers whose meaning is
    defined by the systems that read them (combat, movement, ...).
    """

    max_health: float = 100.0
    max_mana: float = 50.0
    max_stamina: float = 100.0
    physical_strength: float = 10.0
    magic_power: float = 10.0
    magic_resistance: float = 0.0
    durability: float = 0.0
    speed: float = 150.0
    agility: float = 0.0
    health: float | None = None
    mana: float | None = None
    stamina: float | None = None

    def __post_init__(self) -> None:
        # Omitted current pools start full.
        if self.health is None:
            self.health = self.max_health
        if self.mana is None:
            self.mana = self.max_mana
        if self.stamina is None:
            self.stamina = self.max_stamina
        self.validate()

    # ------------------------------------------------------------------ checks
    def validate(self) -> None:
        """Raise ``TypeError``/``ValueError`` if any value is invalid."""
        for f in fields(self):
            setattr(self, f.name, _check_number(f.name, getattr(self, f.name)))
        if self.max_health <= 0:
            raise ValueError("max_health must be greater than zero")
        for pool in POOL_NAMES:
            current = getattr(self, pool)
            maximum = getattr(self, f"max_{pool}")
            if current > maximum:
                raise ValueError(f"{pool} ({current}) exceeds max_{pool} ({maximum})")

    @property
    def is_alive(self) -> bool:
        return self.health > 0

    # ------------------------------------------------------------------ health
    def take_damage(self, amount: float) -> float:
        """Reduce health by ``amount`` and return the damage actually applied."""
        amount = _check_number("damage", amount)
        applied = min(amount, self.health)
        self.health -= applied
        return applied

    def heal(self, amount: float) -> float:
        """Restore health up to ``max_health``. Dead entities cannot be healed."""
        amount = _check_number("heal", amount)
        if not self.is_alive:
            return 0.0
        return self._restore("health", amount)

    # --------------------------------------------------------- mana / stamina
    def consume_mana(self, amount: float) -> bool:
        return self._consume("mana", amount)

    def restore_mana(self, amount: float) -> float:
        return self._restore("mana", amount)

    def consume_stamina(self, amount: float) -> bool:
        return self._consume("stamina", amount)

    def restore_stamina(self, amount: float) -> float:
        return self._restore("stamina", amount)

    def _consume(self, pool: str, amount: float) -> bool:
        """Spend ``amount`` from ``pool``; all-or-nothing. Returns success."""
        amount = _check_number(pool, amount)
        current = getattr(self, pool)
        if amount > current:
            return False
        setattr(self, pool, current - amount)
        return True

    def _restore(self, pool: str, amount: float) -> float:
        amount = _check_number(pool, amount)
        current = getattr(self, pool)
        new_value = min(current + amount, getattr(self, f"max_{pool}"))
        setattr(self, pool, new_value)
        return new_value - current

    # ------------------------------------------------------------ max changes
    def increase_max(self, pool: str, amount: float, refill: bool = True) -> None:
        """Grow a pool's maximum (e.g. on level-up), optionally refilling it."""
        if pool not in POOL_NAMES:
            raise ValueError(f"unknown pool {pool!r}")
        amount = _check_number(pool, amount)
        setattr(self, f"max_{pool}", getattr(self, f"max_{pool}") + amount)
        if refill:
            setattr(self, pool, getattr(self, f"max_{pool}"))

    def increase_attribute(self, name: str, amount: float) -> None:
        if name not in ATTRIBUTE_NAMES:
            raise ValueError(f"unknown attribute {name!r}")
        amount = _check_number(name, amount)
        setattr(self, name, getattr(self, name) + amount)

    # ------------------------------------------------------------ persistence
    def to_dict(self) -> Dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Stats":
        if not isinstance(data, dict):
            raise TypeError("stats data must be an object")
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown stat fields: {sorted(unknown)}")
        return cls(**data)
