"""A reusable encounter: participating enemies plus lifecycle tracking.

Later systems (dungeon rooms, village defence, monster hunts, invasions,
arena fights, world events) can build on this; none of them exist yet.
The encounter is headless and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from game.ai.coordination import AttackCoordinator
from game.ai.projectiles import ProjectileSystem
from game.ai.space import Bounds, CombatSpace
from game.core.combat import AttackResult
from game.core.entity import DeathContext, Entity
from game.core.vector import Vec2
from game.entities.archetypes import create_enemy
from game.entities.enemy import Enemy


class EncounterStatus(str, Enum):
    PENDING = "pending"  # set up, waiting for its trigger
    ACTIVE = "active"
    CLEARED = "cleared"  # every enemy is dead
    FAILED = "failed"  # the player died (or it was interrupted)


@dataclass(frozen=True)
class SpawnSpec:
    archetype_id: str
    x: float
    y: float
    level: Optional[int] = None  # None: match the player's level


@dataclass(frozen=True)
class EncounterSpec:
    encounter_id: str
    name: str
    spawns: Tuple[SpawnSpec, ...]
    # Start when the player comes this close to any enemy; None = immediately.
    trigger_range: Optional[float] = None
    max_melee_attackers: int = 1
    # When one enemy engages, the rest of the group is alerted too.
    group_alert: bool = True
    # Rebuild the encounter shortly after it is cleared (training loops).
    repeat_on_clear: bool = False
    context: DeathContext = DeathContext.OPEN_WORLD


@dataclass(frozen=True)
class CombatEvent:
    attacker: Entity
    target: Entity
    result: AttackResult
    ranged: bool = False


SEPARATION = 1.0  # enemies keep their combined half-sizes apart


class Encounter:
    def __init__(self, spec: EncounterSpec, player_level: int = 1, bounds: Optional[Bounds] = None) -> None:
        if not spec.spawns:
            raise ValueError("an encounter needs at least one enemy")
        self.spec = spec
        self.status = EncounterStatus.PENDING
        self.elapsed = 0.0
        self.failure_reason: Optional[str] = None
        self.enemies: List[Enemy] = [
            create_enemy(s.archetype_id, s.level or max(1, player_level), Vec2(s.x, s.y)) for s in spec.spawns
        ]
        self.projectiles = ProjectileSystem()
        self.coordinator = AttackCoordinator(spec.max_melee_attackers)
        self.space = CombatSpace(bounds, self.projectiles, self.coordinator, spec.context, spec.encounter_id)

    # ---------------------------------------------------------------- queries
    @property
    def living_enemies(self) -> List[Enemy]:
        return [e for e in self.enemies if e.is_alive]

    @property
    def is_over(self) -> bool:
        return self.status in (EncounterStatus.CLEARED, EncounterStatus.FAILED)

    def nearest_enemy(self, position: Vec2) -> Optional[Enemy]:
        living = self.living_enemies
        return min(living, key=lambda e: e.position.distance_to(position)) if living else None

    # -------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self.status is EncounterStatus.PENDING:
            self.status = EncounterStatus.ACTIVE

    def fail(self, reason: str) -> None:
        """Mark the encounter failed/interrupted. Applies no penalties."""
        if not self.is_over:
            self.status = EncounterStatus.FAILED
            self.failure_reason = reason
            self.projectiles.clear()

    def update(self, dt: float, player: Entity, world_time: Optional[float] = None) -> List[CombatEvent]:
        events: List[CombatEvent] = []
        if self.status is EncounterStatus.PENDING and self._triggered(player):
            self.start()
        active = self.status is EncounterStatus.ACTIVE
        target = player if active else None
        if active:
            self.elapsed += dt

        for enemy in self.enemies:
            result = enemy.update(dt, target, world_time, self.space)
            if result is not None:
                events.append(CombatEvent(enemy, player, result))
        if active and self.spec.group_alert and any(e.engaged for e in self.living_enemies):
            for enemy in self.living_enemies:
                enemy.alert()
        for hit in self.projectiles.update(dt, world_time, self.spec.context, self.spec.encounter_id):
            events.append(CombatEvent(hit.projectile.owner, hit.projectile.target, hit.result, ranged=True))
        self._separate()

        if active:
            if not player.is_alive:
                self.fail("player_died")
            elif not self.living_enemies:
                self.status = EncounterStatus.CLEARED
                self.projectiles.clear()
        return events

    def _triggered(self, player: Entity) -> bool:
        if self.spec.trigger_range is None:
            return True
        return player.is_alive and any(
            e.distance_to(player) <= self.spec.trigger_range for e in self.living_enemies
        )

    def _separate(self) -> None:
        """Push overlapping living enemies apart (tiny O(n^2); n is 2-3)."""
        living = self.living_enemies
        for i, a in enumerate(living):
            for b in living[i + 1:]:
                min_gap = (a.size + b.size) / 2 * SEPARATION
                offset = b.position - a.position
                distance = offset.length()
                if distance >= min_gap:
                    continue
                push = offset.normalized() if distance > 0 else Vec2(1.0, 0.0)
                shift = push * ((min_gap - distance) / 2)
                a.position = a.position - shift
                b.position = b.position + shift
