"""Spell requirement checks and casting through the shared combat rules."""

from __future__ import annotations

from typing import Optional

from game.core.combat import AttackOutcome, AttackResult, Cooldown, try_attack
from game.core.entity import DeathContext, Entity
from game.magic.spells import Spell


def check_spell_requirements(caster: Entity, spell: Spell) -> Optional[AttackOutcome]:
    """Return the first unmet requirement, or ``None`` if the caster qualifies."""
    if not caster.has_attribute(spell.element):
        return AttackOutcome.MISSING_ATTRIBUTE
    if caster.level < spell.min_level:
        return AttackOutcome.INSUFFICIENT_LEVEL
    if caster.stats.magic_power < spell.required_magic_power:
        return AttackOutcome.INSUFFICIENT_MAGIC_POWER
    return None


def cast_spell(
    caster: Entity,
    target: Entity,
    spell: Spell,
    cooldown: Cooldown,
    world_time: Optional[float] = None,
    context: Optional[DeathContext] = None,
    context_id: Optional[str] = None,
) -> AttackResult:
    """Enforce requirements, then resolve the spell like any other attack."""
    if not caster.is_alive:
        return AttackResult(AttackOutcome.ATTACKER_DEAD)
    failure = check_spell_requirements(caster, spell)
    if failure is not None:
        return AttackResult(failure, element=spell.element)
    return try_attack(caster, target, spell.attack, cooldown, world_time, context, context_id)
