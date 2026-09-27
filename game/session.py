"""The arena sandbox session (MC-002 to MC-005 scenarios).

One encounter at a time, chosen by id; ``N`` in the Pygame demo cycles them.
All shared play logic lives in ``game.play.PlaySession``; the zone-based
world is ``game.world_session.WorldSession``. The names that used to live
here are re-exported for compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional

from game.core.vector import Vec2
from game.encounters.catalog import get_encounter
from game.encounters.encounter import Encounter, EncounterStatus
from game.npcs.catalog import get_npc
from game.npcs.definitions import NpcDefinition
from game.play import (  # noqa: F401  (re-exported)
    BLOCK_MOVE_MULTIPLIER,
    DEMO_ATTRIBUTES,
    DODGE_SPEED_MULTIPLIER,
    MANA_REGEN_PER_SECOND,
    STAMINA_REGEN_PER_SECOND,
    STARTING_KIT,
    STARTING_WEAPON_ID,
    WEAPON_CYCLE,
    Arena,
    PlayerInput,
    PlaySession,
    make_demo_player,
    outcome_text,
)

ENEMY_RESPAWN_SECONDS = 3.0  # repeating encounters (goblin training) only

# GameSession.new() keeps the MC-002 goblin loop; the Pygame demo opens the
# world instead (``--arena`` for this sandbox).
DEFAULT_ENCOUNTER_ID = "goblin_training"

# Which prototype NPCs stand in which sandbox scenario (the world uses zones).
SCENARIO_NPCS = {"quest_camp": ("proto_elder", "proto_scout")}


@dataclass
class GameSession(PlaySession):
    """One playable scenario: the player, the world clock and an encounter."""

    encounter_id: str = DEFAULT_ENCOUNTER_ID
    encounter: Optional[Encounter] = None
    _respawn_timer: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
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
        player = make_demo_player(player_name, Vec2(arena.width * 0.2, arena.height * 0.5))
        return cls(player=player, arena=arena, encounter_id=encounter_id)

    def start_encounter(self, encounter_id: str, mirror: bool = False) -> Encounter:
        spec = get_encounter(encounter_id)
        if mirror:  # respawn on the far side from the player
            spec = replace(spec, spawns=tuple(replace(s, x=self.arena.width - s.x) for s in spec.spawns))
        self.encounter_id = encounter_id
        self.encounter = Encounter(spec, self.player.level, self.bounds)
        return self.encounter

    @property
    def encounters(self) -> List[Encounter]:
        return [self.encounter]

    @property
    def npcs(self) -> List[NpcDefinition]:
        return [get_npc(npc_id) for npc_id in SCENARIO_NPCS.get(self.encounter_id, ())]

    def _on_encounter_over(self, encounter: Encounter) -> None:
        super()._on_encounter_over(encounter)
        if encounter.status is EncounterStatus.CLEARED:
            self._respawn_timer = ENEMY_RESPAWN_SECONDS

    def _after_update(self, dt: float) -> None:
        encounter, player = self.encounter, self.player
        if encounter.status is EncounterStatus.CLEARED and encounter.spec.repeat_on_clear:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0 and player.is_alive:
                near = any(player.position.distance_to(Vec2(s.x, s.y)) < 200 for s in encounter.spec.spawns)
                self.start_encounter(self.encounter_id, mirror=near)
                for enemy in self.enemies:
                    self.log(f"A level {enemy.level} {enemy.name} appears.")
