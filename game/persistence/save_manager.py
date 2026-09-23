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
from game.equipment.catalog import get_weapon
from game.magic.attributes import parse_attributes
from game.magic.catalog import get_spell
from game.world.world_state import WorldState

# v1: MC-001 (id, name, level, xp, position, stats, world)
# v2: MC-002 adds magic_attributes, equipped_weapon, known_spells, selected_spell
SAVE_SCHEMA_VERSION = 2


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
        "magic_attributes": sorted(attribute.value for attribute in player.magic_attributes),
        "equipped_weapon": player.weapon.weapon_id if player.weapon else None,
        "known_spells": [spell.spell_id for spell in player.spellbook.spells],
        "selected_spell": player.spellbook.selected_id,
    }


def player_from_dict(data: Dict[str, Any]) -> Player:
    if not isinstance(data, dict):
        raise TypeError("player data must be an object")
    position = data.get("position") or {}
    player = Player(
        name=data["name"],
        stats=Stats.from_dict(data["stats"]),
        level=data["level"],
        xp=data["xp"],
        entity_id=str(data["id"]),
        position=Vec2(float(position.get("x", 0.0)), float(position.get("y", 0.0))),
        magic_attributes=parse_attributes(data["magic_attributes"]),
    )
    weapon_id = data["equipped_weapon"]
    if weapon_id is not None:
        player.equip(get_weapon(weapon_id))
    known = data["known_spells"]
    if not isinstance(known, list):
        raise TypeError("known_spells must be a list")
    for spell_id in known:
        player.learn_spell(get_spell(spell_id))
    selected = data["selected_spell"]
    if selected is not None and not player.spellbook.select(selected):
        raise ValueError(f"selected_spell {selected!r} is not a known spell")
    return player


def migrate_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """MC-001 saves predate magic and equipment.

    An MC-001 character could always cast Fire Bolt and fought unarmed, so
    the migrated character keeps exactly that: the Fire attribute, Fire Bolt
    known and selected, and no weapon.
    """
    player = data.get("player")
    if not isinstance(player, dict):
        raise TypeError("player data must be an object")
    migrated = dict(data)
    migrated["player"] = {
        **player,
        "magic_attributes": ["fire"],
        "equipped_weapon": None,
        "known_spells": ["fire_bolt"],
        "selected_spell": "fire_bolt",
    }
    migrated["schema_version"] = 2
    return migrated


_MIGRATIONS = {1: migrate_v1_to_v2}


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
    known_version = isinstance(version, int) and not isinstance(version, bool)
    if not known_version or (version != SAVE_SCHEMA_VERSION and version not in _MIGRATIONS):
        return LoadResult(
            LoadStatus.UNSUPPORTED_VERSION,
            error=f"schema_version {version!r} is not supported (expected {SAVE_SCHEMA_VERSION})",
        )
    try:
        while data["schema_version"] in _MIGRATIONS:
            data = _MIGRATIONS[data["schema_version"]](data)
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
