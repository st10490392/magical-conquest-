"""Player character built on the shared Entity foundation."""

from __future__ import annotations

from enum import Enum
from typing import Dict, Iterable, Optional

from game.core.combat import Attack, AttackOutcome, AttackResult, Cooldown, DamageType, try_attack
from game.core.defense import GuardProfile
from game.core.entity import DeathContext, Entity
from game.core.stats import Stats
from game.core.vector import Vec2
from game.equipment.loadout import Equipment, Equippable, EquipSlot
from game.equipment.weapons import Weapon
from game.items.inventory import DEFAULT_CAPACITY, Inventory
from game.magic.attributes import MagicAttribute
from game.magic.casting import cast_spell
from game.magic.catalog import SPELLS
from game.magic.spellbook import SpellBook
from game.magic.spells import Spell
from game.progression.experience import Experience, LevelUpResult, ProgressionCurve
from game.progression.growth import StatGrowth

# Unarmed strike, used when no weapon is equipped.
MELEE_STRIKE = Attack(
    name="melee_strike",
    damage_type=DamageType.PHYSICAL,
    base_power=8.0,
    scaling=1.0,
    reach=70.0,
    cooldown=0.4,
    stamina_cost=8.0,
)

# Kept for MC-001 callers: the raw combat Attack behind the Fire Bolt spell.
# Using it directly skips spell requirements; use Player.cast for spells.
FIRE_BOLT = SPELLS["fire_bolt"].attack


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
    is_player_character = True

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
        magic_attributes: Iterable[MagicAttribute] = (),
        inventory_capacity: int = DEFAULT_CAPACITY,
    ) -> None:
        super().__init__(
            name,
            stats if stats is not None else default_player_stats(),
            level=level,
            entity_id=entity_id,
            position=position,
            magic_attributes=magic_attributes,
        )
        self.experience = Experience(xp, curve)
        self.growth = growth or StatGrowth()
        self.movement_state = MovementState.IDLE
        self.facing = Vec2(1.0, 0.0)
        self.attack_cooldown = Cooldown()
        self.equipment = Equipment()
        self.spellbook = SpellBook()
        self.inventory = Inventory(inventory_capacity)
        # Attribute bonuses currently applied to ``stats`` by equipment.
        self._applied_modifiers: Dict[str, float] = {}

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
        self.spellbook.tick(dt)
        self.defense.tick(dt)
        if not self.is_alive:
            self.movement_state = MovementState.DEAD

    # ----------------------------------------------------------- equipment
    @property
    def weapon(self) -> Optional[Weapon]:
        return self.equipment.weapon

    def equip(self, item: Equippable) -> Optional[Equippable]:
        """Equip a weapon or armor piece directly (no inventory involved).

        Returns what it replaced. For inventory-aware equipping use
        ``game.items.actions.equip_from_inventory``.
        """
        previous = self.equipment.equip(item)
        self._refresh_equipment_modifiers()
        if not self.guard_profile().can_block:
            self.stop_block()
        return previous

    def unequip(self, slot: EquipSlot = EquipSlot.MAIN_HAND) -> Optional[Equippable]:
        if slot is EquipSlot.MAIN_HAND:
            self.stop_block()
        item = self.equipment.unequip(slot)
        self._refresh_equipment_modifiers()
        return item

    def _refresh_equipment_modifiers(self) -> None:
        """Apply only the *difference* between the new and the applied
        bonuses, rounded, so repeated equip/unequip can never drift or
        inflate stats."""
        new = self.equipment.total_modifiers()
        for name in set(new) | set(self._applied_modifiers):
            delta = new.get(name, 0.0) - self._applied_modifiers.get(name, 0.0)
            if delta:
                value = round(getattr(self.stats, name) + delta, 6)
                setattr(self.stats, name, max(0.0, value))
        self._applied_modifiers = new

    @property
    def equipment_bonuses(self) -> Dict[str, float]:
        return dict(self._applied_modifiers)

    def base_stats(self) -> Stats:
        """Stats without equipment bonuses (what gets saved)."""
        data = self.stats.to_dict()
        for name, value in self._applied_modifiers.items():
            data[name] = max(0.0, round(data[name] - value, 6))
        return Stats.from_dict(data)

    def owned_count(self, item_id: str) -> int:
        """Copies held in the inventory plus equipped ones."""
        equipped = sum(1 for item in self.equipment.items().values() if item.item_id == item_id)
        return self.inventory.count(item_id) + equipped

    def guard_profile(self) -> GuardProfile:
        return self.equipment.guard_profile()

    # -------------------------------------------------------------- combat
    def attack(
        self,
        target: Entity,
        attack: Attack = MELEE_STRIKE,
        world_time: Optional[float] = None,
        context: Optional[DeathContext] = None,
    ) -> AttackResult:
        """Low-level attack with any ``Attack`` (MC-001 API)."""
        return try_attack(self, target, attack, self.attack_cooldown, world_time, context)

    def weapon_attack(
        self, target: Entity, world_time: Optional[float] = None, context: Optional[DeathContext] = None
    ) -> AttackResult:
        """Attack with the equipped weapon, or unarmed if none is equipped."""
        attack = self.weapon.attack if self.weapon else MELEE_STRIKE
        return self.attack(target, attack, world_time, context)

    def learn_spell(self, spell: Spell) -> None:
        self.spellbook.learn(spell)

    def cast(
        self,
        target: Entity,
        spell: Optional[Spell] = None,
        world_time: Optional[float] = None,
        context: Optional[DeathContext] = None,
    ) -> AttackResult:
        """Cast ``spell`` (default: the selected one), enforcing requirements."""
        spell = spell or self.spellbook.selected
        if spell is None:
            return AttackResult(AttackOutcome.NO_SPELL_SELECTED)
        if not self.spellbook.knows(spell):
            return AttackResult(AttackOutcome.SPELL_NOT_KNOWN, element=spell.element)
        return cast_spell(self, target, spell, self.spellbook.cooldown_for(spell), world_time, context)

    def gain_xp(self, amount: int) -> LevelUpResult:
        """Add XP; each level gained applies ``growth`` and refills pools."""
        result = self.experience.add(self.level, amount)
        if result.levels_gained and self.is_alive:
            self.growth.apply(self.stats, result.levels_gained)
        self.level = result.new_level
        return result
