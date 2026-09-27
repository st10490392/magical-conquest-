"""Prototype NPCs. PROTOTYPE / NON-CANON CONTENT - not Magical Conquest
characters; names are placeholders."""

from __future__ import annotations

from typing import Dict

from game.core.vector import Vec2
from game.npcs.definitions import NpcDefinition, NpcRole

NPCS: Dict[str, NpcDefinition] = {
    npc.npc_id: npc
    for npc in (
        NpcDefinition("proto_elder", "Village Elder", NpcRole.QUEST_GIVER, "elder",
                      position=Vec2(260, 240), gives_quests=("proto_clear_camp", "proto_strange_bones")),
        NpcDefinition("proto_scout", "Scout", NpcRole.SCOUT, "scout", position=Vec2(260, 400)),
    )
}


def get_npc(npc_id: str) -> NpcDefinition:
    try:
        return NPCS[npc_id]
    except KeyError:
        raise ValueError(f"unknown npc {npc_id!r}") from None
