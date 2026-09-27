"""Quest turn-in: the one place where a quest's reward is granted."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from game.entities.player import Player
from game.items.definitions import ItemDefinition
from game.progression.rewards import CurrencyAccount, GrantStatus, Reward, RewardLedger, grant_reward
from game.quests.log import QuestLog
from game.quests.model import ObjectiveType, QuestStatus


class TurnInStatus(str, Enum):
    OK = "ok"
    UNKNOWN_QUEST = "unknown_quest"
    NOT_READY = "not_ready"
    ALREADY_COMPLETED = "already_completed"
    WRONG_NPC = "wrong_npc"
    INVENTORY_FULL = "inventory_full"
    DEAD = "dead"


@dataclass(frozen=True)
class TurnInResult:
    status: TurnInStatus
    quest_id: str
    reward: Optional[Reward] = None
    levels_gained: int = 0

    @property
    def ok(self) -> bool:
        return self.status is TurnInStatus.OK


def turn_in(
    quest_id: str,
    player: Player,
    quests: QuestLog,
    ledger: RewardLedger,
    lookup: Callable[[str], ItemDefinition],
    npc_id: Optional[str] = None,
    wallet: Optional[CurrencyAccount] = None,
    on_item: Optional[Callable[[str, int], None]] = None,
) -> TurnInResult:
    """Hand in collected items and grant the reward, atomically and once.

    If the reward does not fit, nothing changes: collected items stay in the
    inventory and the quest stays ready.
    """
    if quest_id not in quests.definitions:
        return TurnInResult(TurnInStatus.UNKNOWN_QUEST, quest_id)
    definition = quests.definitions[quest_id]
    if quests.stored_status(quest_id) is QuestStatus.COMPLETED or ledger.is_claimed(definition.reward_key):
        return TurnInResult(TurnInStatus.ALREADY_COMPLETED, quest_id)
    if npc_id is not None and definition.turn_in_npc is not None and npc_id != definition.turn_in_npc:
        return TurnInResult(TurnInStatus.WRONG_NPC, quest_id)
    if quests.status(quest_id, player.inventory.count) is not QuestStatus.READY_TO_TURN_IN:
        return TurnInResult(TurnInStatus.NOT_READY, quest_id)

    handed_over = [
        (o.target, o.count) for o in definition.objectives
        if o.type is ObjectiveType.COLLECT and definition.consume_collected
    ]
    # Check the reward fits *after* the hand-over, then do both or neither.
    trial = player.inventory.copy()
    for item_id, count in handed_over:
        trial.remove(item_id, count)
    items = [(lookup(i), q) for i, q in definition.reward.items]
    if not trial.can_add_all(items):
        return TurnInResult(TurnInStatus.INVENTORY_FULL, quest_id, definition.reward)
    if not player.is_alive:
        return TurnInResult(TurnInStatus.DEAD, quest_id)
    for item_id, count in handed_over:
        player.inventory.remove(item_id, count)
    grant = grant_reward(player, definition.reward, definition.reward_key, ledger, lookup, wallet, on_item)
    if grant.status is not GrantStatus.OK:  # cannot happen after the checks above
        raise RuntimeError(f"reward grant failed after validation: {grant.status}")
    quests.mark_completed(quest_id)
    return TurnInResult(TurnInStatus.OK, quest_id, definition.reward, grant.levels_gained)
