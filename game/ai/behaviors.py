"""Per-archetype decision making.

A ``Behavior`` only answers "what do I want to do this tick?" by returning a
``Decision``. The shared lifecycle (alert delay, telegraph -> active ->
recovery, stagger, cooldowns, attack tokens, death) lives in ``Enemy``, so
new enemy types (knights, werewolves, bosses...) add a behaviour instead of
growing one giant update function.

Everything here is deterministic: no randomness.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from game.ai.perception import Percept
from game.ai.space import CombatSpace
from game.ai.states import AIState
from game.core.vector import Vec2

if TYPE_CHECKING:
    from game.entities.enemy import Enemy


@dataclass(frozen=True)
class Decision:
    state: AIState
    direction: Vec2 = Vec2()
    speed_scale: float = 1.0
    max_step: float = math.inf  # never move further than this this tick
    attack: bool = False  # wants to start its attack (if cooldown/token allow)


IDLE = Decision(AIState.IDLE)


def toward(enemy: "Enemy", point: Vec2) -> Vec2:
    return (point - enemy.position).normalized()


class Behavior:
    """Base behaviour: stands still. Subclasses override the hooks they need."""

    def decide(self, enemy: "Enemy", percept: Percept, space: Optional[CombatSpace]) -> Decision:
        return IDLE

    def on_telegraph_start(self, enemy: "Enemy", percept: Percept) -> None:
        """Called once when a wind-up begins."""

    def telegraph_motion(self, enemy: "Enemy", percept: Percept) -> Optional[Decision]:
        """Movement allowed during the wind-up. Default: rooted."""
        return None

    def before_strike(self, enemy: "Enemy", percept: Percept) -> None:
        """Called on the active tick, just before the attack resolves."""


class MeleeBehavior(Behavior):
    """Striker: closes distance, strikes at close range, keeps pressure by
    tracking the target slightly during its wind-up."""

    def __init__(self, telegraph_tracking: float = 0.0, spacing: float = 0.85) -> None:
        self.telegraph_tracking = telegraph_tracking  # share of speed while winding up
        self.spacing = spacing  # stop at this share of attack range

    def decide(self, enemy: "Enemy", percept: Percept, space: Optional[CombatSpace]) -> Decision:
        start_range = enemy.attack_profile.start_range
        if percept.distance <= start_range:
            if enemy.attack_cooldown.ready:
                return Decision(AIState.POSITION, attack=True)
            return Decision(AIState.POSITION)  # hold ground until ready
        return Decision(
            AIState.APPROACH,
            toward(enemy, percept.target.position),
            max_step=percept.distance - start_range * self.spacing,
        )

    def telegraph_motion(self, enemy: "Enemy", percept: Percept) -> Optional[Decision]:
        reach = enemy.attack.reach
        if self.telegraph_tracking <= 0 or percept.distance <= reach * 0.8:
            return None
        return Decision(
            AIState.TELEGRAPH,
            toward(enemy, percept.target.position),
            speed_scale=self.telegraph_tracking,
            max_step=percept.distance - reach * 0.8,
        )


class HeavyBehavior(MeleeBehavior):
    """Brute: slow, commits fully. At wind-up start it locks an aim point
    (where the target stood) and does not track; on release it lunges toward
    that point and slams. Stepping away from the aim point avoids the hit,
    and the long recovery afterwards is the punish window."""

    def __init__(self, lunge_distance: float = 45.0) -> None:
        super().__init__(telegraph_tracking=0.0, spacing=0.9)
        self.lunge_distance = lunge_distance

    def on_telegraph_start(self, enemy: "Enemy", percept: Percept) -> None:
        enemy.aim_point = percept.target.position

    def before_strike(self, enemy: "Enemy", percept: Percept) -> None:
        aim = enemy.aim_point
        if aim is None:
            return
        distance = enemy.position.distance_to(aim)
        step = min(self.lunge_distance, max(0.0, distance - enemy.size / 2))
        enemy.position = enemy.position + toward(enemy, aim) * step


class RangedBehavior(Behavior):
    """Archer: keeps a preferred distance band, backs off when the target gets
    close (sliding along arena walls), and only shoots from inside its band."""

    def __init__(self, min_range: float = 170.0, max_range: float = 320.0) -> None:
        if not 0 < min_range < max_range:
            raise ValueError("need 0 < min_range < max_range")
        self.min_range = min_range
        self.max_range = max_range

    def decide(self, enemy: "Enemy", percept: Percept, space: Optional[CombatSpace]) -> Decision:
        distance = percept.distance
        target = percept.target.position
        if distance < self.min_range:
            away = (enemy.position - target).normalized()
            if away.length() == 0:
                away = Vec2(1.0, 0.0)
            direction = self._escape_direction(enemy, away, space)
            return Decision(AIState.RETREAT, direction, max_step=self.min_range - distance)
        if distance > self.max_range:
            return Decision(AIState.APPROACH, toward(enemy, target), max_step=distance - self.max_range * 0.95)
        if enemy.attack_cooldown.ready and distance <= enemy.attack_profile.start_range:
            return Decision(AIState.POSITION, attack=True)
        return Decision(AIState.POSITION)

    @staticmethod
    def _escape_direction(enemy: "Enemy", away: Vec2, space: Optional[CombatSpace]) -> Vec2:
        """Move away from the target; slide along walls; strafe if cornered."""
        if space is None or space.bounds is None:
            return away
        probe = enemy.size
        x, y = away.x, away.y
        if not space.contains(Vec2(enemy.position.x + x * probe, enemy.position.y), enemy.size / 2):
            x = 0.0
        if not space.contains(Vec2(enemy.position.x, enemy.position.y + y * probe), enemy.size / 2):
            y = 0.0
        slide = Vec2(x, y).normalized()
        if slide.length():
            return slide
        for strafe in (Vec2(-away.y, away.x), Vec2(away.y, -away.x)):
            if space.contains(enemy.position + strafe * probe, enemy.size / 2):
                return strafe
        return away
