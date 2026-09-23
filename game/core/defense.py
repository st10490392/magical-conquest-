"""Deterministic defensive actions: block, parry and dodge.

Every entity carries a ``DefensiveState``. It only holds timers and flags; it
does not know about weapons. What an entity *can* do defensively comes from
its ``GuardProfile`` (for players, derived from the equipped weapon), so the
core stays independent of the equipment package.

Nothing here is random. Whether a parry or dodge succeeds depends only on
whether the attack resolves inside the active window, which makes the rules
testable and suitable for later server-authoritative, skill-based combat.

All numbers in ``DefenseConfig`` are PROTOTYPE VALUES - NON-FINAL BALANCE.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from game.core.stats import Stats

# A block may never absorb everything; see "level never grants immunity".
MAX_BLOCK_CAPABILITY = 0.9


@dataclass(frozen=True)
class GuardProfile:
    """What the current loadout allows. ``block_capability`` is the fraction
    of incoming damage a block absorbs; 0 means blocking is impossible."""

    block_capability: float = 0.0
    can_parry: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.block_capability <= MAX_BLOCK_CAPABILITY:
            raise ValueError(f"block_capability must be within 0..{MAX_BLOCK_CAPABILITY}")

    @property
    def can_block(self) -> bool:
        return self.block_capability > 0.0


@dataclass(frozen=True)
class DefenseConfig:
    block_stamina_per_damage: float = 0.5  # stamina spent per point absorbed
    block_affects_magic: bool = True
    parry_window: float = 0.20  # seconds a parry is active
    parry_recovery: float = 0.80  # seconds before the next parry (from start)
    parry_stamina_cost: float = 12.0
    parry_damage_ratio: float = 0.0  # share of damage that still gets through
    parry_affects_magic: bool = False  # weapons parry weapons, not spells
    dodge_duration: float = 0.25  # evade window
    dodge_cooldown: float = 0.90  # from dodge start; must exceed duration
    dodge_stamina_cost: float = 20.0

    def __post_init__(self) -> None:
        if self.dodge_cooldown <= self.dodge_duration:
            raise ValueError("dodge_cooldown must be longer than dodge_duration")
        if self.parry_recovery <= self.parry_window:
            raise ValueError("parry_recovery must be longer than parry_window")
        if not 0.0 <= self.parry_damage_ratio <= 1.0:
            raise ValueError("parry_damage_ratio must be within 0..1")


DEFAULT_DEFENSE = DefenseConfig()


class DefenseAction(str, Enum):
    STARTED = "started"
    DEAD = "dead"
    NOT_CAPABLE = "not_capable"  # loadout cannot block/parry
    NOT_ENOUGH_STAMINA = "not_enough_stamina"
    ON_COOLDOWN = "on_cooldown"


class DefensiveState:
    def __init__(self, config: DefenseConfig = DEFAULT_DEFENSE) -> None:
        self.config = config
        self.blocking = False
        self.parry_remaining = 0.0
        self.parry_cooldown = 0.0
        self.dodge_remaining = 0.0
        self.dodge_cooldown = 0.0

    @property
    def is_parrying(self) -> bool:
        return self.parry_remaining > 0.0

    @property
    def is_dodging(self) -> bool:
        return self.dodge_remaining > 0.0

    def tick(self, dt: float) -> None:
        self.parry_remaining = max(0.0, self.parry_remaining - dt)
        self.parry_cooldown = max(0.0, self.parry_cooldown - dt)
        self.dodge_remaining = max(0.0, self.dodge_remaining - dt)
        self.dodge_cooldown = max(0.0, self.dodge_cooldown - dt)

    def reset(self) -> None:
        self.blocking = False
        self.parry_remaining = self.parry_cooldown = 0.0
        self.dodge_remaining = self.dodge_cooldown = 0.0

    # ------------------------------------------------------------ actions
    def start_block(self, stats: Stats, guard: GuardProfile) -> DefenseAction:
        if not stats.is_alive:
            return DefenseAction.DEAD
        if not guard.can_block:
            return DefenseAction.NOT_CAPABLE
        if stats.stamina <= 0:
            return DefenseAction.NOT_ENOUGH_STAMINA
        self.blocking = True
        return DefenseAction.STARTED

    def stop_block(self) -> None:
        self.blocking = False

    def start_parry(self, stats: Stats, guard: GuardProfile) -> DefenseAction:
        if not stats.is_alive:
            return DefenseAction.DEAD
        if not guard.can_parry:
            return DefenseAction.NOT_CAPABLE
        if self.parry_cooldown > 0:
            return DefenseAction.ON_COOLDOWN
        if not stats.consume_stamina(self.config.parry_stamina_cost):
            return DefenseAction.NOT_ENOUGH_STAMINA
        self.parry_remaining = self.config.parry_window
        self.parry_cooldown = self.config.parry_recovery
        return DefenseAction.STARTED

    def start_dodge(self, stats: Stats) -> DefenseAction:
        if not stats.is_alive:
            return DefenseAction.DEAD
        if self.dodge_cooldown > 0:
            return DefenseAction.ON_COOLDOWN
        if not stats.consume_stamina(self.config.dodge_stamina_cost):
            return DefenseAction.NOT_ENOUGH_STAMINA
        self.blocking = False  # dodging drops the guard
        self.dodge_remaining = self.config.dodge_duration
        self.dodge_cooldown = self.config.dodge_cooldown
        return DefenseAction.STARTED
