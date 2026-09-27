"""Tiny prototype item catalog.

PROTOTYPE / NON-CANON CONTENT. Names, values and stats are NON-FINAL.
No legendary or canonical equipment is defined here.
"""

from __future__ import annotations

from typing import Dict

from game.equipment.catalog import WEAPONS
from game.equipment.slots import EquipSlot, StatModifiers
from game.equipment.weapons import Weapon
from game.items.definitions import ArmorProfile, ConsumableEffect, ItemCategory, ItemDefinition, Rarity

C, R = ItemCategory, Rarity


def _armor(item_id, name, slot, rarity, value, description, **mods):
    return ItemDefinition(item_id, name, C.ARMOR, description, rarity, base_value=value,
                          armor=ArmorProfile(slot, StatModifiers.of(**mods)))


_WEAPON_VALUES = {
    "iron_sword": (R.COMMON, 40),
    "iron_greatsword": (R.UNCOMMON, 70),
    "steel_dagger": (R.COMMON, 30),
    "ash_spear": (R.COMMON, 45),
    "oak_staff": (R.COMMON, 25),
}

_ITEMS = (
    *(ItemDefinition.for_weapon(WEAPONS[wid], rarity, value) for wid, (rarity, value) in _WEAPON_VALUES.items()),
    _armor("leather_cap", "Leather Cap", EquipSlot.HEAD, R.COMMON, 12, "Soft leather cap.", durability=2),
    _armor("iron_helm", "Iron Helm", EquipSlot.HEAD, R.UNCOMMON, 35, "Dented but solid.", durability=5),
    _armor("warding_hood", "Warding Hood", EquipSlot.HEAD, R.UNCOMMON, 30, "Stitched with protective thread.",
           magic_resistance=6),
    _armor("leather_jerkin", "Leather Jerkin", EquipSlot.CHEST, R.COMMON, 20, "Padded leather.",
           durability=4, magic_resistance=1),
    _armor("leather_gloves", "Leather Gloves", EquipSlot.HANDS, R.COMMON, 10, "A good grip.", agility=4),
    _armor("leather_greaves", "Leather Greaves", EquipSlot.LEGS, R.COMMON, 14, "Shin guards.", durability=2),
    _armor("traveler_boots", "Traveler Boots", EquipSlot.FEET, R.COMMON, 15, "Light boots.", speed=15),
    ItemDefinition("minor_health_potion", "Minor Health Potion", C.CONSUMABLE, "Restores 40 health.",
                   max_stack=10, base_value=15, consumable=ConsumableEffect(restore_health=40)),
    ItemDefinition("minor_mana_potion", "Minor Mana Potion", C.CONSUMABLE, "Restores 30 mana.",
                   max_stack=10, base_value=15, consumable=ConsumableEffect(restore_mana=30)),
    ItemDefinition("stamina_tonic", "Stamina Tonic", C.CONSUMABLE, "Restores 50 stamina.",
                   max_stack=10, base_value=10, consumable=ConsumableEffect(restore_stamina=50)),
    ItemDefinition("bone_shard", "Bone Shard", C.MATERIAL, "A crafting material.", max_stack=20, base_value=3),
    ItemDefinition("tattered_cloth", "Tattered Cloth", C.MATERIAL, "Scraps of cloth.", max_stack=20, base_value=2),
    ItemDefinition("iron_scrap", "Iron Scrap", C.MATERIAL, "Bent metal.", R.UNCOMMON, max_stack=20, base_value=6),
    ItemDefinition("old_coin", "Old Coin", C.MISC, "Worn, of no known realm.", max_stack=50, base_value=5),
    ItemDefinition("sealed_letter", "Sealed Letter", C.QUEST, "Not yours to open.", sellable=False),
)

ITEMS: Dict[str, ItemDefinition] = {item.item_id: item for item in _ITEMS}
assert len(ITEMS) == len(_ITEMS), "duplicate item ids"


def get_item(item_id: str) -> ItemDefinition:
    try:
        return ITEMS[item_id]
    except (KeyError, TypeError):
        raise ValueError(f"unknown item {item_id!r}") from None


def item_for(equippable) -> ItemDefinition:
    """The catalog item for something equipped (an ItemDefinition or bare Weapon)."""
    if isinstance(equippable, ItemDefinition):
        return equippable
    if isinstance(equippable, Weapon):
        item = ITEMS.get(equippable.weapon_id)
        if item is not None and item.weapon == equippable:
            return item
        return ItemDefinition.for_weapon(equippable)
    raise TypeError(f"{equippable!r} is not an item")
