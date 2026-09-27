"""The prototype world: three connected zones.

PROTOTYPE / NON-CANON LOCATIONS. Not the Royal Kingdom or any canonical
geography; names are placeholders.

    Prototype Village (safe)  <->  Prototype Road (wild)  <->  Prototype Wilds (wild)
"""

from __future__ import annotations

from game.core.vector import Vec2
from game.encounters.catalog import ENCOUNTERS
from game.npcs.catalog import NPCS
from game.world.zones import (
    EncounterPlacement,
    PointOfInterest,
    Rect,
    RespawnRule,
    WorldGraph,
    ZoneDefinition,
    ZoneExit,
    ZoneKind,
)

EAST_EDGE = Rect(770, 200, 30, 200)
WEST_EDGE = Rect(0, 200, 30, 200)

VILLAGE = ZoneDefinition(
    "proto_village", "Prototype Village", ZoneKind.SAFE,
    spawn_points=(("default", Vec2(400, 300)), ("from_road", Vec2(720, 300))),
    exits=(ZoneExit("to_road", EAST_EDGE, "proto_road", "from_village"),),
    points_of_interest=(PointOfInterest("village_square", "Village Square", Vec2(400, 300), 80),),
    description="A quiet settlement. No fighting here.",
)

ROAD = ZoneDefinition(
    "proto_road", "Prototype Road", ZoneKind.WILD,
    spawn_points=(("default", Vec2(80, 300)), ("from_village", Vec2(80, 300)), ("from_wilds", Vec2(720, 300))),
    exits=(
        ZoneExit("to_village", WEST_EDGE, "proto_village", "from_road"),
        ZoneExit("to_wilds", EAST_EDGE, "proto_wilds", "from_road"),
    ),
    encounters=(EncounterPlacement("ambush", "road_ambush", RespawnRule.ON_REENTRY),),
    points_of_interest=(PointOfInterest("old_milestone", "Old Milestone", Vec2(400, 540), 50, discovery_xp=15),),
)

WILDS = ZoneDefinition(
    "proto_wilds", "Prototype Wilds", ZoneKind.WILD,
    spawn_points=(("default", Vec2(80, 300)), ("from_road", Vec2(80, 300))),
    exits=(ZoneExit("to_road", WEST_EDGE, "proto_road", "from_wilds"),),
    encounters=(
        EncounterPlacement("camp", "raider_camp", RespawnRule.ON_REENTRY),
        EncounterPlacement("den", "brute_den", RespawnRule.NEVER),
    ),
    points_of_interest=(PointOfInterest("watchtower", "Old Watchtower", Vec2(700, 250), 60, discovery_xp=25),),
)

WORLD = WorldGraph((VILLAGE, ROAD, WILDS), start_zone="proto_village")
WORLD.validate_references(lambda e: e in ENCOUNTERS, {n.npc_id: n.location_id for n in NPCS.values()})


def npcs_in(zone_id: str):
    return [npc for npc in NPCS.values() if npc.location_id == zone_id]
