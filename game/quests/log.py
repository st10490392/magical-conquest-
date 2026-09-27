"""Runtime quest state for one player.

Only ACTIVE / COMPLETED / FAILED and event-driven counters are stored.
AVAILABLE, UNAVAILABLE and READY_TO_TURN_IN are derived on demand, so they
can never go stale (e.g. selling a collected item un-readies a quest).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from game.events.events import EnemyDefeated, GameEvent, LocationReached, NpcInteracted, QuestProgressed, QuestStatusChanged
from game.quests.model import ObjectiveType, QuestDefinition, QuestStatus

ItemCounter = Callable[[str], int]
_STORED = (QuestStatus.ACTIVE, QuestStatus.COMPLETED, QuestStatus.FAILED)


@dataclass
class QuestProgress:
    status: QuestStatus
    counts: Dict[str, int] = field(default_factory=dict)


class QuestActionStatus(str, Enum):
    OK = "ok"
    UNKNOWN_QUEST = "unknown_quest"
    NOT_AVAILABLE = "not_available"
    ALREADY_ACTIVE = "already_active"
    ALREADY_COMPLETED = "already_completed"
    NOT_ACTIVE = "not_active"


class QuestLog:
    def __init__(self, definitions: Mapping[str, QuestDefinition]) -> None:
        self.definitions = definitions
        self._progress: Dict[str, QuestProgress] = {}
        self._publish: Callable[[GameEvent], None] = lambda event: None

    def attach(self, publish: Callable[[GameEvent], None]) -> None:
        """Route QuestProgressed / QuestStatusChanged to an event bus."""
        self._publish = publish

    # --------------------------------------------------------------- status
    def status(self, quest_id: str, item_count: Optional[ItemCounter] = None) -> QuestStatus:
        definition = self.definitions[quest_id]
        progress = self._progress.get(quest_id)
        if progress is None or progress.status is QuestStatus.FAILED:
            if all(self.stored_status(p) is QuestStatus.COMPLETED for p in definition.prerequisites):
                return QuestStatus.AVAILABLE if progress is None else QuestStatus.FAILED
            return QuestStatus.UNAVAILABLE
        if progress.status is QuestStatus.ACTIVE and item_count is not None and self._objectives_met(definition, progress, item_count):
            return QuestStatus.READY_TO_TURN_IN
        return progress.status

    def stored_status(self, quest_id: str) -> Optional[QuestStatus]:
        progress = self._progress.get(quest_id)
        return progress.status if progress else None

    def objective_progress(self, quest_id: str, objective_id: str, item_count: ItemCounter) -> Tuple[int, int]:
        definition = self.definitions[quest_id]
        objective = definition.objective(objective_id)
        progress = self._progress.get(quest_id)
        if progress is None:
            return 0, objective.count
        if progress.status is QuestStatus.COMPLETED:
            return objective.count, objective.count
        if objective.type is ObjectiveType.COLLECT:
            return min(item_count(objective.target), objective.count), objective.count
        return progress.counts.get(objective_id, 0), objective.count

    def _objectives_met(self, definition: QuestDefinition, progress: QuestProgress, item_count: ItemCounter) -> bool:
        for objective in definition.objectives:
            if objective.type is ObjectiveType.COLLECT:
                if item_count(objective.target) < objective.count:
                    return False
            elif progress.counts.get(objective.objective_id, 0) < objective.count:
                return False
        return True

    def active(self) -> List[str]:
        return [qid for qid, p in self._progress.items() if p.status is QuestStatus.ACTIVE]

    # ------------------------------------------------------------ transitions
    def accept(self, quest_id: str) -> QuestActionStatus:
        if quest_id not in self.definitions:
            return QuestActionStatus.UNKNOWN_QUEST
        stored = self.stored_status(quest_id)
        if stored is QuestStatus.ACTIVE:
            return QuestActionStatus.ALREADY_ACTIVE
        if stored is QuestStatus.COMPLETED:
            return QuestActionStatus.ALREADY_COMPLETED
        if self.status(quest_id) not in (QuestStatus.AVAILABLE, QuestStatus.FAILED):
            return QuestActionStatus.NOT_AVAILABLE
        self._progress[quest_id] = QuestProgress(QuestStatus.ACTIVE)
        self._publish(QuestStatusChanged(quest_id, QuestStatus.ACTIVE.value))
        return QuestActionStatus.OK

    def mark_completed(self, quest_id: str) -> None:
        """Only the turn-in service calls this, after granting the reward."""
        progress = self._progress[quest_id]
        if progress.status is not QuestStatus.ACTIVE:
            raise ValueError(f"{quest_id} is not active")
        progress.status = QuestStatus.COMPLETED
        progress.counts = {}
        self._publish(QuestStatusChanged(quest_id, QuestStatus.COMPLETED.value))

    def fail(self, quest_id: str) -> QuestActionStatus:
        progress = self._progress.get(quest_id)
        if progress is None or progress.status is not QuestStatus.ACTIVE:
            return QuestActionStatus.NOT_ACTIVE
        progress.status = QuestStatus.FAILED
        progress.counts = {}
        self._publish(QuestStatusChanged(quest_id, QuestStatus.FAILED.value))
        return QuestActionStatus.OK

    def on_player_death(self) -> List[str]:
        """Fail active quests marked ``fail_on_death``; others keep progress."""
        failed = [qid for qid in self.active() if self.definitions[qid].fail_on_death]
        for quest_id in failed:
            self.fail(quest_id)
        return failed

    # ----------------------------------------------------------------- events
    def handle(self, event: GameEvent) -> None:
        if isinstance(event, EnemyDefeated):
            self._count(ObjectiveType.DEFEAT, event.archetype_id)
        elif isinstance(event, NpcInteracted):
            self._count(ObjectiveType.TALK, event.npc_id)
        elif isinstance(event, LocationReached):
            self._count(ObjectiveType.REACH, event.location_id)

    def _count(self, kind: ObjectiveType, target: str) -> None:
        for quest_id in self.active():
            progress = self._progress[quest_id]
            for objective in self.definitions[quest_id].objectives:
                if objective.type is kind and objective.target == target:
                    current = progress.counts.get(objective.objective_id, 0)
                    if current < objective.count:
                        progress.counts[objective.objective_id] = current + 1
                        self._publish(QuestProgressed(quest_id, objective.objective_id, current + 1, objective.count))

    # ------------------------------------------------------------ persistence
    def to_dict(self) -> dict:
        return {
            qid: {"status": p.status.value, "counts": dict(p.counts)}
            for qid, p in sorted(self._progress.items())
        }

    @classmethod
    def from_dict(cls, data, definitions: Mapping[str, QuestDefinition]) -> "QuestLog":
        """Validate untrusted save data against the quest definitions."""
        if not isinstance(data, dict):
            raise TypeError("quests must be an object")
        log = cls(definitions)
        for quest_id, entry in data.items():
            if quest_id not in definitions:
                raise ValueError(f"unknown quest {quest_id!r}")
            if not isinstance(entry, dict) or set(entry) != {"status", "counts"}:
                raise ValueError(f"bad quest entry for {quest_id}")
            status = QuestStatus(entry["status"])
            if status not in _STORED:
                raise ValueError(f"{quest_id}: status {status.value} cannot be stored")
            counts = entry["counts"]
            if not isinstance(counts, dict):
                raise TypeError(f"{quest_id}: counts must be an object")
            definition = definitions[quest_id]
            for objective_id, value in counts.items():
                objective = definition.objective(objective_id)
                if (not objective.event_driven or isinstance(value, bool) or not isinstance(value, int)
                        or not 0 <= value <= objective.count):
                    raise ValueError(f"{quest_id}.{objective_id}: impossible count {value!r}")
            if status is not QuestStatus.ACTIVE and counts:
                raise ValueError(f"{quest_id}: only active quests carry counts")
            log._progress[quest_id] = QuestProgress(status, dict(counts))
        for quest_id, progress in log._progress.items():
            if progress.status in (QuestStatus.ACTIVE, QuestStatus.COMPLETED):
                for prerequisite in definitions[quest_id].prerequisites:
                    if log.stored_status(prerequisite) is not QuestStatus.COMPLETED:
                        raise ValueError(f"{quest_id} is {progress.status.value} but {prerequisite} is not completed")
        return log
