"""Quest definitions (static data)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from game.progression.rewards import Reward, RewardSource, reward_key


class QuestStatus(str, Enum):
    UNAVAILABLE = "unavailable"  # prerequisites not met (computed)
    AVAILABLE = "available"  # can be accepted (computed)
    ACTIVE = "active"
    READY_TO_TURN_IN = "ready_to_turn_in"  # all objectives met (computed)
    COMPLETED = "completed"  # turned in and rewarded
    FAILED = "failed"


class ObjectiveType(str, Enum):
    DEFEAT = "defeat"  # target: enemy archetype id; counted from EnemyDefeated events
    COLLECT = "collect"  # target: item id; progress = how many you *hold* now
    TALK = "talk"  # target: npc id; counted from NpcInteracted events
    REACH = "reach"  # target: location id; counted from LocationReached events


@dataclass(frozen=True)
class QuestObjective:
    objective_id: str
    type: ObjectiveType
    target: str
    count: int = 1
    description: str = ""

    def __post_init__(self) -> None:
        if not self.objective_id or not self.target:
            raise ValueError("objective_id and target are required")
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 1:
            raise ValueError("objective count must be an integer >= 1")

    @property
    def event_driven(self) -> bool:
        return self.type is not ObjectiveType.COLLECT


@dataclass(frozen=True)
class QuestDefinition:
    """PROTOTYPE / NON-CANON quest content lives in ``catalog.py``.

    ``consume_collected``: COLLECT items are handed over on turn-in (this is
    also how a "deliver to the turn-in NPC" quest is expressed).
    ``fail_on_death``: the quest fails if the player dies while it is active.
    Failed quests can be accepted again (progress restarts).
    """

    quest_id: str
    title: str
    description: str
    objectives: Tuple[QuestObjective, ...]
    reward: Reward = Reward()
    giver_npc: Optional[str] = None
    turn_in_npc: Optional[str] = None
    prerequisites: Tuple[str, ...] = ()
    consume_collected: bool = True
    fail_on_death: bool = False

    def __post_init__(self) -> None:
        if not self.quest_id or not self.title or not self.objectives:
            raise ValueError("quest_id, title and at least one objective are required")
        ids = [o.objective_id for o in self.objectives]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.quest_id}: duplicate objective ids")
        if self.quest_id in self.prerequisites:
            raise ValueError(f"{self.quest_id} cannot require itself")

    @property
    def reward_key(self) -> str:
        return reward_key(RewardSource.QUEST, self.quest_id)

    def objective(self, objective_id: str) -> QuestObjective:
        for objective in self.objectives:
            if objective.objective_id == objective_id:
                return objective
        raise KeyError(objective_id)
