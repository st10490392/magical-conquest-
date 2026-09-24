"""Headless game session: ties player, enemies, combat and world together.

The Pygame layer converts keyboard/mouse state into a ``PlayerInput`` and
draws the session; everything else happens here, so the whole demo loop can
be driven by tests or a future server without a window.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List, Optional

from game.ai.space import Bounds
from game.ai.states import AIState
from game.core.combat import AttackOutcome, AttackResult
from game.core.defense import DefenseAction
from game.core.entity import DeathRecord
from game.core.vector import Vec2
from game.encounters.catalog import get_encounter
from game.encounters.encounter import CombatEvent, Encounter, EncounterStatus
from game.entities.enemy import Enemy
from game.entities.player import Player
from game.equipment.catalog import WEAPONS
from game.magic.attributes import MagicAttribute
from game.magic.catalog import SPELLS
from game.magic.casting import check_spell_requirements
from game.world.world_state import WorldState

# PROTOTYPE VALUES - NON-FINAL BALANCE.
STAMINA_REGEN_PER_SECOND = 15.0
MANA_REGEN_PER_SECOND = 4.0
ENEMY_RESPAWN_SECONDS = 3.0  # repeating encounters (goblin training) only
BLOCK_MOVE_MULTIPLIER = 0.5
DODGE_SPEED_MULTIPLIER = 2.8

# Attributes the demo character starts with. Deliberately not all of them,
# so the demo also shows the "missing attribute" requirement.
DEMO_ATTRIBUTES = (MagicAttribute.FIRE, MagicAttribute.ICE, MagicAttribute.WIND, MagicAttribute.LIGHTNING, MagicAttribute.LIGHT)
STARTING_WEAPON_ID = "iron_sword"

# GameSession.new() keeps the MC-002 goblin loop; the Pygame demo starts
# with the mixed MC-003 encounter instead.
DEFAULT_ENCOUNTER_ID = "goblin_training"

# Order in which TAB cycles weapons; None means unarmed.
WEAPON_CYCLE = (*WEAPONS.keys(), None)


@dataclass(frozen=True)
class PlayerInput:
    """One frame of player intent.

    ``melee``, ``magic`` and ``block`` are held states; ``parry``, ``dodge``,
    ``cycle_weapon`` and ``select_spell`` are one-shot presses.
    """

    move: Vec2 = Vec2()
    melee: bool = False  # attack with the equipped weapon (or unarmed)
    magic: bool = False  # cast the selected spell
    block: bool = False
    parry: bool = False
    dodge: bool = False
    cycle_weapon: bool = False
    select_spell: Optional[int] = None  # 0-based index into the spellbook


@dataclass
class Arena:
    width: float = 800.0
    height: float = 600.0

    def clamp(self, position: Vec2, margin: float) -> Vec2:
        return position.clamped(margin, margin, self.width - margin, self.height - margin)


def outcome_text(outcome: AttackOutcome) -> str:
    return outcome.value.replace("_", " ")


@dataclass
class GameSession:
    """One playable scenario: the player, the world clock and an encounter."""

    player: Player
    world: WorldState = field(default_factory=WorldState)
    arena: Arena = field(default_factory=Arena)
    encounter_id: str = DEFAULT_ENCOUNTER_ID
    encounter: Optional[Encounter] = None
    kills: int = 0
    messages: List[str] = field(default_factory=list)
    last_player_death: Optional[DeathRecord] = None
    _respawn_timer: float = 0.0

    def __post_init__(self) -> None:
        if self.encounter is None:
            self.start_encounter(self.encounter_id)

    @classmethod
    def new(
        cls,
        player_name: str = "Hero",
        arena: Optional[Arena] = None,
        encounter_id: str = DEFAULT_ENCOUNTER_ID,
    ) -> "GameSession":
        arena = arena or Arena()
        player = Player(
            player_name,
            position=Vec2(arena.width * 0.2, arena.height * 0.5),
            magic_attributes=DEMO_ATTRIBUTES,
        )
        player.equip(WEAPONS[STARTING_WEAPON_ID])
        for spell in SPELLS.values():
            player.learn_spell(spell)
        return cls(player=player, arena=arena, encounter_id=encounter_id)

    # ------------------------------------------------------------- encounter
    @property
    def bounds(self) -> Bounds:
        return (0.0, 0.0, self.arena.width, self.arena.height)

    def start_encounter(self, encounter_id: str, mirror: bool = False) -> Encounter:
        spec = get_encounter(encounter_id)
        if mirror:  # respawn on the far side from the player
            spec = replace(spec, spawns=tuple(replace(s, x=self.arena.width - s.x) for s in spec.spawns))
        self.encounter_id = encounter_id
        self.encounter = Encounter(spec, self.player.level, self.bounds)
        return self.encounter

    @property
    def enemies(self) -> List[Enemy]:
        return self.encounter.enemies

    @property
    def enemy(self) -> Optional[Enemy]:
        """The nearest living enemy (the player's target), else the first one."""
        nearest = self.encounter.nearest_enemy(self.player.position)
        return nearest if nearest is not None else (self.enemies[0] if self.enemies else None)

    def log(self, text: str) -> None:
        self.messages.append(text)
        del self.messages[:-6]  # keep only the recent ones for the HUD

    # ------------------------------------------------------------------ loop
    def update(self, dt: float, controls: PlayerInput) -> None:
        self.world.tick(dt)
        player = self.player
        player.update(dt)

        if player.is_alive:
            self._handle_loadout_input(controls)
            self._handle_defense_input(controls)
            self._move_player(dt, controls)

        target = self.encounter.nearest_enemy(player.position)
        busy = player.defense.blocking or player.defense.is_dodging
        if target is not None and player.is_alive and not busy:
            if controls.melee:
                self._player_attack(target, player.weapon_attack(target, self.world.time))
            elif controls.magic:
                self._player_attack(target, player.cast(target, world_time=self.world.time))

        encounter = self.encounter
        was_over = encounter.is_over
        for event in encounter.update(dt, player, self.world.time):
            self._report_enemy_attack(event)
        if not player.is_alive and self.last_player_death is None:
            self.last_player_death = player.death
        if encounter.is_over and not was_over:
            self._on_encounter_over(encounter)
        if encounter.status is EncounterStatus.CLEARED and encounter.spec.repeat_on_clear:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0 and player.is_alive:
                near = any(player.position.distance_to(Vec2(s.x, s.y)) < 200 for s in encounter.spec.spawns)
                self.start_encounter(self.encounter_id, mirror=near)
                for enemy in self.enemies:
                    self.log(f"A level {enemy.level} {enemy.name} appears.")

    def _handle_loadout_input(self, controls: PlayerInput) -> None:
        player = self.player
        if controls.select_spell is not None and player.spellbook.select_index(controls.select_spell):
            spell = player.spellbook.selected
            problem = check_spell_requirements(player, spell)
            note = f" ({outcome_text(problem)})" if problem else ""
            self.log(f"Selected {spell.name} [{spell.rank.value}-rank {spell.element.label}]{note}")
        if controls.cycle_weapon:
            current = player.weapon.weapon_id if player.weapon else None
            next_id = WEAPON_CYCLE[(WEAPON_CYCLE.index(current) + 1) % len(WEAPON_CYCLE)]
            if next_id is None:
                player.unequip()
                self.log("Unequipped weapon (unarmed)")
            else:
                player.equip(WEAPONS[next_id])
                self.log(f"Equipped {WEAPONS[next_id].name}")

    def _handle_defense_input(self, controls: PlayerInput) -> None:
        player = self.player
        if controls.dodge:
            action = player.dodge()
            if action is not DefenseAction.STARTED:
                self.log(f"Dodge: {action.value.replace('_', ' ')}")
        if controls.parry:
            action = player.parry()
            if action is not DefenseAction.STARTED:
                self.log(f"Parry: {action.value.replace('_', ' ')}")
        if controls.block and not player.defense.blocking and not player.defense.is_dodging:
            player.start_block()  # silently does nothing with a weapon that cannot block
        elif not controls.block and player.defense.blocking:
            player.stop_block()

    def _move_player(self, dt: float, controls: PlayerInput) -> None:
        player = self.player
        defense = player.defense
        if defense.is_dodging:
            direction = controls.move if controls.move.length() else player.facing
            player.move(direction, dt * DODGE_SPEED_MULTIPLIER)
        elif defense.blocking:
            player.move(controls.move, dt * BLOCK_MOVE_MULTIPLIER)
        else:
            player.move(controls.move, dt)
        player.position = self.arena.clamp(player.position, player.size / 2)
        if not defense.blocking and not defense.is_dodging:
            player.stats.restore_stamina(STAMINA_REGEN_PER_SECOND * dt)
        player.stats.restore_mana(MANA_REGEN_PER_SECOND * dt)

    # ------------------------------------------------------------- reporting
    def _player_attack(self, target: Enemy, result: AttackResult) -> AttackResult:
        if result.landed:
            note = " (staggered!)" if target.state is AIState.STAGGERED else ""
            self.log(f"You hit {target.name} for {result.damage:.1f}{note}")
            if result.killed:
                self._on_enemy_killed(target)
        elif result.outcome not in (AttackOutcome.ON_COOLDOWN, AttackOutcome.OUT_OF_RANGE):
            self.log(outcome_text(result.outcome))
        return result

    def _report_enemy_attack(self, event: CombatEvent) -> None:
        name, result = event.attacker.name, event.result
        verb = "shoots" if event.ranged else "hits"
        outcome = result.outcome
        if outcome is AttackOutcome.HIT:
            self.log(f"{name} {verb} you for {result.damage:.1f}")
        elif outcome is AttackOutcome.BLOCKED:
            broken = " - guard broken!" if result.guard_broken else ""
            self.log(f"Blocked {name}: {result.absorbed:.1f} absorbed, took {result.damage:.1f}{broken}")
        elif outcome is AttackOutcome.PARRIED:
            staggered = " - it staggers!" if event.attacker.state is AIState.STAGGERED else ""
            self.log(f"Parried {name}!{staggered}")
        elif outcome is AttackOutcome.DODGED:
            self.log(f"Dodged {name}!")
        elif outcome is AttackOutcome.OUT_OF_RANGE:
            self.log(f"{name} swings and misses")
        if result.killed and event.target is self.player:
            self.log(f"You died ({result.death.context.value}).")

    def _on_encounter_over(self, encounter: Encounter) -> None:
        if encounter.status is EncounterStatus.CLEARED:
            self.log(f"{encounter.spec.name}: cleared in {encounter.elapsed:.1f}s")
            self._respawn_timer = ENEMY_RESPAWN_SECONDS
        else:
            self.log(f"{encounter.spec.name}: failed - press R to restart")

    def _on_enemy_killed(self, enemy: Enemy) -> None:
        self.kills += 1
        gained = self.player.gain_xp(enemy.xp_reward)
        self.log(f"{enemy.name} defeated! +{enemy.xp_reward} XP")
        if gained.levels_gained:
            self.log(f"Level up! You are now level {gained.new_level}")
