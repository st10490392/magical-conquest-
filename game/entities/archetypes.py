"""Prototype enemy archetypes: data + a behaviour, built into ``Enemy``s.

These are mechanical test subjects, not Magical Conquest species or lore.
Each one asks the player a different question:

* Striker (melee): can you read and answer close-range pressure?
* Archer (ranged): can you close the gap or avoid ranged pressure?
* Brute (heavy): can you spot a committed attack and punish its recovery?

ALL NUMBERS ARE PROTOTYPE VALUES - NON-FINAL BALANCE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Optional

from game.ai.attacks import EnemyAttack
from game.ai.behaviors import Behavior, HeavyBehavior, MeleeBehavior, RangedBehavior
from game.ai.perception import PerceptionConfig
from game.core.combat import Attack, DamageType
from game.core.stats import Stats
from game.core.vector import Vec2
from game.entities.enemy import Enemy, create_goblin
from game.progression.growth import StatGrowth


class ArchetypeKind(str, Enum):
    MELEE = "melee"
    RANGED = "ranged"
    HEAVY = "heavy"


@dataclass(frozen=True)
class EnemyArchetype:
    archetype_id: str
    name: str
    kind: ArchetypeKind
    stats: Dict[str, float]
    attack: EnemyAttack
    behavior: Callable[[], Behavior]  # a fresh behaviour per enemy
    perception: PerceptionConfig
    alert_time: float = 0.25
    parry_stagger: float = 0.0
    size: float = 40.0
    xp_reward: int = 50
    xp_per_level: int = 15
    growth: StatGrowth = field(default_factory=lambda: StatGrowth(
        max_health=10.0, max_mana=0.0, max_stamina=0.0, physical_strength=1.5,
        magic_power=0.0, durability=1.0, magic_resistance=1.0, agility=0.5,
    ))

    def create(self, level: int = 1, position: Optional[Vec2] = None) -> Enemy:
        stats = Stats(max_mana=0.0, max_stamina=0.0, magic_power=0.0, **self.stats)
        self.growth.apply(stats, level - 1)
        return Enemy(
            self.name,
            stats,
            self.attack,
            level=level,
            xp_reward=self.xp_reward + self.xp_per_level * (level - 1),
            position=position,
            behavior=self.behavior(),
            perception=self.perception,
            alert_time=self.alert_time,
            parry_stagger=self.parry_stagger,
            archetype=self.archetype_id,
            size=self.size,
        )


STRIKER = EnemyArchetype(
    archetype_id="striker",
    name="Striker",
    kind=ArchetypeKind.MELEE,
    stats=dict(max_health=70.0, physical_strength=8.0, durability=3.0, magic_resistance=2.0, speed=150.0),
    attack=EnemyAttack(
        Attack("strike", DamageType.PHYSICAL, base_power=6.0, scaling=0.9, reach=55.0, cooldown=1.1),
        telegraph=0.45,
        recovery=0.5,
    ),
    # Tracks at 35% speed while winding up: backing off slowly is not enough.
    behavior=lambda: MeleeBehavior(telegraph_tracking=0.35),
    perception=PerceptionConfig(detection_range=420.0, disengage_range=650.0),
    alert_time=0.25,
    parry_stagger=1.2,
    xp_reward=45,
)

ARCHER = EnemyArchetype(
    archetype_id="archer",
    name="Archer",
    kind=ArchetypeKind.RANGED,
    stats=dict(max_health=45.0, physical_strength=7.0, durability=1.0, magic_resistance=4.0, speed=140.0),
    attack=EnemyAttack(
        Attack("arrow", DamageType.PHYSICAL, base_power=7.0, scaling=0.8, reach=360.0, cooldown=1.8),
        telegraph=0.7,
        recovery=0.35,
        projectile_speed=380.0,
    ),
    behavior=lambda: RangedBehavior(min_range=170.0, max_range=320.0),
    perception=PerceptionConfig(detection_range=480.0, disengage_range=700.0),
    alert_time=0.25,
    parry_stagger=0.0,  # arrows can be parried, but the archer is not staggered
    xp_reward=50,
)

BRUTE = EnemyArchetype(
    archetype_id="brute",
    name="Brute",
    kind=ArchetypeKind.HEAVY,
    stats=dict(max_health=260.0, physical_strength=14.0, durability=20.0, magic_resistance=6.0, speed=85.0),
    attack=EnemyAttack(
        Attack("slam", DamageType.PHYSICAL, base_power=18.0, scaling=1.4, reach=80.0, cooldown=2.2),
        telegraph=1.1,
        recovery=1.3,
        trigger_range=110.0,  # starts the slam from further out and lunges in
    ),
    behavior=lambda: HeavyBehavior(lunge_distance=45.0),
    perception=PerceptionConfig(detection_range=380.0, disengage_range=600.0),
    alert_time=0.4,
    parry_stagger=1.8,
    size=56.0,
    xp_reward=80,
    xp_per_level=25,
    growth=StatGrowth(
        max_health=22.0, max_mana=0.0, max_stamina=0.0, physical_strength=2.0,
        magic_power=0.0, durability=2.0, magic_resistance=1.0, agility=0.0,
    ),
)

ARCHETYPES: Dict[str, EnemyArchetype] = {a.archetype_id: a for a in (STRIKER, ARCHER, BRUTE)}


def create_enemy(archetype_id: str, level: int = 1, position: Optional[Vec2] = None) -> Enemy:
    """Build an enemy from an archetype id (``goblin`` is the MC-001/002 enemy)."""
    if archetype_id == "goblin":
        return create_goblin(level, position)
    try:
        archetype = ARCHETYPES[archetype_id]
    except KeyError:
        raise ValueError(f"unknown enemy archetype {archetype_id!r}") from None
    return archetype.create(level, position)
