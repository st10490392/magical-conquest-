"""Per-level stat growth. Configurable data, not a table per level."""

from __future__ import annotations

from dataclasses import dataclass

from game.core.stats import Stats


@dataclass(frozen=True)
class StatGrowth:
    """Flat stat increase granted for each level gained."""

    max_health: float = 12.0
    max_mana: float = 6.0
    max_stamina: float = 5.0
    physical_strength: float = 2.0
    magic_power: float = 2.0
    durability: float = 1.5
    magic_resistance: float = 1.5
    agility: float = 0.5

    def apply(self, stats: Stats, levels: int, refill: bool = True) -> None:
        if levels <= 0:
            return
        stats.increase_max("health", self.max_health * levels, refill=refill)
        stats.increase_max("mana", self.max_mana * levels, refill=refill)
        stats.increase_max("stamina", self.max_stamina * levels, refill=refill)
        for name in ("physical_strength", "magic_power", "durability", "magic_resistance", "agility"):
            stats.increase_attribute(name, getattr(self, name) * levels)
