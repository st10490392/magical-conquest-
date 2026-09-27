"""NPC definitions (static) and per-NPC runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Mapping, Optional, Tuple

from game.core.vector import Vec2

INTERACT_RADIUS = 70.0


class NpcRole(str, Enum):
    VILLAGER = "villager"
    QUEST_GIVER = "quest_giver"
    MERCHANT = "merchant"
    BLACKSMITH = "blacksmith"
    SCOUT = "scout"


@dataclass(frozen=True)
class NpcDefinition:
    npc_id: str
    name: str
    role: NpcRole
    dialogue_id: str
    location_id: Optional[str] = None  # zone the NPC lives in (MC-006)
    position: Vec2 = Vec2()
    gives_quests: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.npc_id or not self.name or not self.dialogue_id:
            raise ValueError("npc_id, name and dialogue_id are required")

    @property
    def is_quest_giver(self) -> bool:
        return bool(self.gives_quests)


def can_interact(npc: NpcDefinition, player_position: Vec2, player_alive: bool, radius: float = INTERACT_RADIUS) -> bool:
    return player_alive and npc.position.distance_to(player_position) <= radius


@dataclass
class NpcState:
    times_talked: int = 0


@dataclass
class NpcRegistry:
    """Runtime state for every NPC the player has met (saved)."""

    states: Dict[str, NpcState] = field(default_factory=dict)

    def record_interaction(self, npc_id: str) -> NpcState:
        state = self.states.setdefault(npc_id, NpcState())
        state.times_talked += 1
        return state

    def times_talked(self, npc_id: str) -> int:
        state = self.states.get(npc_id)
        return state.times_talked if state else 0

    def to_dict(self) -> dict:
        return {npc_id: {"times_talked": s.times_talked} for npc_id, s in sorted(self.states.items())}

    @classmethod
    def from_dict(cls, data, known: Mapping[str, NpcDefinition]) -> "NpcRegistry":
        if not isinstance(data, dict):
            raise TypeError("npcs must be an object")
        registry = cls()
        for npc_id, entry in data.items():
            if npc_id not in known:
                raise ValueError(f"unknown npc {npc_id!r}")
            if not isinstance(entry, dict) or set(entry) != {"times_talked"}:
                raise ValueError(f"bad npc entry for {npc_id}")
            count = entry["times_talked"]
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"{npc_id}: bad times_talked {count!r}")
            registry.states[npc_id] = NpcState(count)
        return registry
