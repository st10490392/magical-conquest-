"""Spell definitions: pure data, turned into combat ``Attack``s on demand."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from game.core.combat import Attack, DamageType
from game.magic.attributes import MagicAttribute
from game.magic.ranks import RANK_MIN_MAGIC_POWER, SpellRank


@dataclass(frozen=True)
class Spell:
    """A castable spell. All numbers are prototype values.

    ``min_magic_power`` is combined with the rank floor in
    ``RANK_MIN_MAGIC_POWER`` (the higher value wins), so no spell can be made
    castable below its rank's minimum by accident.
    """

    spell_id: str
    name: str
    rank: SpellRank
    element: MagicAttribute
    base_power: float
    magic_scaling: float = 1.0
    mana_cost: float = 10.0
    cooldown: float = 1.0
    reach: float = 250.0
    min_magic_power: float = 0.0
    min_level: int = 1

    def __post_init__(self) -> None:
        if not self.spell_id or not self.name:
            raise ValueError("spell_id and name are required")
        if not isinstance(self.rank, SpellRank) or not isinstance(self.element, MagicAttribute):
            raise TypeError("rank must be a SpellRank and element a MagicAttribute")
        for label in ("base_power", "magic_scaling", "mana_cost", "cooldown", "reach", "min_magic_power"):
            if getattr(self, label) < 0:
                raise ValueError(f"{label} must not be negative")
        if self.min_level < 1:
            raise ValueError("min_level must be >= 1")

    @property
    def required_magic_power(self) -> float:
        return max(self.min_magic_power, RANK_MIN_MAGIC_POWER[self.rank])

    @cached_property
    def attack(self) -> Attack:
        return Attack(
            name=self.spell_id,
            damage_type=DamageType.MAGIC,
            base_power=self.base_power,
            scaling=self.magic_scaling,
            reach=self.reach,
            cooldown=self.cooldown,
            mana_cost=self.mana_cost,
            element=self.element,
        )
