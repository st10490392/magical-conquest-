"""The zone-based world session (MC-006): travel between connected zones.

Adds to ``PlaySession``:

* a current ``ZoneInstance`` (live encounters + ground loot) rebuilt on entry;
* travel by walking into an exit area (``ZoneLeft`` / ``ZoneEntered`` and a
  ``LocationReached`` for the zone id, so REACH objectives can target zones);
* point-of-interest discovery (``LocationReached`` + a once-only XP reward);
* permanent clearing of NEVER-respawn encounters;
* safe zones where fighting is disabled;
* a no-penalty respawn at the start zone after death.

World time is the single ``WorldState`` clock; it keeps running across travel.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from game.core.vector import Vec2
from game.encounters.encounter import Encounter, EncounterStatus
from game.events.events import LocationReached, ZoneEntered, ZoneLeft
from game.items.catalog import get_item
from game.npcs.definitions import NpcDefinition
from game.play import Arena, PlayerInput, PlaySession, make_demo_player
from game.progression.rewards import Reward, grant_reward
from game.world.exploration import Location, cleared_key
from game.world.zone_catalog import WORLD, npcs_in
from game.world.zone_instance import ZoneInstance
from game.world.zones import RespawnRule, WorldGraph, ZoneDefinition

# The adventurer's starting bag in the world (PROTOTYPE / NON-FINAL).
WORLD_STARTING_KIT = (("minor_health_potion", 2), ("minor_mana_potion", 1))


class TravelStatus(str, Enum):
    OK = "ok"
    UNKNOWN_EXIT = "unknown_exit"
    DEAD = "dead"
    IN_CONVERSATION = "in_conversation"


@dataclass
class WorldSession(PlaySession):
    graph: WorldGraph = WORLD
    zone: Optional[ZoneInstance] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        location = self.campaign.location
        if location is None:
            start = self.graph.zone(self.graph.start_zone)
            location = Location(start.zone_id, start.spawn())
        self.enter_zone(location.zone_id, position=location.position, announce=self.campaign.location is None)

    @classmethod
    def new(cls, player_name: str = "Hero") -> "WorldSession":
        player = make_demo_player(player_name, Vec2(), kit=WORLD_STARTING_KIT)
        return cls(player=player)

    # ------------------------------------------------------------- queries
    @property
    def zone_definition(self) -> ZoneDefinition:
        return self.zone.definition

    @property
    def location_id(self) -> Optional[str]:
        return self.zone.zone_id if self.zone else None

    @property
    def encounters(self) -> List[Encounter]:
        return self.zone.running() if self.zone else []

    @property
    def npcs(self) -> List[NpcDefinition]:
        return npcs_in(self.zone.zone_id) if self.zone else []

    @property
    def in_safe_zone(self) -> bool:
        return self.zone_definition.is_safe

    # --------------------------------------------------------- navigation
    def enter_zone(self, zone_id: str, spawn: str = "default", position: Optional[Vec2] = None,
                   announce: bool = True) -> ZoneDefinition:
        definition = self.graph.zone(zone_id)
        self.zone = ZoneInstance(definition, self.campaign.exploration, self.player.level)
        self.ground = self.zone.ground
        self.arena = Arena(definition.width, definition.height)
        self.player.position = position if position is not None else definition.spawn(spawn)
        self.campaign.location = Location(zone_id, self.player.position)
        first_visit = zone_id not in self.campaign.exploration.visited_zones
        self.campaign.exploration.visited_zones.add(zone_id)
        if announce:
            kind = "safe" if definition.is_safe else "hostile"
            self.log(f"Entered {definition.name} ({kind}){' - first visit' if first_visit else ''}")
            self.bus.publish(ZoneEntered(zone_id))
            self.bus.publish(LocationReached(zone_id))
        return definition

    def travel(self, exit_id: str) -> TravelStatus:
        exit_ = self.zone_definition.exit(exit_id)
        if exit_ is None:
            return TravelStatus.UNKNOWN_EXIT
        if not self.player.is_alive:
            return TravelStatus.DEAD
        if self.conversation is not None:
            return TravelStatus.IN_CONVERSATION
        self.player.stop_block()
        self.bus.publish(ZoneLeft(self.zone.zone_id))
        self.enter_zone(exit_.target_zone, exit_.target_spawn)
        return TravelStatus.OK

    def respawn(self) -> bool:
        """After death: revive at the start zone. No penalties (deferred)."""
        if self.player.is_alive:
            return False
        self.player.revive()
        self.last_player_death = None
        self.enter_zone(self.graph.start_zone)
        self.log("You wake up in the village.")
        return True

    # ---------------------------------------------------------- per tick
    def update(self, dt: float, controls: PlayerInput) -> None:
        if self.in_safe_zone:  # no fighting in settlements
            controls = PlayerInput(move=controls.move, block=False, parry=False, dodge=controls.dodge,
                                   cycle_weapon=controls.cycle_weapon, select_spell=controls.select_spell,
                                   interact=controls.interact)
        super().update(dt, controls)

    def _after_update(self, dt: float) -> None:
        player = self.player
        if not player.is_alive:
            return
        self.campaign.location = Location(self.zone.zone_id, player.position)
        self._discover()
        exit_ = self.zone_definition.exit_at(player.position)
        if exit_ is not None and self.conversation is None:
            self.travel(exit_.exit_id)

    def _discover(self) -> None:
        exploration = self.campaign.exploration
        for poi in self.zone_definition.points_of_interest:
            if poi.poi_id in exploration.discovered or poi.position.distance_to(self.player.position) > poi.radius:
                continue
            exploration.discovered.add(poi.poi_id)
            self.log(f"Discovered: {poi.name}")
            if poi.discovery_xp:
                grant = grant_reward(self.player, Reward(xp=poi.discovery_xp), f"discovery:{poi.poi_id}",
                                     self.campaign.ledger, get_item)
                if grant.ok:
                    self.log(f"+{poi.discovery_xp} XP for exploring")
            self.bus.publish(LocationReached(poi.poi_id))

    def _on_encounter_over(self, encounter: Encounter) -> None:
        super()._on_encounter_over(encounter)
        placement_id = self.zone.placement_of(encounter)
        placement = self.zone_definition.placement(placement_id) if placement_id else None
        if encounter.status is EncounterStatus.CLEARED and placement and placement.respawn is RespawnRule.NEVER:
            self.campaign.exploration.cleared.add(cleared_key(self.zone.zone_id, placement_id))
