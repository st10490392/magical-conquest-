"""Saved exploration progress and the player's location."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Set

from game.core.vector import Vec2
from game.world.zones import RespawnRule, WorldGraph


@dataclass(frozen=True)
class Location:
    zone_id: str
    position: Vec2

    def to_dict(self) -> dict:
        return {"zone": self.zone_id, "x": self.position.x, "y": self.position.y}

    @classmethod
    def from_dict(cls, data, graph: WorldGraph) -> "Location":
        if not isinstance(data, dict) or set(data) != {"zone", "x", "y"}:
            raise ValueError("location must be {zone, x, y}")
        zone = graph.zone(data["zone"])
        x, y = data["x"], data["y"]
        for value in (x, y):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("location coordinates must be finite numbers")
        position = Vec2(float(x), float(y))
        if not zone.contains(position):
            raise ValueError(f"location is outside {zone.zone_id}")
        return cls(zone.zone_id, position)


def cleared_key(zone_id: str, placement_id: str) -> str:
    return f"{zone_id}/{placement_id}"


@dataclass
class Exploration:
    visited_zones: Set[str] = field(default_factory=set)
    discovered: Set[str] = field(default_factory=set)  # point-of-interest ids
    cleared: Set[str] = field(default_factory=set)  # "zone/placement" of NEVER-respawn encounters

    def to_dict(self) -> dict:
        return {
            "visited_zones": sorted(self.visited_zones),
            "discovered": sorted(self.discovered),
            "cleared": sorted(self.cleared),
        }

    @classmethod
    def from_dict(cls, data, graph: WorldGraph) -> "Exploration":
        if not isinstance(data, dict) or set(data) != {"visited_zones", "discovered", "cleared"}:
            raise ValueError("exploration must be {visited_zones, discovered, cleared}")
        for key in data:
            if not isinstance(data[key], list) or not all(isinstance(v, str) for v in data[key]):
                raise TypeError(f"exploration.{key} must be a list of strings")
        for zone_id in data["visited_zones"]:
            graph.zone(zone_id)
        for poi_id in data["discovered"]:
            if graph.poi(poi_id) is None:
                raise ValueError(f"unknown point of interest {poi_id!r}")
        for key in data["cleared"]:
            zone_id, _, placement_id = key.partition("/")
            placement = graph.zone(zone_id).placement(placement_id)
            if placement is None or placement.respawn is not RespawnRule.NEVER:
                raise ValueError(f"{key!r} is not a permanently clearable encounter")
        return cls(set(data["visited_zones"]), set(data["discovered"]), set(data["cleared"]))


