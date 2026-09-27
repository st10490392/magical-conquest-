"""Loot lying in the world, waiting to be picked up."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional, Tuple

from game.core.vector import Vec2
from game.items.definitions import ItemDefinition
from game.items.inventory import InventoryResult
from game.items.loot import ItemDrop

PICKUP_RADIUS = 60.0


@dataclass
class LootDrop:
    drop_id: int
    position: Vec2
    items: List[Tuple[ItemDefinition, int]] = field(default_factory=list)


class PickupStatus(str, Enum):
    ALL = "all"  # everything picked up
    PARTIAL = "partial"  # some stacks did not fit and stay on the ground
    NOTHING = "nothing"  # nothing fit
    NO_DROP = "no_drop"


@dataclass(frozen=True)
class PickupResult:
    status: PickupStatus
    taken: Tuple[Tuple[str, int], ...] = ()
    left: Tuple[Tuple[str, int], ...] = ()


Receiver = Callable[[ItemDefinition, int], InventoryResult]


class GroundLoot:
    def __init__(self) -> None:
        self.drops: List[LootDrop] = []
        self._next_id = 1

    def spawn(self, position: Vec2, drops: List[ItemDrop], lookup: Callable[[str], ItemDefinition]) -> Optional[LootDrop]:
        if not drops:
            return None
        drop = LootDrop(self._next_id, position, [(lookup(d.item_id), d.quantity) for d in drops])
        self._next_id += 1
        self.drops.append(drop)
        return drop

    def nearest(self, position: Vec2, radius: float = PICKUP_RADIUS) -> Optional[LootDrop]:
        in_reach = [d for d in self.drops if d.position.distance_to(position) <= radius]
        return min(in_reach, key=lambda d: d.position.distance_to(position)) if in_reach else None

    def pickup(self, drop_id: int, receive: Receiver) -> PickupResult:
        """Give each stack to ``receive`` (all-or-nothing per stack)."""
        drop = next((d for d in self.drops if d.drop_id == drop_id), None)
        if drop is None:
            return PickupResult(PickupStatus.NO_DROP)
        taken, left = [], []
        for item, quantity in drop.items:
            if receive(item, quantity).ok:
                taken.append((item.item_id, quantity))
            else:
                left.append((item, quantity))
        drop.items = left
        if not left:
            self.drops.remove(drop)
        status = PickupStatus.ALL if not left else (PickupStatus.PARTIAL if taken else PickupStatus.NOTHING)
        return PickupResult(status, tuple(taken), tuple((i.item_id, q) for i, q in left))

    def clear(self) -> None:
        self.drops.clear()
