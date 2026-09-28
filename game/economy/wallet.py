"""One prototype currency ("coins"). Balances are whole, never negative."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

MAX_BALANCE = 1_000_000_000  # sanity cap; also rejects absurd save data
CURRENCY_NAME = "coins"  # PROTOTYPE / NON-CANON name


class WalletStatus(str, Enum):
    OK = "ok"
    INVALID_AMOUNT = "invalid_amount"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    OVER_LIMIT = "over_limit"


@dataclass(frozen=True)
class WalletResult:
    status: WalletStatus
    balance: int

    @property
    def ok(self) -> bool:
        return self.status is WalletStatus.OK


def _valid_amount(amount: object) -> bool:
    return isinstance(amount, int) and not isinstance(amount, bool) and amount > 0


class Wallet:
    def __init__(self, balance: int = 0) -> None:
        if isinstance(balance, bool) or not isinstance(balance, int) or not 0 <= balance <= MAX_BALANCE:
            raise ValueError(f"balance must be an integer within 0..{MAX_BALANCE}")
        self._balance = balance

    @property
    def balance(self) -> int:
        return self._balance

    def can_afford(self, amount: int) -> bool:
        return _valid_amount(amount) and amount <= self._balance

    def can_earn(self, amount: int) -> bool:
        return _valid_amount(amount) and self._balance + amount <= MAX_BALANCE

    def earn(self, amount: int) -> WalletResult:
        if not _valid_amount(amount):
            return WalletResult(WalletStatus.INVALID_AMOUNT, self._balance)
        if self._balance + amount > MAX_BALANCE:
            return WalletResult(WalletStatus.OVER_LIMIT, self._balance)
        self._balance += amount
        return WalletResult(WalletStatus.OK, self._balance)

    def spend(self, amount: int) -> WalletResult:
        if not _valid_amount(amount):
            return WalletResult(WalletStatus.INVALID_AMOUNT, self._balance)
        if amount > self._balance:
            return WalletResult(WalletStatus.INSUFFICIENT_FUNDS, self._balance)
        self._balance -= amount
        return WalletResult(WalletStatus.OK, self._balance)
