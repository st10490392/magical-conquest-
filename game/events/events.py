"""Domain events. Systems publish what happened; other systems (quests,
logs, later achievements or world events) react without direct coupling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GameEvent:
    """Base class for all domain events."""


@dataclass(frozen=True)
class EnemyDefeated(GameEvent):
    enemy_id: str
    archetype_id: str
    encounter_id: Optional[str] = None
    zone_id: Optional[str] = None


@dataclass(frozen=True)
class ItemObtained(GameEvent):
    item_id: str
    quantity: int
    source: str = ""  # "loot", "reward", "purchase"...


@dataclass(frozen=True)
class NpcInteracted(GameEvent):
    npc_id: str


@dataclass(frozen=True)
class LocationReached(GameEvent):
    """A named location or point of interest was reached."""

    location_id: str


@dataclass(frozen=True)
class QuestProgressed(GameEvent):
    quest_id: str
    objective_id: str
    count: int
    required: int


@dataclass(frozen=True)
class QuestStatusChanged(GameEvent):
    quest_id: str
    status: str
