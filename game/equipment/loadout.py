"""Equipped items. Only the main hand exists for now; armor and other slots
can be added as new ``EquipSlot`` members without changing callers."""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional

from game.core.defense import GuardProfile
from game.equipment.weapons import Weapon


class EquipSlot(str, Enum):
    MAIN_HAND = "main_hand"


class Equipment:
    def __init__(self) -> None:
        self._slots: Dict[EquipSlot, Weapon] = {}

    @property
    def weapon(self) -> Optional[Weapon]:
        return self._slots.get(EquipSlot.MAIN_HAND)

    def equip(self, weapon: Weapon) -> Optional[Weapon]:
        """Equip ``weapon`` in the main hand; returns what it replaced."""
        if not isinstance(weapon, Weapon):
            raise TypeError("only Weapon objects can be equipped")
        previous = self._slots.get(EquipSlot.MAIN_HAND)
        self._slots[EquipSlot.MAIN_HAND] = weapon
        return previous

    def unequip(self, slot: EquipSlot = EquipSlot.MAIN_HAND) -> Optional[Weapon]:
        return self._slots.pop(slot, None)

    def guard_profile(self) -> GuardProfile:
        weapon = self.weapon
        return weapon.guard if weapon else GuardProfile()
