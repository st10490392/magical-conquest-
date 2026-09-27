"""Headless inventory: a fixed number of slots holding item stacks.

Every mutating operation is all-or-nothing and returns an explicit result,
so a failed add/remove never leaves partial changes behind (no duplication,
no silent loss). Stacks fill in slot order, which keeps behaviour
deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, List, Optional, Tuple

from game.items.definitions import ItemDefinition

DEFAULT_CAPACITY = 20


class InventoryStatus(str, Enum):
    OK = "ok"
    FULL = "inventory_full"
    INVALID_QUANTITY = "invalid_quantity"
    NOT_ENOUGH = "not_enough_items"
    UNIQUE_OWNED = "unique_already_owned"
    INVALID_SLOT = "invalid_slot"


@dataclass(frozen=True)
class InventoryResult:
    status: InventoryStatus
    item_id: Optional[str] = None
    quantity: int = 0

    @property
    def ok(self) -> bool:
        return self.status is InventoryStatus.OK


@dataclass
class ItemStack:
    item: ItemDefinition
    quantity: int


def _valid_quantity(quantity: Any) -> bool:
    return isinstance(quantity, int) and not isinstance(quantity, bool) and quantity >= 1


class Inventory:
    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an integer >= 1")
        self.capacity = capacity
        self._stacks: List[ItemStack] = []

    # ------------------------------------------------------------- queries
    @property
    def stacks(self) -> Tuple[Tuple[ItemDefinition, int], ...]:
        """Read-only snapshot: ``(item, quantity)`` per occupied slot."""
        return tuple((s.item, s.quantity) for s in self._stacks)

    @property
    def used_slots(self) -> int:
        return len(self._stacks)

    @property
    def free_slots(self) -> int:
        return self.capacity - len(self._stacks)

    def count(self, item_id: str) -> int:
        return sum(s.quantity for s in self._stacks if s.item.item_id == item_id)

    def has(self, item_id: str, quantity: int = 1) -> bool:
        return self.count(item_id) >= quantity

    def space_for(self, item: ItemDefinition) -> int:
        """How many more of ``item`` fit right now."""
        if item.unique:
            return 0 if self.count(item.item_id) else (1 if self.free_slots else 0)
        top_up = sum(item.max_stack - s.quantity for s in self._stacks if s.item.item_id == item.item_id)
        return top_up + self.free_slots * item.max_stack

    def can_add(self, item: ItemDefinition, quantity: int = 1) -> bool:
        return _valid_quantity(quantity) and self.space_for(item) >= quantity

    def can_add_all(self, items: List[Tuple[ItemDefinition, int]]) -> bool:
        """Whether several additions fit together (used for rewards)."""
        trial = self.copy()
        return all(trial.add(item, qty).ok for item, qty in items)

    # ----------------------------------------------------------- mutation
    def add(self, item: ItemDefinition, quantity: int = 1) -> InventoryResult:
        if not _valid_quantity(quantity):
            return InventoryResult(InventoryStatus.INVALID_QUANTITY, item.item_id)
        if item.unique and self.count(item.item_id):
            return InventoryResult(InventoryStatus.UNIQUE_OWNED, item.item_id)
        if self.space_for(item) < quantity:
            return InventoryResult(InventoryStatus.FULL, item.item_id)
        remaining = quantity
        for stack in self._stacks:
            if remaining and stack.item.item_id == item.item_id and stack.quantity < item.max_stack:
                moved = min(remaining, item.max_stack - stack.quantity)
                stack.quantity += moved
                remaining -= moved
        while remaining:
            moved = min(remaining, item.max_stack)
            self._stacks.append(ItemStack(item, moved))
            remaining -= moved
        return InventoryResult(InventoryStatus.OK, item.item_id, quantity)

    def remove(self, item_id: str, quantity: int = 1) -> InventoryResult:
        if not _valid_quantity(quantity):
            return InventoryResult(InventoryStatus.INVALID_QUANTITY, item_id)
        if self.count(item_id) < quantity:
            return InventoryResult(InventoryStatus.NOT_ENOUGH, item_id)
        remaining = quantity
        for stack in reversed(self._stacks):  # drain the last stacks first
            if remaining and stack.item.item_id == item_id:
                moved = min(remaining, stack.quantity)
                stack.quantity -= moved
                remaining -= moved
        self._stacks = [s for s in self._stacks if s.quantity > 0]
        return InventoryResult(InventoryStatus.OK, item_id, quantity)

    def split(self, slot: int, quantity: int) -> InventoryResult:
        """Move ``quantity`` from the stack in ``slot`` into a new slot."""
        if not 0 <= slot < len(self._stacks):
            return InventoryResult(InventoryStatus.INVALID_SLOT)
        stack = self._stacks[slot]
        if not _valid_quantity(quantity) or quantity >= stack.quantity:
            return InventoryResult(InventoryStatus.INVALID_QUANTITY, stack.item.item_id)
        if not self.free_slots:
            return InventoryResult(InventoryStatus.FULL, stack.item.item_id)
        stack.quantity -= quantity
        self._stacks.append(ItemStack(stack.item, quantity))
        return InventoryResult(InventoryStatus.OK, stack.item.item_id, quantity)

    def copy(self) -> "Inventory":
        clone = Inventory(self.capacity)
        clone._stacks = [ItemStack(s.item, s.quantity) for s in self._stacks]
        return clone

    # -------------------------------------------------------- persistence
    def to_list(self) -> List[dict]:
        return [{"item": s.item.item_id, "qty": s.quantity} for s in self._stacks]

    @classmethod
    def from_list(
        cls, data: Any, lookup: Callable[[str], ItemDefinition], capacity: int = DEFAULT_CAPACITY
    ) -> "Inventory":
        """Rebuild from saved data, treating it as untrusted input."""
        if not isinstance(data, list):
            raise TypeError("inventory must be a list")
        if len(data) > capacity:
            raise ValueError("inventory has more stacks than slots")
        inventory = cls(capacity)
        for entry in data:
            if not isinstance(entry, dict) or set(entry) != {"item", "qty"}:
                raise ValueError(f"bad inventory entry {entry!r}")
            item = lookup(entry["item"])
            quantity = entry["qty"]
            if not _valid_quantity(quantity) or quantity > item.max_stack:
                raise ValueError(f"impossible stack quantity {quantity!r} for {item.item_id}")
            if item.unique and inventory.count(item.item_id):
                raise ValueError(f"unique item {item.item_id} appears twice")
            inventory._stacks.append(ItemStack(item, quantity))
        return inventory
