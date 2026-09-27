"""Prototype quests. PROTOTYPE / NON-CANON CONTENT - rewards are NON-FINAL."""

from __future__ import annotations

from typing import Dict

from game.progression.rewards import Reward
from game.quests.model import ObjectiveType as O, QuestDefinition, QuestObjective

QUESTS: Dict[str, QuestDefinition] = {
    quest.quest_id: quest
    for quest in (
        QuestDefinition(
            "proto_clear_camp",
            "Clear the Raider Camp",
            "Two raiders attack anyone passing their camp. Defeat them.",
            (QuestObjective("defeat_strikers", O.DEFEAT, "striker", 2, "Defeat raiders (Strikers)"),),
            Reward(xp=120, items=(("minor_health_potion", 2),)),
            giver_npc="proto_elder",
            turn_in_npc="proto_elder",
        ),
        QuestDefinition(
            "proto_strange_bones",
            "Strange Bones",
            "Hear what the scout found, then bring the elder three bone shards.",
            (
                QuestObjective("talk_scout", O.TALK, "proto_scout", 1, "Talk to the scout"),
                QuestObjective("collect_shards", O.COLLECT, "bone_shard", 3, "Bone shards"),
            ),
            Reward(xp=150, items=(("leather_jerkin", 1),)),
            giver_npc="proto_elder",
            turn_in_npc="proto_elder",
            prerequisites=("proto_clear_camp",),
        ),
    )
}


def validate_quests(quests: Dict[str, QuestDefinition], item_exists, npc_exists) -> None:
    for quest in quests.values():
        for prerequisite in quest.prerequisites:
            if prerequisite not in quests:
                raise ValueError(f"{quest.quest_id} requires unknown quest {prerequisite}")
        for npc in (quest.giver_npc, quest.turn_in_npc):
            if npc is not None and not npc_exists(npc):
                raise ValueError(f"{quest.quest_id} references unknown npc {npc}")
        for item_id, _ in quest.reward.items:
            if not item_exists(item_id):
                raise ValueError(f"{quest.quest_id} rewards unknown item {item_id}")
        for objective in quest.objectives:
            if objective.type is O.COLLECT and not item_exists(objective.target):
                raise ValueError(f"{quest.quest_id} collects unknown item {objective.target}")
            if objective.type is O.TALK and not npc_exists(objective.target):
                raise ValueError(f"{quest.quest_id} talks to unknown npc {objective.target}")
