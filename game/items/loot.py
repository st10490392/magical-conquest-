"""Explicit, inspectable loot tables.

Randomness only comes from an injected ``random.Random`` so every roll is
reproducible from a seed. Entries with ``chance=1`` and a fixed quantity are
guaranteed and consume no randomness at all.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class LootEntry:
    """Independent roll: drops with probability ``chance`` (1.0 = always)."""

    item_id: str
    chance: float = 1.0
    min_qty: int = 1
    max_qty: int = 1

    def __post_init__(self) -> None:
        if not 0.0 < self.chance <= 1.0:
            raise ValueError("chance must be within (0, 1]")
        if not 1 <= self.min_qty <= self.max_qty:
            raise ValueError("need 1 <= min_qty <= max_qty")


@dataclass(frozen=True)
class WeightedPick:
    """One option in a weighted pool; ``item_id=None`` means "nothing"."""

    item_id: Optional[str]
    weight: int
    min_qty: int = 1
    max_qty: int = 1

    def __post_init__(self) -> None:
        if self.weight < 1 or not 1 <= self.min_qty <= self.max_qty:
            raise ValueError("weight must be >= 1 and 1 <= min_qty <= max_qty")


@dataclass(frozen=True)
class ItemDrop:
    item_id: str
    quantity: int


@dataclass(frozen=True)
class LootTable:
    table_id: str
    entries: Tuple[LootEntry, ...] = ()
    pool: Tuple[WeightedPick, ...] = ()
    pool_picks: int = 0  # how many times to pick from ``pool``

    def __post_init__(self) -> None:
        if self.pool_picks and not self.pool:
            raise ValueError("pool_picks needs a pool")

    @property
    def guaranteed(self) -> Tuple[LootEntry, ...]:
        return tuple(e for e in self.entries if e.chance >= 1.0)

    def roll(self, rng: random.Random) -> List[ItemDrop]:
        """Roll the table; quantities of the same item are merged."""
        totals: Dict[str, int] = {}

        def add(item_id: str, low: int, high: int) -> None:
            quantity = low if low == high else rng.randint(low, high)
            totals[item_id] = totals.get(item_id, 0) + quantity

        for entry in self.entries:
            if entry.chance >= 1.0 or rng.random() < entry.chance:
                add(entry.item_id, entry.min_qty, entry.max_qty)
        if self.pool_picks:
            total_weight = sum(p.weight for p in self.pool)
            for _ in range(self.pool_picks):
                point = rng.randrange(total_weight)
                for pick in self.pool:
                    if point < pick.weight:
                        if pick.item_id is not None:
                            add(pick.item_id, pick.min_qty, pick.max_qty)
                        break
                    point -= pick.weight
        return [ItemDrop(item_id, qty) for item_id, qty in totals.items()]

    def item_ids(self) -> List[str]:
        ids = [e.item_id for e in self.entries] + [p.item_id for p in self.pool if p.item_id]
        return list(dict.fromkeys(ids))


def validate_tables(tables: Dict[str, LootTable], item_exists: Callable[[str], bool]) -> None:
    for table in tables.values():
        for item_id in table.item_ids():
            if not item_exists(item_id):
                raise ValueError(f"loot table {table.table_id} references unknown item {item_id!r}")
