"""A zone the player is currently in: its live encounters and ground loot.

Built fresh on every entry and discarded on exit, so:

* ON_REENTRY encounters come back at full strength after leaving;
* NEVER encounters that were cleared (recorded in ``Exploration``) stay gone;
* loot left on the ground is lost when you leave (prototype rule).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from game.encounters.catalog import get_encounter
from game.encounters.encounter import Encounter
from game.items.ground import GroundLoot
from game.world.exploration import Exploration, cleared_key
from game.world.zones import RespawnRule, ZoneDefinition


class ZoneInstance:
    def __init__(self, definition: ZoneDefinition, exploration: Exploration, player_level: int) -> None:
        self.definition = definition
        self.ground = GroundLoot()
        self.encounters: Dict[str, Encounter] = {}
        bounds = (0.0, 0.0, definition.width, definition.height)
        for placement in definition.encounters:
            if placement.respawn is RespawnRule.NEVER and cleared_key(definition.zone_id, placement.placement_id) in exploration.cleared:
                continue
            self.encounters[placement.placement_id] = Encounter(
                get_encounter(placement.encounter_id), player_level, bounds
            )

    @property
    def zone_id(self) -> str:
        return self.definition.zone_id

    def running(self) -> List[Encounter]:
        return list(self.encounters.values())

    def placement_of(self, encounter: Encounter) -> Optional[str]:
        for placement_id, candidate in self.encounters.items():
            if candidate is encounter:
                return placement_id
        return None
