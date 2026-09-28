"""Merchants: stock, prices and atomic buy/sell transactions.

Every transaction validates everything first and only then mutates, in an
order where the later steps cannot fail. So a failed purchase never takes
coins without giving the item (or vice versa), and a sale never removes an
item without paying.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from game.economy.pricing import PricePolicy
from game.economy.wallet import Wallet
from game.entities.player import Player
from game.items.actions import give_item
from game.items.definitions import ItemCategory, ItemDefinition


class ServiceType(str, Enum):
    """Services an NPC offers. Upgrading/repair/crafting are deliberately
    absent: their rules are not designed yet (extension point)."""

    SHOP = "shop"
    INSPECT = "inspect"


@dataclass(frozen=True)
class StockEntry:
    item_id: str
    quantity: Optional[int] = None  # None = unlimited

    def __post_init__(self) -> None:
        if self.quantity is not None and (isinstance(self.quantity, bool) or self.quantity < 1):
            raise ValueError("limited stock must start at >= 1")


@dataclass(frozen=True)
class MerchantDefinition:
    merchant_id: str
    name: str
    npc_id: str
    stock: Tuple[StockEntry, ...]
    pricing: PricePolicy = PricePolicy()
    buys: Tuple[ItemCategory, ...] = (
        ItemCategory.WEAPON, ItemCategory.ARMOR, ItemCategory.CONSUMABLE, ItemCategory.MATERIAL, ItemCategory.MISC,
    )
    services: Tuple[ServiceType, ...] = (ServiceType.SHOP,)

    def __post_init__(self) -> None:
        ids = [s.item_id for s in self.stock]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.merchant_id}: duplicate stock entries")
        if ItemCategory.QUEST in self.buys:
            raise ValueError("merchants never buy quest items")

    def entry(self, item_id: str) -> Optional[StockEntry]:
        return next((s for s in self.stock if s.item_id == item_id), None)


@dataclass
class MerchantState:
    """Remaining limited stock (saved). Unlimited entries are not stored."""

    remaining: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def fresh(cls, definition: MerchantDefinition) -> "MerchantState":
        return cls({s.item_id: s.quantity for s in definition.stock if s.quantity is not None})

    def to_dict(self) -> Dict[str, int]:
        return dict(sorted(self.remaining.items()))

    @classmethod
    def from_dict(cls, data, definition: MerchantDefinition) -> "MerchantState":
        if not isinstance(data, dict):
            raise TypeError("merchant state must be an object")
        state = cls.fresh(definition)
        if set(data) != set(state.remaining):
            raise ValueError(f"{definition.merchant_id}: stock entries do not match the merchant")
        for item_id, quantity in data.items():
            initial = definition.entry(item_id).quantity
            if isinstance(quantity, bool) or not isinstance(quantity, int) or not 0 <= quantity <= initial:
                raise ValueError(f"{definition.merchant_id}.{item_id}: impossible stock {quantity!r}")
            state.remaining[item_id] = quantity
        return state


class TransactionStatus(str, Enum):
    OK = "ok"
    UNKNOWN_ITEM = "unknown_item"
    NOT_SOLD_HERE = "not_sold_here"
    OUT_OF_STOCK = "out_of_stock"
    INVALID_QUANTITY = "invalid_quantity"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    INVENTORY_FULL = "inventory_full"
    UNIQUE_OWNED = "unique_already_owned"
    NOT_OWNED = "not_owned"
    UNSELLABLE = "unsellable"
    NOT_BUYING = "merchant_does_not_buy_this"
    WALLET_FULL = "wallet_full"
    DEAD = "dead"
    NO_SHOP_OPEN = "no_shop_open"


@dataclass(frozen=True)
class TransactionResult:
    status: TransactionStatus
    item_id: str
    quantity: int = 0
    total: int = 0

    @property
    def ok(self) -> bool:
        return self.status is TransactionStatus.OK


@dataclass(frozen=True)
class Offer:
    item: ItemDefinition
    price: int
    available: Optional[int]  # None = unlimited


def _valid_quantity(quantity: object) -> bool:
    return isinstance(quantity, int) and not isinstance(quantity, bool) and quantity >= 1


class Merchant:
    def __init__(self, definition: MerchantDefinition, state: MerchantState,
                 lookup: Callable[[str], ItemDefinition]) -> None:
        self.definition = definition
        self.state = state
        self.lookup = lookup

    def has_service(self, service: ServiceType) -> bool:
        return service in self.definition.services

    def offers(self) -> List[Offer]:
        result = []
        for entry in self.definition.stock:
            item = self.lookup(entry.item_id)
            available = None if entry.quantity is None else self.state.remaining.get(entry.item_id, 0)
            result.append(Offer(item, self.definition.pricing.buy_price(item), available))
        return result

    def sell_price(self, item: ItemDefinition) -> int:
        if item.category not in self.definition.buys:
            return 0
        return self.definition.pricing.sell_price(item)

    # --------------------------------------------------------------- buying
    def buy(self, player: Player, wallet: Wallet, item_id: str, quantity: int = 1) -> TransactionResult:
        """The player buys from the merchant."""
        if not _valid_quantity(quantity):
            return TransactionResult(TransactionStatus.INVALID_QUANTITY, item_id)
        if not player.is_alive:
            return TransactionResult(TransactionStatus.DEAD, item_id)
        entry = self.definition.entry(item_id)
        if entry is None:
            return TransactionResult(TransactionStatus.NOT_SOLD_HERE, item_id)
        item = self.lookup(item_id)
        if entry.quantity is not None and self.state.remaining.get(item_id, 0) < quantity:
            return TransactionResult(TransactionStatus.OUT_OF_STOCK, item_id)
        total = self.definition.pricing.buy_price(item) * quantity
        if not wallet.can_afford(total):
            return TransactionResult(TransactionStatus.INSUFFICIENT_FUNDS, item_id, quantity, total)
        if item.unique and player.owned_count(item_id):
            return TransactionResult(TransactionStatus.UNIQUE_OWNED, item_id)
        if not player.inventory.can_add(item, quantity):
            return TransactionResult(TransactionStatus.INVENTORY_FULL, item_id, quantity, total)
        # All checks passed; none of these steps can fail now.
        wallet.spend(total)
        added = give_item(player, item, quantity)
        if not added.ok:  # defensive: never keep the money without the goods
            wallet.earn(total)
            return TransactionResult(TransactionStatus.INVENTORY_FULL, item_id, quantity, total)
        if entry.quantity is not None:
            self.state.remaining[item_id] -= quantity
        return TransactionResult(TransactionStatus.OK, item_id, quantity, total)

    # -------------------------------------------------------------- selling
    def sell(self, player: Player, wallet: Wallet, item_id: str, quantity: int = 1) -> TransactionResult:
        """The player sells to the merchant (only from the inventory; equipped
        gear must be unequipped first)."""
        if not _valid_quantity(quantity):
            return TransactionResult(TransactionStatus.INVALID_QUANTITY, item_id)
        if not player.is_alive:
            return TransactionResult(TransactionStatus.DEAD, item_id)
        try:
            item = self.lookup(item_id)
        except ValueError:
            return TransactionResult(TransactionStatus.UNKNOWN_ITEM, item_id)
        if player.inventory.count(item_id) < quantity:
            return TransactionResult(TransactionStatus.NOT_OWNED, item_id)
        if not item.sellable:
            return TransactionResult(TransactionStatus.UNSELLABLE, item_id)
        if item.category not in self.definition.buys:
            return TransactionResult(TransactionStatus.NOT_BUYING, item_id)
        price = self.sell_price(item)
        if price <= 0:
            return TransactionResult(TransactionStatus.UNSELLABLE, item_id)
        total = price * quantity
        if not wallet.can_earn(total):
            return TransactionResult(TransactionStatus.WALLET_FULL, item_id, quantity, total)
        player.inventory.remove(item_id, quantity)
        wallet.earn(total)
        return TransactionResult(TransactionStatus.OK, item_id, quantity, total)
