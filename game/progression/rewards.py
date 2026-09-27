"""Rewards and the ledger that makes each reward claimable exactly once.

A reward is granted atomically: if the items do not all fit, nothing is
granted (no XP, no items) and the claim is not recorded, so the player can
make room and try again. Claim keys are stable strings such as
``"quest:proto_clear_camp"``; the ledger is saved with the game.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Optional, Protocol, Set, Tuple

from game.entities.player import Player
from game.items.definitions import ItemDefinition


@dataclass(frozen=True)
class Reward:
    """PROTOTYPE amounts - NON-FINAL."""

    xp: int = 0
    currency: int = 0
    items: Tuple[Tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if self.xp < 0 or self.currency < 0 or any(q < 1 for _, q in self.items):
            raise ValueError("reward amounts must be non-negative and item quantities >= 1")

    @property
    def empty(self) -> bool:
        return not (self.xp or self.currency or self.items)


class CurrencyAccount(Protocol):
    def earn(self, amount: int): ...


class RewardLedger:
    def __init__(self, claimed: Iterable[str] = ()) -> None:
        self._claimed: Set[str] = set(claimed)

    def is_claimed(self, key: str) -> bool:
        return key in self._claimed

    def _record(self, key: str) -> None:
        self._claimed.add(key)

    @property
    def claimed(self) -> Tuple[str, ...]:
        return tuple(sorted(self._claimed))

    def to_list(self) -> list:
        return list(self.claimed)

    @classmethod
    def from_list(cls, data) -> "RewardLedger":
        if not isinstance(data, list) or not all(isinstance(k, str) and k for k in data):
            raise TypeError("reward ledger must be a list of non-empty strings")
        if len(set(data)) != len(data):
            raise ValueError("reward ledger contains duplicates")
        return cls(data)


class GrantStatus(str, Enum):
    OK = "ok"
    ALREADY_CLAIMED = "already_claimed"
    INVENTORY_FULL = "inventory_full"
    DEAD = "dead"


@dataclass(frozen=True)
class RewardGrant:
    status: GrantStatus
    reward: Optional[Reward] = None
    levels_gained: int = 0

    @property
    def ok(self) -> bool:
        return self.status is GrantStatus.OK


def grant_reward(
    player: Player,
    reward: Reward,
    key: str,
    ledger: RewardLedger,
    lookup: Callable[[str], ItemDefinition],
    wallet: Optional[CurrencyAccount] = None,
    on_item: Optional[Callable[[str, int], None]] = None,
) -> RewardGrant:
    """Grant ``reward`` once under ``key``; all-or-nothing."""
    if ledger.is_claimed(key):
        return RewardGrant(GrantStatus.ALREADY_CLAIMED, reward)
    if not player.is_alive:
        return RewardGrant(GrantStatus.DEAD, reward)
    if reward.currency and wallet is None:
        raise ValueError("this reward pays currency but no wallet was provided")
    items = [(lookup(item_id), quantity) for item_id, quantity in reward.items]
    if not player.inventory.can_add_all(items) or any(i.unique and player.owned_count(i.item_id) for i, _ in items):
        return RewardGrant(GrantStatus.INVENTORY_FULL, reward)
    ledger._record(key)
    for item, quantity in items:
        player.inventory.add(item, quantity)
        if on_item:
            on_item(item.item_id, quantity)
    if reward.currency:
        wallet.earn(reward.currency)
    levels = player.gain_xp(reward.xp).levels_gained if reward.xp else 0
    return RewardGrant(GrantStatus.OK, reward, levels)
