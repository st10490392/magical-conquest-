"""What an entity has equipped, one item per ``EquipSlot``.

Anything with ``item_id``, ``equip_slot``, ``modifiers`` and ``weapon``
(a ``Weapon`` or ``None``) can be equipped: a bare MC-002 ``Weapon`` or an
MC-004 ``ItemDefinition``. Stat modifiers are *summed* here; the owner
applies the difference to its stats (see ``Player``), which keeps them
reversible.
"""

from __future__ import annotations

from typing import Dict, Optional, Protocol

from game.core.defense import GuardProfile
from game.equipment.slots import ARMOR_SLOTS, EquipSlot, StatModifiers
from game.equipment.weapons import Weapon

__all__ = ["ARMOR_SLOTS", "EquipSlot", "Equippable", "Equipment"]


class Equippable(Protocol):
    @property
    def item_id(self) -> str: ...

    @property
    def equip_slot(self) -> Optional[EquipSlot]: ...

    @property
    def modifiers(self) -> StatModifiers: ...

    @property
    def weapon(self) -> Optional[Weapon]: ...


class Equipment:
    def __init__(self) -> None:
        self._slots: Dict[EquipSlot, Equippable] = {}

    @property
    def weapon(self) -> Optional[Weapon]:
        item = self._slots.get(EquipSlot.MAIN_HAND)
        return item.weapon if item is not None else None

    def get(self, slot: EquipSlot) -> Optional[Equippable]:
        return self._slots.get(slot)

    def items(self) -> Dict[EquipSlot, Equippable]:
        """Equipped items in slot order."""
        return {slot: self._slots[slot] for slot in EquipSlot if slot in self._slots}

    def equip(self, item: Equippable) -> Optional[Equippable]:
        """Equip ``item`` in its slot; returns what it replaced."""
        slot = getattr(item, "equip_slot", None)
        if not isinstance(slot, EquipSlot):
            raise TypeError(f"{item!r} cannot be equipped")
        if slot is EquipSlot.MAIN_HAND and item.weapon is None:
            raise TypeError("only weapons go in the main hand")
        previous = self._slots.get(slot)
        self._slots[slot] = item
        return previous

    def unequip(self, slot: EquipSlot = EquipSlot.MAIN_HAND) -> Optional[Equippable]:
        return self._slots.pop(slot, None)

    def total_modifiers(self) -> Dict[str, float]:
        return StatModifiers.total(item.modifiers for item in self._slots.values())

    def guard_profile(self) -> GuardProfile:
        weapon = self.weapon
        return weapon.guard if weapon else GuardProfile()
