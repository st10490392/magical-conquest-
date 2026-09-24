"""Enemy attack definitions and the telegraph -> active -> recovery lifecycle.

Damage always goes through ``game.core.combat``; this module only decides
*when* an attack resolves.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from game.core.combat import Attack


@dataclass(frozen=True)
class EnemyAttack:
    """How an enemy uses a combat ``Attack``. PROTOTYPE VALUES - NON-FINAL.

    ``telegraph``: wind-up seconds before the attack resolves.
    ``recovery``: seconds the enemy is committed afterwards (punish window).
    ``projectile_speed``: ``None`` for melee (resolves instantly at the end of
    the telegraph, range-checked); otherwise a projectile is launched.
    ``trigger_range``: start the wind-up when the target is this close
    (defaults to the attack's reach).
    """

    attack: Attack
    telegraph: float = 0.4
    recovery: float = 0.4
    projectile_speed: Optional[float] = None
    trigger_range: Optional[float] = None

    def __post_init__(self) -> None:
        if self.telegraph < 0 or self.recovery < 0:
            raise ValueError("telegraph and recovery must not be negative")
        if self.projectile_speed is not None and self.projectile_speed <= 0:
            raise ValueError("projectile_speed must be positive")

    @property
    def is_melee(self) -> bool:
        return self.projectile_speed is None

    @property
    def start_range(self) -> float:
        return self.trigger_range if self.trigger_range is not None else self.attack.reach


class AttackPhase(str, Enum):
    NONE = "none"
    TELEGRAPH = "telegraph"
    RECOVERY = "recovery"


class AttackLifecycle:
    """Timers for one attack at a time. The ACTIVE moment is the tick on which
    the telegraph runs out; ``tick`` reports it by returning True."""

    def __init__(self) -> None:
        self.phase = AttackPhase.NONE
        self.remaining = 0.0
        self.current: Optional[EnemyAttack] = None

    @property
    def busy(self) -> bool:
        return self.phase is not AttackPhase.NONE

    def start(self, attack: EnemyAttack) -> None:
        self.current = attack
        self.phase = AttackPhase.TELEGRAPH
        self.remaining = attack.telegraph

    def tick_telegraph(self, dt: float) -> bool:
        """Advance the wind-up; True when the attack should resolve now."""
        self.remaining -= dt
        return self.remaining <= 1e-9

    def begin_recovery(self, extra: float = 0.0) -> None:
        self.phase = AttackPhase.RECOVERY
        self.remaining = self.current.recovery + extra if self.current else extra

    def tick_recovery(self, dt: float) -> bool:
        """Advance recovery; True when the enemy is free to act again."""
        self.remaining -= dt
        if self.remaining <= 1e-9:
            self.cancel()
            return True
        return False

    def cancel(self) -> None:
        self.phase = AttackPhase.NONE
        self.remaining = 0.0
        self.current = None
