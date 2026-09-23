"""Deterministic combat rules, shared by PvE and PvP.

Damage flow::

    raw = attack.base_power + attacker attribute * attack.scaling
    mitigated = raw * DEFENSE_CONSTANT / (DEFENSE_CONSTANT + defense)
    final = max(mitigated, raw * MIN_DAMAGE_RATIO, MIN_DAMAGE)   (if raw > 0)

``defense`` is ``durability`` for physical attacks and ``magic_resistance``
for magic attacks. Mitigation approaches but never reaches 100 %, and there
is a hard floor, so any valid hit always deals damage.

Before damage is applied, the defender's active defense is checked in the
order dodge -> parry -> block (see ``apply_defense`` and ``core.defense``).
None of them is random, and a block can never absorb everything.

Level is deliberately **not** an input. Higher-level characters are tougher
only through the stats they have gained (bigger health pools, more
durability/resistance), so a lower-level attacker can always finish a
higher-level target given enough hits.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple

from game.core.entity import DeathContext, DeathRecord, Entity

if TYPE_CHECKING:
    from game.magic.attributes import MagicAttribute

DEFENSE_CONSTANT = 100.0
MIN_DAMAGE_RATIO = 0.10
MIN_DAMAGE = 1.0


class DamageType(str, Enum):
    PHYSICAL = "physical"
    MAGIC = "magic"


@dataclass(frozen=True)
class Attack:
    """A usable attack definition. Data only; no state.

    ``element`` is informational for combat (it is reported in results and
    death causes); spells use it for their attribute requirement.
    """

    name: str
    damage_type: DamageType
    base_power: float
    scaling: float = 1.0
    reach: float = 60.0
    cooldown: float = 0.5
    stamina_cost: float = 0.0
    mana_cost: float = 0.0
    element: Optional["MagicAttribute"] = None


class AttackOutcome(str, Enum):
    HIT = "hit"
    BLOCKED = "blocked"  # reduced damage got through
    PARRIED = "parried"
    DODGED = "dodged"
    ON_COOLDOWN = "on_cooldown"
    ATTACKER_DEAD = "attacker_dead"
    TARGET_DEAD = "target_dead"
    OUT_OF_RANGE = "out_of_range"
    NOT_ENOUGH_STAMINA = "not_enough_stamina"
    NOT_ENOUGH_MANA = "not_enough_mana"
    # Spell requirement failures (checked before range and resources).
    NO_SPELL_SELECTED = "no_spell_selected"
    SPELL_NOT_KNOWN = "spell_not_known"
    MISSING_ATTRIBUTE = "missing_attribute"
    INSUFFICIENT_LEVEL = "insufficient_level"
    INSUFFICIENT_MAGIC_POWER = "insufficient_magic_power"


@dataclass(frozen=True)
class AttackResult:
    outcome: AttackOutcome
    damage: float = 0.0
    killed: bool = False
    death: Optional[DeathRecord] = None
    element: Optional["MagicAttribute"] = None
    absorbed: float = 0.0  # damage stopped by a block or parry
    guard_broken: bool = False  # the block ran out of stamina

    @property
    def landed(self) -> bool:
        """Damage reached the defender (a clean hit or a partial block)."""
        return self.outcome in (AttackOutcome.HIT, AttackOutcome.BLOCKED)

    @property
    def executed(self) -> bool:
        """The attack was performed, whatever the defender did about it."""
        return self.outcome in _EXECUTED


_EXECUTED = frozenset(
    {AttackOutcome.HIT, AttackOutcome.BLOCKED, AttackOutcome.PARRIED, AttackOutcome.DODGED}
)


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


def infer_death_context(attacker: Entity, defender: Entity) -> DeathContext:
    """PvP when two player characters fight, otherwise open world.

    Dungeon and world-event code will pass their context explicitly.
    """
    if attacker.is_player_character and defender.is_player_character:
        return DeathContext.PVP
    return DeathContext.OPEN_WORLD


def apply_defense(defender: Entity, attack: Attack, damage: float) -> Tuple[AttackOutcome, float, float, bool]:
    """Resolve the defender's active defense against incoming ``damage``.

    Order: dodge, then parry, then block. Returns
    ``(outcome, damage_after_defense, absorbed, guard_broken)``.
    """
    state = defender.defense
    config = state.config
    guard = defender.guard_profile()
    is_magic = attack.damage_type is DamageType.MAGIC

    if state.is_dodging:
        return AttackOutcome.DODGED, 0.0, 0.0, False

    if state.is_parrying and guard.can_parry and (config.parry_affects_magic or not is_magic):
        remaining = damage * config.parry_damage_ratio
        return AttackOutcome.PARRIED, remaining, damage - remaining, False

    if state.blocking and guard.can_block and (config.block_affects_magic or not is_magic):
        wanted = damage * guard.block_capability
        per_point = config.block_stamina_per_damage
        affordable = defender.stats.stamina / per_point if per_point > 0 else wanted
        absorbed = min(wanted, affordable)
        defender.stats.consume_stamina(min(defender.stats.stamina, absorbed * per_point))
        guard_broken = absorbed < wanted
        if guard_broken:
            state.stop_block()  # stamina exhausted: the guard collapses
        return AttackOutcome.BLOCKED, damage - absorbed, absorbed, guard_broken

    return AttackOutcome.HIT, damage, 0.0, False


def resolve_attack(
    attacker: Entity,
    defender: Entity,
    attack: Attack,
    check_range: bool = True,
    world_time: Optional[float] = None,
    context: Optional[DeathContext] = None,
    context_id: Optional[str] = None,
) -> AttackResult:
    """Validate, pay costs, apply defenses and damage for one attack.

    Costs are paid whenever the attack is executed, including when it is
    blocked, parried or dodged. Failed validation (range, resources, dead
    participants) costs nothing. The same function serves PvE and PvP.
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
    outcome, damage, absorbed, guard_broken = apply_defense(defender, attack, damage)

    applied = 0.0
    if damage > 0:
        applied = defender.receive_damage(
            damage,
            source_id=attacker.entity_id,
            cause=f"{attack.damage_type.value}:{attack.name}",
            world_time=world_time,
            context=context or infer_death_context(attacker, defender),
            context_id=context_id,
        )
    killed = not defender.is_alive
    return AttackResult(
        outcome,
        applied,
        killed,
        defender.death if killed else None,
        attack.element,
        absorbed,
        guard_broken,
    )


def attack_interval(attack: Attack, agility: float) -> float:
    """Cooldown after ``attack``; agility shortens it with diminishing returns."""
    return attack.cooldown / (1.0 + max(0.0, agility) / 100.0)


def try_attack(
    attacker: Entity,
    defender: Entity,
    attack: Attack,
    cooldown: "Cooldown",
    world_time: Optional[float] = None,
    context: Optional[DeathContext] = None,
    context_id: Optional[str] = None,
) -> AttackResult:
    """``resolve_attack`` gated by a cooldown, which restarts once executed."""
    if not cooldown.ready:
        return AttackResult(AttackOutcome.ON_COOLDOWN)
    result = resolve_attack(attacker, defender, attack, world_time=world_time, context=context, context_id=context_id)
    if result.executed:
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
