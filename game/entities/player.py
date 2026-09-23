"""Player character built on the shared Entity foundation."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from game.core.combat import Attack, AttackResult, Cooldown, DamageType, try_attack
from game.core.entity import Entity
from game.core.stats import Stats
from game.core.vector import Vec2
from game.progression.experience import Experience, LevelUpResult, ProgressionCurve
from game.progression.growth import StatGrowth

MELEE_STRIKE = Attack(
    name="melee_strike",
    damage_type=DamageType.PHYSICAL,
    base_power=8.0,
    scaling=1.0,
    reach=70.0,
    cooldown=0.4,
    stamina_cost=8.0,
)

FIRE_BOLT = Attack(
    name="fire_bolt",
    damage_type=DamageType.MAGIC,
    base_power=10.0,
    scaling=1.2,
    reach=260.0,
    cooldown=0.9,
    mana_cost=12.0,
)


class MovementState(str, Enum):
    IDLE = "idle"
    MOVING = "moving"
    DEAD = "dead"


def default_player_stats() -> Stats:
    return Stats(
        max_health=120.0,
        max_mana=60.0,
        max_stamina=100.0,
        physical_strength=10.0,
        magic_power=10.0,
        magic_resistance=5.0,
        durability=5.0,
        speed=220.0,
        agility=10.0,
    )


class Player(Entity):
    def __init__(
        self,
        name: str,
        stats: Optional[Stats] = None,
        level: int = 1,
        xp: int = 0,
        entity_id: Optional[str] = None,
        position: Optional[Vec2] = None,
        curve: Optional[ProgressionCurve] = None,
        growth: Optional[StatGrowth] = None,
    ) -> None:
        super().__init__(
            name,
            stats if stats is not None else default_player_stats(),
            level=level,
            entity_id=entity_id,
            position=position,
        )
        self.experience = Experience(xp, curve)
        self.growth = growth or StatGrowth()
        self.movement_state = MovementState.IDLE
        self.facing = Vec2(1.0, 0.0)
        self.attack_cooldown = Cooldown()

    @property
    def xp(self) -> int:
        return self.experience.xp

    @property
    def xp_to_next(self) -> int:
        return self.experience.curve.xp_to_next(self.level)

    def move(self, direction: Vec2, dt: float) -> None:
        """Move along ``direction`` (any length) at the ``speed`` stat."""
        if not self.is_alive:
            self.movement_state = MovementState.DEAD
            return
        step = direction.normalized()
        if step.length() == 0:
            self.movement_state = MovementState.IDLE
            return
        self.facing = step
        self.position = self.position + step * (self.stats.speed * dt)
        self.movement_state = MovementState.MOVING

    def update(self, dt: float) -> None:
        self.attack_cooldown.tick(dt)
        if not self.is_alive:
            self.movement_state = MovementState.DEAD

    def attack(self, target: Entity, attack: Attack = MELEE_STRIKE, world_time: Optional[float] = None) -> AttackResult:
        return try_attack(self, target, attack, self.attack_cooldown, world_time)

    def gain_xp(self, amount: int) -> LevelUpResult:
        """Add XP; each level gained applies ``growth`` and refills pools."""
        result = self.experience.add(self.level, amount)
        if result.levels_gained and self.is_alive:
            self.growth.apply(self.stats, result.levels_gained)
        self.level = result.new_level
        return result
