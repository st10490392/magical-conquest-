"""A simple melee enemy that chases and attacks a target.

The AI works in abstract world units; the Pygame layer only draws the result.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from game.core.combat import Attack, AttackResult, Cooldown, DamageType, attack_interval, resolve_attack, try_attack
from game.core.entity import Entity
from game.core.stats import Stats
from game.core.vector import Vec2
from game.progression.growth import StatGrowth

GOBLIN_CLAW = Attack(
    name="claw",
    damage_type=DamageType.PHYSICAL,
    base_power=5.0,
    scaling=0.8,
    reach=50.0,
    cooldown=1.0,
)

# Telegraph before each claw so parry/dodge timing can be learned.
# PROTOTYPE VALUE - NON-FINAL.
GOBLIN_WINDUP = 0.35

GOBLIN_GROWTH = StatGrowth(
    max_health=10.0,
    max_mana=0.0,
    max_stamina=0.0,
    physical_strength=1.5,
    magic_power=0.0,
    durability=1.0,
    magic_resistance=1.0,
    agility=0.5,
)


class EnemyState(str, Enum):
    IDLE = "idle"
    CHASING = "chasing"
    WINDUP = "windup"  # telegraphing an attack; the moment to parry/dodge
    ATTACKING = "attacking"
    DEAD = "dead"


class Enemy(Entity):
    def __init__(
        self,
        name: str,
        stats: Stats,
        attack: Attack,
        level: int = 1,
        aggro_range: float = 400.0,
        xp_reward: int = 50,
        entity_id: Optional[str] = None,
        position: Optional[Vec2] = None,
        windup: float = 0.0,
    ) -> None:
        super().__init__(name, stats, level=level, entity_id=entity_id, position=position)
        if windup < 0:
            raise ValueError("windup must not be negative")
        self.attack = attack
        self.windup = windup
        self.windup_remaining = 0.0
        self.aggro_range = aggro_range
        self.xp_reward = xp_reward
        self.state = EnemyState.IDLE
        self.attack_cooldown = Cooldown()

    def update(self, dt: float, target: Optional[Entity], world_time: Optional[float] = None) -> Optional[AttackResult]:
        """Advance AI by ``dt`` seconds. Returns an attack result if it swung.

        With a ``windup``, the enemy telegraphs for that long, then strikes
        whether or not the target is still in reach (a whiff still costs it
        its cooldown).
        """
        self.attack_cooldown.tick(dt)
        self.defense.tick(dt)
        if not self.is_alive:
            self.state = EnemyState.DEAD
            self.windup_remaining = 0.0
            return None
        if target is None or not target.is_alive:
            self.state = EnemyState.IDLE
            self.windup_remaining = 0.0
            return None

        if self.windup_remaining > 0:
            self.windup_remaining -= dt
            if self.windup_remaining > 0:
                return None
            self.windup_remaining = 0.0
            self.state = EnemyState.ATTACKING
            self.attack_cooldown.start(attack_interval(self.attack, self.stats.agility))
            return resolve_attack(self, target, self.attack, world_time=world_time)

        distance = self.distance_to(target)
        if distance <= self.attack.reach:
            self.state = EnemyState.ATTACKING
            if self.attack_cooldown.ready:
                if self.windup > 0:
                    self.state = EnemyState.WINDUP
                    self.windup_remaining = self.windup
                    return None
                return try_attack(self, target, self.attack, self.attack_cooldown, world_time)
            return None
        if distance <= self.aggro_range:
            self.state = EnemyState.CHASING
            # Stop just inside reach instead of overlapping the target.
            step = min(self.stats.speed * dt, distance - self.attack.reach * 0.9)
            direction = (target.position - self.position).normalized()
            self.position = self.position + direction * max(0.0, step)
            return None
        self.state = EnemyState.IDLE
        return None


def create_goblin(level: int = 1, position: Optional[Vec2] = None) -> Enemy:
    """The single MC-001 test enemy, scaled by level through stat growth."""
    stats = Stats(
        max_health=60.0,
        max_mana=0.0,
        max_stamina=0.0,
        physical_strength=6.0,
        magic_power=0.0,
        magic_resistance=0.0,
        durability=2.0,
        speed=130.0,
        agility=0.0,
    )
    GOBLIN_GROWTH.apply(stats, level - 1)
    return Enemy(
        "Goblin",
        stats,
        GOBLIN_CLAW,
        level=level,
        aggro_range=500.0,
        windup=GOBLIN_WINDUP,
        xp_reward=40 + 15 * (level - 1),
        position=position,
    )
