"""Dialogue data. Conversations are content, not Pygame code.

A ``Dialogue`` has conditional entry points (the first whose conditions pass
is where the conversation starts) and nodes. Each node has text and player
responses; a response may be hidden by conditions, may trigger effects, and
leads to another node or ends the conversation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class ConditionKind(str, Enum):
    QUEST_STATUS = "quest_status"  # key: quest id, value: status (or "a|b")
    HAS_ITEM = "has_item"  # key: item id, value: quantity (default 1)
    FLAG = "flag"  # key: flag name
    NOT_FLAG = "not_flag"
    MIN_LEVEL = "min_level"  # value: level


@dataclass(frozen=True)
class Condition:
    kind: ConditionKind
    key: str = ""
    value: Optional[str] = None


class EffectKind(str, Enum):
    ACCEPT_QUEST = "accept_quest"
    TURN_IN_QUEST = "turn_in_quest"
    SET_FLAG = "set_flag"
    OPEN_SHOP = "open_shop"  # handled by the session/UI (merchants, MC-007)


@dataclass(frozen=True)
class Effect:
    kind: EffectKind
    key: str


@dataclass(frozen=True)
class DialogueResponse:
    text: str
    next_node: Optional[str] = None  # None ends the conversation
    conditions: Tuple[Condition, ...] = ()
    effects: Tuple[Effect, ...] = ()


@dataclass(frozen=True)
class DialogueNode:
    node_id: str
    text: str
    responses: Tuple[DialogueResponse, ...] = ()


@dataclass(frozen=True)
class DialogueEntry:
    node_id: str
    conditions: Tuple[Condition, ...] = ()


@dataclass(frozen=True)
class Dialogue:
    dialogue_id: str
    entries: Tuple[DialogueEntry, ...]
    nodes: Tuple[DialogueNode, ...]

    def __post_init__(self) -> None:
        index = {n.node_id: n for n in self.nodes}
        if len(index) != len(self.nodes):
            raise ValueError(f"{self.dialogue_id}: duplicate node ids")
        if not self.entries or self.entries[-1].conditions:
            raise ValueError(f"{self.dialogue_id}: the last entry must be unconditional (a fallback)")
        for entry in self.entries:
            if entry.node_id not in index:
                raise ValueError(f"{self.dialogue_id}: entry to unknown node {entry.node_id}")
        for node in self.nodes:
            for response in node.responses:
                if response.next_node is not None and response.next_node not in index:
                    raise ValueError(f"{self.dialogue_id}: {node.node_id} leads to unknown node {response.next_node}")

    def node(self, node_id: str) -> DialogueNode:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    @property
    def node_map(self) -> Dict[str, DialogueNode]:
        return {n.node_id: n for n in self.nodes}
