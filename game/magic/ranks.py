"""Spell ranks, ordered E < D < C < B < A < S."""

from __future__ import annotations

from enum import Enum


class SpellRank(str, Enum):
    E = "E"
    D = "D"
    C = "C"
    B = "B"
    A = "A"
    S = "S"

    @property
    def tier(self) -> int:
        """0 for E up to 5 for S."""
        return _TIERS[self]

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SpellRank):
            return NotImplemented
        return self.tier < other.tier

    def __le__(self, other: object) -> bool:
        if not isinstance(other, SpellRank):
            return NotImplemented
        return self.tier <= other.tier

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, SpellRank):
            return NotImplemented
        return self.tier > other.tier

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, SpellRank):
            return NotImplemented
        return self.tier >= other.tier


_TIERS = {SpellRank(letter): tier for tier, letter in enumerate("EDCBAS")}

# Minimum magic_power required to cast any spell of a rank. A spell can demand
# more, never less. PROTOTYPE VALUES - NON-FINAL BALANCE.
RANK_MIN_MAGIC_POWER = {
    SpellRank.E: 0.0,
    SpellRank.D: 15.0,
    SpellRank.C: 30.0,
    SpellRank.B: 50.0,
    SpellRank.A: 80.0,
    SpellRank.S: 150.0,
}
