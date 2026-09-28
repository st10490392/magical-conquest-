"""Saving and resuming a play session (the save/load facade the demo and
the end-to-end test use). Rules about *when* saving is allowed live on the
session (``PlaySession.save_blocker``); file format rules live in
``save_manager``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from game.persistence.save_manager import LoadResult, SaveManager
from game.play import PlaySession
from game.world_session import WorldSession


@dataclass(frozen=True)
class SaveOutcome:
    ok: bool
    reason: str = ""


def save_session(manager: SaveManager, session: PlaySession) -> SaveOutcome:
    blocker = session.save_blocker()
    if blocker:
        return SaveOutcome(False, blocker)
    try:
        manager.save(session.player, session.world, session.campaign)
    except OSError as exc:
        return SaveOutcome(False, f"could not write save: {exc}")
    return SaveOutcome(True)


def load_world_session(manager: SaveManager) -> tuple[LoadResult, Optional[WorldSession]]:
    """Resume the zone world from disk. The session is None unless the load
    succeeded; missing and malformed saves are reported, never raised."""
    result = manager.load()
    if not result.ok:
        return result, None
    return result, WorldSession(player=result.player, world=result.world, campaign=result.campaign)
