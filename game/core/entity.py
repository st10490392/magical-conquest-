"""Base entity shared by players, monsters and (later) NPCs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Iterable, Optional, Set

from game.core.defense import DefenseAction, DefenseConfig, DefensiveState, GuardProfile
from game.core.stats import Stats
from game.core.vector import Vec2

if TYPE_CHECKING:
    from game.magic.attributes import MagicAttribute


class DeathContext(str, Enum):
    """Where/how a death happened. Penalty rules (XP loss, loot loss, event
    elimination, respawn) will key off this in later milestones; combat
    itself never applies penalties."""

    OPEN_WORLD = "open_world"
    PVP = "pvp"
    DUNGEON = "dungeon"
    WORLD_EVENT = "world_event"


@dataclass(frozen=True)
class DeathRecord:
    """What happened when an entity died.

    Later milestones (dungeon/PvP XP loss, loot, respawn rules) will consume
    this record; for now it is only created. ``context_id`` can identify the
    dungeon or world event involved.
    """

    entity_id: str
    killer_id: Optional[str]
    cause: str
    world_time: Optional[float] = None
    context: DeathContext = DeathContext.OPEN_WORLD
    context_id: Optional[str] = None


def new_entity_id() -> str:
    return uuid.uuid4().hex


class Entity:
    """Anything with a name, a level and a stat block that can live and die."""

    # True for player characters; used to recognise PvP deaths.
    is_player_character = False

    def __init__(
        self,
        name: str,
        stats: Optional[Stats] = None,
        level: int = 1,
        entity_id: Optional[str] = None,
        position: Optional[Vec2] = None,
        size: float = 40.0,
        magic_attributes: Iterable["MagicAttribute"] = (),
        defense_config: Optional[DefenseConfig] = None,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("entity name must be a non-empty string")
        if isinstance(level, bool) or not isinstance(level, int) or level < 1:
            raise ValueError(f"level must be an integer >= 1, got {level!r}")
        self.entity_id = entity_id or new_entity_id()
        self.name = name
        self.level = level
        self.stats = stats if stats is not None else Stats()
        self.position = position if position is not None else Vec2()
        self.size = size
        self.magic_attributes: Set["MagicAttribute"] = set(magic_attributes)
        self.defense = DefensiveState(defense_config) if defense_config else DefensiveState()
        self.death: Optional[DeathRecord] = None
        if not self.stats.is_alive:
            self.death = DeathRecord(self.entity_id, None, "loaded_dead")

    @property
    def is_alive(self) -> bool:
        return self.death is None and self.stats.is_alive

    def has_attribute(self, attribute: "MagicAttribute") -> bool:
        return attribute in self.magic_attributes

    def grant_attribute(self, attribute: "MagicAttribute") -> None:
        self.magic_attributes.add(attribute)

    def revoke_attribute(self, attribute: "MagicAttribute") -> None:
        self.magic_attributes.discard(attribute)

    # ------------------------------------------------------------- defense
    def guard_profile(self) -> GuardProfile:
        """Defensive capabilities; subclasses derive this from equipment."""
        return GuardProfile()

    def start_block(self) -> DefenseAction:
        return self.defense.start_block(self.stats, self.guard_profile())

    def stop_block(self) -> None:
        self.defense.stop_block()

    def parry(self) -> DefenseAction:
        return self.defense.start_parry(self.stats, self.guard_profile())

    def dodge(self) -> DefenseAction:
        return self.defense.start_dodge(self.stats)

    # -------------------------------------------------------------- damage
    def receive_damage(
        self,
        amount: float,
        source_id: Optional[str] = None,
        cause: str = "damage",
        world_time: Optional[float] = None,
        context: DeathContext = DeathContext.OPEN_WORLD,
        context_id: Optional[str] = None,
    ) -> float:
        """Apply already-mitigated damage. Returns the damage actually applied.

        Dead entities ignore further damage. Reaching zero health records a
        ``DeathRecord`` exactly once.
        """
        if not self.is_alive:
            return 0.0
        applied = self.stats.take_damage(amount)
        if not self.stats.is_alive:
            self.death = DeathRecord(self.entity_id, source_id, cause, world_time, context, context_id)
            self.defense.reset()
        return applied

    def distance_to(self, other: "Entity") -> float:
        return self.position.distance_to(other.position)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(name={self.name!r}, level={self.level}, "
            f"hp={self.stats.health:.0f}/{self.stats.max_health:.0f})"
        )
