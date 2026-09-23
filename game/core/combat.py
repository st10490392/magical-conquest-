"""Deterministic combat rules, shared by PvE and PvP.

Damage flow::

    raw = attack.base_power + attacker attribute * attack.scaling
    mitigated = raw * DEFENSE_CONSTANT / (DEFENSE_CONSTANT + defense)
    final = max(mitigated, raw * MIN_DAMAGE_RATIO, MIN_DAMAGE)   (if raw > 0)

``defense`` is ``durability`` for physical attacks and ``magic_resistance``
for magic attacks. Mitigation approaches but never reaches 100 %, and there
is a hard floor, so any valid hit always deals damage.

Level is deliberately **not** an input. Higher-level characters are tougher
only through the stats they have gained (bigger health pools, more
durability/resistance), so a lower-level attacker can always finish a
higher-level target given enough hits.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from game.core.entity import DeathRecord, Entity

DEFENSE_CONSTANT = 100.0
MIN_DAMAGE_RATIO = 0.10
MIN_DAMAGE = 1.0


class DamageType(str, Enum):
    PHYSICAL = "physical"
    MAGIC = "magic"


@dataclass(frozen=True)
class Attack:
    """A usable attack definition. Data only; no state."""

    name: str
    damage_type: DamageType
    base_power: float
    scaling: float = 1.0
    reach: float = 60.0
    cooldown: float = 0.5
    stamina_cost: float = 0.0
    mana_cost: float = 0.0


class AttackOutcome(str, Enum):
    HIT = "hit"
    ON_COOLDOWN = "on_cooldown"
    ATTACKER_DEAD = "attacker_dead"
    TARGET_DEAD = "target_dead"
    OUT_OF_RANGE = "out_of_range"
    NOT_ENOUGH_STAMINA = "not_enough_stamina"
    NOT_ENOUGH_MANA = "not_enough_mana"


@dataclass(frozen=True)
class AttackResult:
    outcome: AttackOutcome
    damage: float = 0.0
    killed: bool = False
    death: Optional[DeathRecord] = None

    @property
    def landed(self) -> bool:
        return self.outcome is AttackOutcome.HIT


def raw_damage(attacker: Entity, attack: Attack) -> float:
    if attack.damage_type is DamageType.PHYSICAL:
        attribute = attacker.stats.physical_strength
    else:
        attribute = attacker.stats.magic_power
    return max(0.0, attack.base_power + attribute * attack.scaling)


def defense_for(defender: Entity, damage_type: DamageType) -> float:
    if damage_type is DamageType.PHYSICAL:
        return defender.stats.durability
    return defender.stats.magic_resistance


def mitigate(raw: float, defense: float) -> float:
    """Apply defense to raw damage. Never returns 0 for positive ``raw``."""
    if raw <= 0:
        return 0.0
    defense = max(0.0, defense)
    mitigated = raw * DEFENSE_CONSTANT / (DEFENSE_CONSTANT + defense)
    return max(mitigated, raw * MIN_DAMAGE_RATIO, MIN_DAMAGE)


def calculate_damage(attacker: Entity, defender: Entity, attack: Attack) -> float:
    """Pure damage calculation; does not mutate anything."""
    return mitigate(raw_damage(attacker, attack), defense_for(defender, attack.damage_type))


def resolve_attack(
    attacker: Entity,
    defender: Entity,
    attack: Attack,
    check_range: bool = True,
    world_time: Optional[float] = None,
) -> AttackResult:
    """Validate, pay costs, compute and apply one attack.

    Resources are only spent when the attack actually lands.
    """
    if not attacker.is_alive:
        return AttackResult(AttackOutcome.ATTACKER_DEAD)
    if not defender.is_alive:
        return AttackResult(AttackOutcome.TARGET_DEAD)
    if check_range and attacker.distance_to(defender) > attack.reach:
        return AttackResult(AttackOutcome.OUT_OF_RANGE)
    if attacker.stats.stamina < attack.stamina_cost:
        return AttackResult(AttackOutcome.NOT_ENOUGH_STAMINA)
    if attacker.stats.mana < attack.mana_cost:
        return AttackResult(AttackOutcome.NOT_ENOUGH_MANA)

    attacker.stats.consume_stamina(attack.stamina_cost)
    attacker.stats.consume_mana(attack.mana_cost)
    damage = calculate_damage(attacker, defender, attack)
    applied = defender.receive_damage(
        damage,
        source_id=attacker.entity_id,
        cause=f"{attack.damage_type.value}:{attack.name}",
        world_time=world_time,
    )
    killed = not defender.is_alive
    return AttackResult(AttackOutcome.HIT, applied, killed, defender.death if killed else None)


def attack_interval(attack: Attack, agility: float) -> float:
    """Cooldown after ``attack``; agility shortens it with diminishing returns."""
    return attack.cooldown / (1.0 + max(0.0, agility) / 100.0)


def try_attack(
    attacker: Entity,
    defender: Entity,
    attack: Attack,
    cooldown: "Cooldown",
    world_time: Optional[float] = None,
) -> AttackResult:
    """``resolve_attack`` gated by a cooldown, which restarts on a hit."""
    if not cooldown.ready:
        return AttackResult(AttackOutcome.ON_COOLDOWN)
    result = resolve_attack(attacker, defender, attack, world_time=world_time)
    if result.landed:
        cooldown.start(attack_interval(attack, attacker.stats.agility))
    return result


class Cooldown:
    """Simple countdown timer driven by simulation ``dt``."""

    def __init__(self) -> None:
        self.remaining = 0.0

    @property
    def ready(self) -> bool:
        return self.remaining <= 0.0

    def start(self, seconds: float) -> None:
        self.remaining = max(0.0, seconds)

    def tick(self, dt: float) -> None:
        if self.remaining > 0.0:
            self.remaining = max(0.0, self.remaining - dt)
