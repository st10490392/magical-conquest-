"""Merchant prices from item base value, rarity and merchant margins.

buy  = ceil(base_value * rarity multiplier * markup), at least 1
sell = floor(base_value * rarity multiplier * buyback)

PROTOTYPE numbers - NON-FINAL. Rarity scales price only; it never makes an
item stronger (item stats come from the item definition).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from game.items.definitions import ItemDefinition


@dataclass(frozen=True)
class PricePolicy:
    markup: float = 1.0
    buyback: float = 0.4

    def __post_init__(self) -> None:
        if not (self.markup > 0 and 0 < self.buyback <= self.markup):
            raise ValueError("need markup > 0 and 0 < buyback <= markup (no buy-low/sell-high loop)")

    def value(self, item: ItemDefinition) -> float:
        return item.base_value * item.rarity.value_multiplier

    def buy_price(self, item: ItemDefinition) -> int:
        return max(1, math.ceil(self.value(item) * self.markup))

    def sell_price(self, item: ItemDefinition) -> int:
        """0 means the merchant will not pay anything for it."""
        if not item.sellable:
            return 0
        return math.floor(self.value(item) * self.buyback)
