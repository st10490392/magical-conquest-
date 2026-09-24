"""Attack tokens: cap how many enemies may be winding up / striking in melee
at once, so a group takes turns instead of hitting on the same frame."""

from __future__ import annotations

from typing import Set

from game.core.entity import Entity


class AttackCoordinator:
    def __init__(self, max_melee_attackers: int = 1) -> None:
        if max_melee_attackers < 1:
            raise ValueError("max_melee_attackers must be >= 1")
        self.max_melee_attackers = max_melee_attackers
        self._holders: Set[str] = set()

    def try_acquire(self, enemy: Entity) -> bool:
        if enemy.entity_id in self._holders:
            return True
        if len(self._holders) >= self.max_melee_attackers:
            return False
        self._holders.add(enemy.entity_id)
        return True

    def release(self, enemy: Entity) -> None:
        self._holders.discard(enemy.entity_id)

    def holds(self, enemy: Entity) -> bool:
        return enemy.entity_id in self._holders

    @property
    def active(self) -> int:
        return len(self._holders)
