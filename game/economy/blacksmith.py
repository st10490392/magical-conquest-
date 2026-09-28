"""Blacksmith services foundation.

Magical Conquest expects players to visit crafters/blacksmiths for better
gear rather than upgrading everything themselves. For now a blacksmith
*sells* weapons/armor (a normal ``Merchant`` with the SHOP service) and can
*inspect* gear. Upgrading, repair, crafting and weapon grades are NOT
designed yet, so they are intentionally not implemented: add a new
``ServiceType`` plus a handler here when those rules exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from game.economy.merchant import Merchant, ServiceType
from game.entities.player import Player
from game.equipment.slots import describe
from game.items.catalog import item_for
from game.items.definitions import ItemDefinition


@dataclass(frozen=True)
class GearReport:
    slot: Optional[str]
    name: str
    category: str
    rarity: str
    details: str
    sell_price: int


def inspect_item(merchant: Merchant, item: ItemDefinition, slot: Optional[str] = None) -> GearReport:
    parts: List[str] = []
    if item.weapon is not None:
        w = item.weapon
        parts.append(f"{w.weapon_type.value}: power {w.base_power:g} (+{w.strength_scaling:g}x strength), "
                     f"reach {w.reach:g}, {w.cooldown:g}s, stamina {w.stamina_cost:g}, "
                     f"block {w.block_capability:.0%}, parry {'yes' if w.can_parry else 'no'}")
    if item.armor is not None:
        parts.append(f"{item.armor.slot.value}: {describe(item.modifiers.as_dict())}")
    if item.consumable is not None:
        parts.append(item.description)
    return GearReport(slot, item.name, item.category.value, item.rarity.value,
                      "; ".join(parts) or item.description, merchant.sell_price(item))


def inspect_equipment(merchant: Merchant, player: Player) -> Tuple[GearReport, ...]:
    """What the blacksmith says about the player's equipped gear."""
    if not merchant.has_service(ServiceType.INSPECT):
        return ()
    return tuple(inspect_item(merchant, item_for(item), slot.value)
                 for slot, item in player.equipment.items().items())
