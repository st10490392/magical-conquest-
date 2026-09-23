"""Weapon definitions: data that becomes a combat ``Attack`` and a guard."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import cached_property

from game.core.combat import Attack, DamageType
from game.core.defense import MAX_BLOCK_CAPABILITY, GuardProfile


class WeaponType(str, Enum):
    SWORD = "sword"
    GREATSWORD = "greatsword"
    DAGGER = "dagger"
    SPEAR = "spear"
    STAFF = "staff"


@dataclass(frozen=True)
class Weapon:
    """A weapon profile. ``block_capability`` is the share of damage a block
    absorbs (0 = cannot block, capped below 1 so blocking is never total)."""

    weapon_id: str
    name: str
    weapon_type: WeaponType
    base_power: float
    strength_scaling: float = 1.0
    reach: float = 70.0
    stamina_cost: float = 8.0
    cooldown: float = 0.5
    block_capability: float = 0.0
    can_parry: bool = False

    def __post_init__(self) -> None:
        if not self.weapon_id or not self.name:
            raise ValueError("weapon_id and name are required")
        if not isinstance(self.weapon_type, WeaponType):
            raise TypeError("weapon_type must be a WeaponType")
        for label in ("base_power", "strength_scaling", "reach", "stamina_cost", "cooldown"):
            if getattr(self, label) < 0:
                raise ValueError(f"{label} must not be negative")
        if not 0.0 <= self.block_capability <= MAX_BLOCK_CAPABILITY:
            raise ValueError(f"block_capability must be within 0..{MAX_BLOCK_CAPABILITY}")

    @property
    def can_block(self) -> bool:
        return self.block_capability > 0.0

    @cached_property
    def attack(self) -> Attack:
        return Attack(
            name=self.weapon_id,
            damage_type=DamageType.PHYSICAL,
            base_power=self.base_power,
            scaling=self.strength_scaling,
            reach=self.reach,
            cooldown=self.cooldown,
            stamina_cost=self.stamina_cost,
        )

    @cached_property
    def guard(self) -> GuardProfile:
        return GuardProfile(self.block_capability, self.can_parry)
