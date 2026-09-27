"""Synchronous, deterministic event bus.

Handlers run in subscription order. Events published *while* handling
another event are queued and delivered afterwards (FIFO), so handlers never
re-enter each other and the order is always the same.
"""

from __future__ import annotations

from collections import deque
from typing import Callable, Deque, Dict, List, Type, TypeVar

from game.events.events import GameEvent

E = TypeVar("E", bound=GameEvent)
Handler = Callable[[GameEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: Dict[type, List[Handler]] = {}
        self._queue: Deque[GameEvent] = deque()
        self._dispatching = False
        self.history_limit = 50
        self.history: List[GameEvent] = []  # recent events, for debugging/tests

    def subscribe(self, event_type: Type[E], handler: Callable[[E], None]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)  # type: ignore[arg-type]

    def publish(self, event: GameEvent) -> None:
        if not isinstance(event, GameEvent):
            raise TypeError("only GameEvent instances can be published")
        self._queue.append(event)
        if self._dispatching:
            return
        self._dispatching = True
        try:
            while self._queue:
                current = self._queue.popleft()
                self.history.append(current)
                del self.history[:-self.history_limit]
                for event_type in type(current).__mro__:
                    for handler in list(self._handlers.get(event_type, ())):
                        handler(current)
        finally:
            self._dispatching = False
