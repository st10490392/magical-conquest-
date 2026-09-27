"""Player-facing item actions that span inventory and equipment.

Each action validates everything first and then mutates, so a failure never
leaves the player half-changed (e.g. an item removed but not equipped).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from game.entities.player import Player
from game.equipment.slots import EquipSlot
from game.items.catalog import get_item, item_for
from game.items.definitions import ItemDefinition
from game.items.inventory import InventoryResult, InventoryStatus


class ItemActionStatus(str, Enum):
    OK = "ok"
    NOT_IN_INVENTORY = "not_in_inventory"
    NOT_EQUIPPABLE = "not_equippable"
    NOT_CONSUMABLE = "not_consumable"
    NO_EFFECT = "no_effect"
    DEAD = "dead"
    INVENTORY_FULL = "inventory_full"
    SLOT_EMPTY = "slot_empty"


@dataclass(frozen=True)
class ItemActionResult:
    status: ItemActionStatus
    item_id: Optional[str] = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status is ItemActionStatus.OK


def give_item(player: Player, item: ItemDefinition, quantity: int = 1) -> InventoryResult:
    """Add items to the player's inventory, respecting unique ownership
    across inventory *and* equipment."""
    if item.unique and player.owned_count(item.item_id):
        return InventoryResult(InventoryStatus.UNIQUE_OWNED, item.item_id)
    return player.inventory.add(item, quantity)


def equip_from_inventory(player: Player, item_id: str) -> ItemActionResult:
    """Move one item from the inventory into its slot; whatever was in that
    slot goes back into the freed inventory slot."""
    if not player.is_alive:
        return ItemActionResult(ItemActionStatus.DEAD, item_id)
    if not player.inventory.has(item_id):
        return ItemActionResult(ItemActionStatus.NOT_IN_INVENTORY, item_id)
    item = get_item(item_id)
    if item.equip_slot is None:
        return ItemActionResult(ItemActionStatus.NOT_EQUIPPABLE, item_id)
    player.inventory.remove(item_id, 1)  # frees a slot: equippables never stack
    previous = player.equip(item)
    if previous is not None:
        returned = player.inventory.add(item_for(previous), 1)
        assert returned.ok, "a slot was just freed"
    return ItemActionResult(ItemActionStatus.OK, item_id)


def unequip_to_inventory(player: Player, slot: EquipSlot) -> ItemActionResult:
    equipped = player.equipment.get(slot)
    if equipped is None:
        return ItemActionResult(ItemActionStatus.SLOT_EMPTY)
    item = item_for(equipped)
    if not player.inventory.can_add(item, 1):
        return ItemActionResult(ItemActionStatus.INVENTORY_FULL, item.item_id)
    player.unequip(slot)
    player.inventory.add(item, 1)
    return ItemActionResult(ItemActionStatus.OK, item.item_id)


def use_item(player: Player, item_id: str) -> ItemActionResult:
    """Consume one consumable. Refuses (and keeps the item) if it would do
    nothing, e.g. a health potion at full health."""
    if not player.is_alive:
        return ItemActionResult(ItemActionStatus.DEAD, item_id)
    if not player.inventory.has(item_id):
        return ItemActionResult(ItemActionStatus.NOT_IN_INVENTORY, item_id)
    item = get_item(item_id)
    effect = item.consumable
    if effect is None:
        return ItemActionResult(ItemActionStatus.NOT_CONSUMABLE, item_id)
    stats = player.stats
    useful = (
        (effect.restore_health and stats.health < stats.max_health)
        or (effect.restore_mana and stats.mana < stats.max_mana)
        or (effect.restore_stamina and stats.stamina < stats.max_stamina)
    )
    if not useful:
        return ItemActionResult(ItemActionStatus.NO_EFFECT, item_id)
    player.inventory.remove(item_id, 1)
    restored = []
    if effect.restore_health:
        restored.append(f"{stats.heal(effect.restore_health):.0f} HP")
    if effect.restore_mana:
        restored.append(f"{stats.restore_mana(effect.restore_mana):.0f} MP")
    if effect.restore_stamina:
        restored.append(f"{stats.restore_stamina(effect.restore_stamina):.0f} ST")
    return ItemActionResult(ItemActionStatus.OK, item_id, ", ".join(restored))
