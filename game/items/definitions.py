"""Static item definitions. Runtime state (quantities, ownership) lives in
``Inventory`` and ``Equipment``; definitions are shared and immutable."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from game.equipment.slots import ARMOR_SLOTS, NO_MODIFIERS, EquipSlot, StatModifiers
from game.equipment.weapons import Weapon


class ItemCategory(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    CONSUMABLE = "consumable"
    MATERIAL = "material"
    QUEST = "quest"
    MISC = "misc"


class Rarity(str, Enum):
    """PROTOTYPE rarity tiers - names and multipliers are NON-FINAL.

    Rarity only scales *value* (for merchants). It never sets an item's
    power; an item's stats come from its own definition.
    """

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    UNIQUE = "unique"  # reserved for one-of-a-kind items (none exist yet)

    @property
    def value_multiplier(self) -> float:
        return _VALUE_MULTIPLIERS[self]


_VALUE_MULTIPLIERS = {
    Rarity.COMMON: 1.0,
    Rarity.UNCOMMON: 1.5,
    Rarity.RARE: 2.5,
    Rarity.EPIC: 4.0,
    Rarity.UNIQUE: 6.0,
}


@dataclass(frozen=True)
class ArmorProfile:
    slot: EquipSlot
    modifiers: StatModifiers

    def __post_init__(self) -> None:
        if self.slot not in ARMOR_SLOTS:
            raise ValueError(f"{self.slot} is not an armor slot")


@dataclass(frozen=True)
class ConsumableEffect:
    restore_health: float = 0.0
    restore_mana: float = 0.0
    restore_stamina: float = 0.0

    def __post_init__(self) -> None:
        values = (self.restore_health, self.restore_mana, self.restore_stamina)
        if any(v < 0 for v in values) or not any(values):
            raise ValueError("a consumable must restore something, with no negative amounts")


@dataclass(frozen=True)
class ItemDefinition:
    """One kind of item. ``item_id`` is the stable ID used in saves.

    ``unique``: at most one may be owned (inventory + equipment). This is the
    hook for future one-of-a-kind items; none are defined yet.
    ``sellable``: False for quest items (used by merchants from MC-007).
    """

    item_id: str
    name: str
    category: ItemCategory
    description: str = ""
    rarity: Rarity = Rarity.COMMON
    max_stack: int = 1
    base_value: int = 0
    unique: bool = False
    sellable: bool = True
    weapon: Optional[Weapon] = None
    armor: Optional[ArmorProfile] = None
    consumable: Optional[ConsumableEffect] = None

    def __post_init__(self) -> None:
        if not self.item_id or not self.item_id.replace("_", "").isalnum() or self.item_id != self.item_id.lower():
            raise ValueError(f"item_id must be lower_snake_case, got {self.item_id!r}")
        if not self.name:
            raise ValueError("name is required")
        if not isinstance(self.category, ItemCategory) or not isinstance(self.rarity, Rarity):
            raise TypeError("category/rarity must be enums")
        if isinstance(self.max_stack, bool) or not isinstance(self.max_stack, int) or self.max_stack < 1:
            raise ValueError("max_stack must be an integer >= 1")
        if isinstance(self.base_value, bool) or not isinstance(self.base_value, int) or self.base_value < 0:
            raise ValueError("base_value must be an integer >= 0")
        payloads = {
            ItemCategory.WEAPON: self.weapon,
            ItemCategory.ARMOR: self.armor,
            ItemCategory.CONSUMABLE: self.consumable,
        }
        for category, payload in payloads.items():
            if (self.category is category) != (payload is not None):
                raise ValueError(f"{self.item_id}: {category.value} data must be set exactly for {category.value} items")
        if self.equip_slot is not None and self.max_stack != 1:
            raise ValueError("equippable items cannot stack")
        if self.unique and self.max_stack != 1:
            raise ValueError("unique items cannot stack")
        if self.category is ItemCategory.QUEST and self.sellable:
            raise ValueError("quest items are not sellable")

    @property
    def stackable(self) -> bool:
        return self.max_stack > 1

    # Equippable protocol (see game.equipment.loadout).
    @property
    def equip_slot(self) -> Optional[EquipSlot]:
        if self.weapon is not None:
            return EquipSlot.MAIN_HAND
        if self.armor is not None:
            return self.armor.slot
        return None

    @property
    def modifiers(self) -> StatModifiers:
        return self.armor.modifiers if self.armor is not None else NO_MODIFIERS

    @classmethod
    def for_weapon(cls, weapon: Weapon, rarity: Rarity = Rarity.COMMON, base_value: int = 0) -> "ItemDefinition":
        return cls(
            weapon.weapon_id, weapon.name, ItemCategory.WEAPON,
            description=f"A {weapon.weapon_type.value}.", rarity=rarity, base_value=base_value, weapon=weapon,
        )
