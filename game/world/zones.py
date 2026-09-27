"""Zone definitions and the world graph that connects them.

PROTOTYPE world model: a handful of single-screen zones joined by exits.
It is not the Magical Conquest world map.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from game.core.vector import Vec2


class ZoneKind(str, Enum):
    SAFE = "safe"  # settlements: no hostile encounters may be placed here
    WILD = "wild"  # encounters allowed


class RespawnRule(str, Enum):
    ON_REENTRY = "on_reentry"  # rebuilt fresh every time the zone is entered
    NEVER = "never"  # once cleared, stays cleared (saved)


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def contains(self, point: Vec2) -> bool:
        return self.x <= point.x <= self.x + self.w and self.y <= point.y <= self.y + self.h

    @property
    def centre(self) -> Vec2:
        return Vec2(self.x + self.w / 2, self.y + self.h / 2)


@dataclass(frozen=True)
class ZoneExit:
    exit_id: str
    area: Rect  # walking into this area travels
    target_zone: str
    target_spawn: str


@dataclass(frozen=True)
class EncounterPlacement:
    placement_id: str
    encounter_id: str
    respawn: RespawnRule = RespawnRule.ON_REENTRY


@dataclass(frozen=True)
class PointOfInterest:
    poi_id: str
    name: str
    position: Vec2
    radius: float = 60.0
    discovery_xp: int = 0  # PROTOTYPE / NON-FINAL


@dataclass(frozen=True)
class ZoneDefinition:
    zone_id: str
    name: str
    kind: ZoneKind
    spawn_points: Tuple[Tuple[str, Vec2], ...]
    exits: Tuple[ZoneExit, ...] = ()
    encounters: Tuple[EncounterPlacement, ...] = ()
    points_of_interest: Tuple[PointOfInterest, ...] = ()
    width: float = 800.0
    height: float = 600.0
    description: str = ""

    def __post_init__(self) -> None:
        if not self.zone_id or not self.name:
            raise ValueError("zone_id and name are required")
        names = [name for name, _ in self.spawn_points]
        if "default" not in names or len(set(names)) != len(names):
            raise ValueError(f"{self.zone_id}: needs unique spawn names including 'default'")
        for name, point in self.spawn_points:
            if not self.contains(point):
                raise ValueError(f"{self.zone_id}: spawn {name} is outside the zone")
        if self.kind is ZoneKind.SAFE and self.encounters:
            raise ValueError(f"{self.zone_id}: safe zones cannot host encounters")
        for ids in (
            [e.exit_id for e in self.exits],
            [p.placement_id for p in self.encounters],
            [p.poi_id for p in self.points_of_interest],
        ):
            if len(set(ids)) != len(ids):
                raise ValueError(f"{self.zone_id}: duplicate ids")

    @property
    def is_safe(self) -> bool:
        return self.kind is ZoneKind.SAFE

    def contains(self, point: Vec2) -> bool:
        return (math.isfinite(point.x) and math.isfinite(point.y)
                and 0 <= point.x <= self.width and 0 <= point.y <= self.height)

    def spawn(self, name: str = "default") -> Vec2:
        for spawn_name, point in self.spawn_points:
            if spawn_name == name:
                return point
        raise KeyError(f"{self.zone_id} has no spawn {name!r}")

    def exit(self, exit_id: str) -> Optional[ZoneExit]:
        return next((e for e in self.exits if e.exit_id == exit_id), None)

    def exit_at(self, point: Vec2) -> Optional[ZoneExit]:
        return next((e for e in self.exits if e.area.contains(point)), None)

    def placement(self, placement_id: str) -> Optional[EncounterPlacement]:
        return next((p for p in self.encounters if p.placement_id == placement_id), None)


class WorldGraph:
    """All zones plus validated connections between them."""

    def __init__(self, zones: Iterable[ZoneDefinition], start_zone: str) -> None:
        self.zones: Dict[str, ZoneDefinition] = {}
        for zone in zones:
            if zone.zone_id in self.zones:
                raise ValueError(f"duplicate zone {zone.zone_id}")
            self.zones[zone.zone_id] = zone
        if start_zone not in self.zones:
            raise ValueError(f"unknown start zone {start_zone}")
        self.start_zone = start_zone
        for zone in self.zones.values():
            for exit_ in zone.exits:
                target = self.zones.get(exit_.target_zone)
                if target is None:
                    raise ValueError(f"{zone.zone_id}.{exit_.exit_id} leads to unknown zone {exit_.target_zone}")
                try:
                    arrival = target.spawn(exit_.target_spawn)
                except KeyError as exc:
                    raise ValueError(f"{zone.zone_id}.{exit_.exit_id}: {exc.args[0]}") from None
                if target.exit_at(arrival) is not None:
                    raise ValueError(f"{exit_.target_zone}.{exit_.target_spawn} is inside an exit (travel loop)")

    def zone(self, zone_id: str) -> ZoneDefinition:
        try:
            return self.zones[zone_id]
        except KeyError:
            raise ValueError(f"unknown zone {zone_id!r}") from None

    def neighbours(self, zone_id: str) -> List[str]:
        return sorted({e.target_zone for e in self.zone(zone_id).exits})

    def connected(self, a: str, b: str) -> bool:
        return b in self.neighbours(a)

    def poi(self, poi_id: str) -> Optional[Tuple[ZoneDefinition, PointOfInterest]]:
        for zone in self.zones.values():
            for poi in zone.points_of_interest:
                if poi.poi_id == poi_id:
                    return zone, poi
        return None

    def validate_references(self, encounter_exists: Callable[[str], bool], npc_zones: Dict[str, Optional[str]]) -> None:
        for zone in self.zones.values():
            for placement in zone.encounters:
                if not encounter_exists(placement.encounter_id):
                    raise ValueError(f"{zone.zone_id} places unknown encounter {placement.encounter_id}")
        for npc_id, zone_id in npc_zones.items():
            if zone_id is not None and zone_id not in self.zones:
                raise ValueError(f"npc {npc_id} lives in unknown zone {zone_id}")
