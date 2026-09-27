"""Running a dialogue against the game state through a small protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol, Tuple

from game.dialogue.model import Condition, Dialogue, DialogueNode, DialogueResponse, Effect


class DialogueContext(Protocol):
    """What dialogue may ask of, and do to, the game. Implemented by the
    campaign/session layer so dialogue stays independent of quests, items
    and UI."""

    def check(self, condition: Condition) -> bool: ...

    def apply(self, effect: Effect) -> str: ...


@dataclass(frozen=True)
class ChoiceResult:
    ok: bool
    messages: Tuple[str, ...] = ()
    ended: bool = False


class Conversation:
    def __init__(self, dialogue: Dialogue, context: DialogueContext, speaker: str = "") -> None:
        self.dialogue = dialogue
        self.context = context
        self.speaker = speaker
        self.ended = False
        start = next(e for e in dialogue.entries if all(context.check(c) for c in e.conditions))
        self.node: DialogueNode = dialogue.node(start.node_id)

    def options(self) -> List[DialogueResponse]:
        """Responses whose conditions currently pass (others are hidden)."""
        if self.ended:
            return []
        return [r for r in self.node.responses if all(self.context.check(c) for c in r.conditions)]

    def choose(self, index: int) -> ChoiceResult:
        options = self.options()
        if not 0 <= index < len(options):
            return ChoiceResult(False, ("That option is not available.",))
        response = options[index]
        messages = tuple(m for m in (self.context.apply(e) for e in response.effects) if m)
        if response.next_node is None:
            self.ended = True
        else:
            self.node = self.dialogue.node(response.next_node)
            if not self.options():  # a node without available replies ends the talk
                self.ended = True
        return ChoiceResult(True, messages, self.ended)

    def close(self) -> None:
        self.ended = True

    @property
    def text(self) -> Optional[str]:
        return None if self.ended and not self.node else self.node.text
