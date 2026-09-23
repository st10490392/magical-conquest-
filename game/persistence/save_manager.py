"""Local JSON save/load for the player and world state.

Serialization of domain objects lives here so the core model does not need
to know about file formats. Every save carries ``schema_version`` so later
milestones can migrate old files instead of silently misreading them.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from game.core.stats import Stats
from game.core.vector import Vec2
from game.entities.player import Player
from game.world.world_state import WorldState

SAVE_SCHEMA_VERSION = 1


class LoadStatus(str, Enum):
    OK = "ok"
    MISSING = "missing"
    MALFORMED = "malformed"
    UNSUPPORTED_VERSION = "unsupported_version"


@dataclass(frozen=True)
class LoadResult:
    status: LoadStatus
    player: Optional[Player] = None
    world: Optional[WorldState] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is LoadStatus.OK


def player_to_dict(player: Player) -> Dict[str, Any]:
    return {
        "id": player.entity_id,
        "name": player.name,
        "level": player.level,
        "xp": player.xp,
        "position": {"x": player.position.x, "y": player.position.y},
        "stats": player.stats.to_dict(),
    }


def player_from_dict(data: Dict[str, Any]) -> Player:
    if not isinstance(data, dict):
        raise TypeError("player data must be an object")
    position = data.get("position") or {}
    return Player(
        name=data["name"],
        stats=Stats.from_dict(data["stats"]),
        level=data["level"],
        xp=data["xp"],
        entity_id=str(data["id"]),
        position=Vec2(float(position.get("x", 0.0)), float(position.get("y", 0.0))),
    )


def build_save(player: Player, world: WorldState) -> Dict[str, Any]:
    return {
        "schema_version": SAVE_SCHEMA_VERSION,
        "player": player_to_dict(player),
        "world": world.to_dict(),
    }


def parse_save(data: Any) -> LoadResult:
    if not isinstance(data, dict):
        return LoadResult(LoadStatus.MALFORMED, error="save root must be an object")
    version = data.get("schema_version")
    if version != SAVE_SCHEMA_VERSION:
        return LoadResult(
            LoadStatus.UNSUPPORTED_VERSION,
            error=f"schema_version {version!r} is not supported (expected {SAVE_SCHEMA_VERSION})",
        )
    try:
        player = player_from_dict(data["player"])
        world = WorldState.from_dict(data["world"])
    except (KeyError, TypeError, ValueError) as exc:
        return LoadResult(LoadStatus.MALFORMED, error=f"{type(exc).__name__}: {exc}")
    return LoadResult(LoadStatus.OK, player, world)


class SaveManager:
    """Reads and writes a single JSON save file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.is_file()

    def save(self, player: Player, world: WorldState) -> None:
        """Write atomically so a crash mid-save cannot corrupt the old file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(build_save(player, world), indent=2, allow_nan=False)
        fd, tmp_name = tempfile.mkstemp(dir=self.path.parent, prefix=".save-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def load(self) -> LoadResult:
        """Never raises for missing or bad files; inspect ``status`` instead."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return LoadResult(LoadStatus.MISSING, error=f"no save at {self.path}")
        except (OSError, UnicodeDecodeError) as exc:
            return LoadResult(LoadStatus.MALFORMED, error=f"could not read save: {exc}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return LoadResult(LoadStatus.MALFORMED, error=f"invalid JSON: {exc}")
        return parse_save(data)
