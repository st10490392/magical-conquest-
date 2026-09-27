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

from game.campaign import Campaign
from game.core.stats import Stats
from game.core.vector import Vec2
from game.entities.player import Player
from game.equipment.slots import EquipSlot
from game.items.catalog import get_item, item_for
from game.items.inventory import Inventory
from game.magic.attributes import parse_attributes
from game.magic.catalog import get_spell
from game.world.world_state import WorldState

# v1: MC-001 (id, name, level, xp, position, stats, world)
# v2: MC-002 adds magic_attributes, equipped_weapon, known_spells, selected_spell
# v3: MC-004 replaces equipped_weapon with equipment {slot: item_id}, adds
#     inventory [{item, qty}]; "stats" are now *base* stats (no gear bonuses)
# v4: MC-005 adds "campaign" {quests, npcs, flags, ledger}
# v5: MC-006 adds campaign.exploration {visited_zones, discovered, cleared}
#     and campaign.location {zone, x, y} (null = start of the world)
SAVE_SCHEMA_VERSION = 5


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
    campaign: Optional[Campaign] = None

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
        "stats": player.base_stats().to_dict(),
        "magic_attributes": sorted(attribute.value for attribute in player.magic_attributes),
        "equipment": {slot.value: item_for(item).item_id for slot, item in player.equipment.items().items()},
        "inventory": player.inventory.to_list(),
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
    equipment = data["equipment"]
    if not isinstance(equipment, dict):
        raise TypeError("equipment must be an object")
    for slot_name, item_id in equipment.items():
        slot = EquipSlot(slot_name)
        item = get_item(item_id)
        if item.equip_slot is not slot:
            raise ValueError(f"{item_id} cannot be equipped in {slot_name}")
        player.equip(item)
    player.inventory = Inventory.from_list(data["inventory"], get_item, player.inventory.capacity)
    for item, _ in player.inventory.stacks:
        if item.unique and player.owned_count(item.item_id) > 1:
            raise ValueError(f"unique item {item.item_id} is owned twice")
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


def migrate_v2_to_v3(data: Dict[str, Any]) -> Dict[str, Any]:
    """MC-002 saves had one weapon slot and no inventory. Weapons carried no
    stat bonuses, so their stats already are base stats."""
    player = data.get("player")
    if not isinstance(player, dict):
        raise TypeError("player data must be an object")
    player = dict(player)
    weapon_id = player.pop("equipped_weapon")
    player["equipment"] = {} if weapon_id is None else {EquipSlot.MAIN_HAND.value: weapon_id}
    player["inventory"] = []
    return {**data, "player": player, "schema_version": 3}


def migrate_v3_to_v4(data: Dict[str, Any]) -> Dict[str, Any]:
    """MC-004 saves predate quests: start with an empty campaign."""
    return {**data, "campaign": Campaign().to_dict(), "schema_version": 4}


def migrate_v4_to_v5(data: Dict[str, Any]) -> Dict[str, Any]:
    """MC-005 saves predate zones: nothing explored, start at the village."""
    campaign = data.get("campaign")
    if not isinstance(campaign, dict):
        raise TypeError("campaign must be an object")
    campaign = {**campaign, "exploration": {"visited_zones": [], "discovered": [], "cleared": []}, "location": None}
    return {**data, "campaign": campaign, "schema_version": 5}


_MIGRATIONS = {1: migrate_v1_to_v2, 2: migrate_v2_to_v3, 3: migrate_v3_to_v4, 4: migrate_v4_to_v5}


def build_save(player: Player, world: WorldState, campaign: Optional[Campaign] = None) -> Dict[str, Any]:
    return {
        "schema_version": SAVE_SCHEMA_VERSION,
        "player": player_to_dict(player),
        "world": world.to_dict(),
        "campaign": (campaign or Campaign()).to_dict(),
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
        campaign = Campaign.from_dict(data["campaign"])
    except (KeyError, TypeError, ValueError) as exc:
        return LoadResult(LoadStatus.MALFORMED, error=f"{type(exc).__name__}: {exc}")
    return LoadResult(LoadStatus.OK, player, world, campaign=campaign)


class SaveManager:
    """Reads and writes a single JSON save file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.is_file()

    def save(self, player: Player, world: WorldState, campaign: Optional[Campaign] = None) -> None:
        """Write atomically so a crash mid-save cannot corrupt the old file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(build_save(player, world, campaign), indent=2, allow_nan=False)
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
