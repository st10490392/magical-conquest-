"""Prototype encounters for the demo and tests (800x600 arena coordinates).

PROTOTYPE CONTENT - NON-FINAL.
"""

from __future__ import annotations

from typing import Dict

from game.encounters.encounter import EncounterSpec, SpawnSpec
from game.progression.rewards import Reward

ENCOUNTERS: Dict[str, EncounterSpec] = {
    spec.encounter_id: spec
    for spec in (
        EncounterSpec("mixed_skirmish", "Mixed skirmish", (
            SpawnSpec("striker", 560, 230),
            SpawnSpec("brute", 640, 330),
            SpawnSpec("archer", 720, 460),
        )),
        EncounterSpec("striker_drill", "Striker drill", (SpawnSpec("striker", 600, 300),)),
        EncounterSpec("archer_drill", "Archer drill", (SpawnSpec("archer", 620, 300),)),
        EncounterSpec("brute_drill", "Brute drill", (SpawnSpec("brute", 600, 300),)),
        # MC-005 quest demo: the raider camp waits until you walk up to it.
        EncounterSpec("quest_camp", "Raider camp (quest demo)", (
            SpawnSpec("striker", 620, 250),
            SpawnSpec("striker", 650, 390),
        ), trigger_range=260, repeat_on_clear=True),
        # MC-006 zone encounters (coordinates inside their 800x600 zone).
        EncounterSpec("road_ambush", "Road ambush", (
            SpawnSpec("archer", 520, 140),
            SpawnSpec("striker", 560, 430),
        ), trigger_range=230),
        EncounterSpec("raider_camp", "Raider camp", (
            SpawnSpec("striker", 540, 250),
            SpawnSpec("striker", 580, 390),
        ), trigger_range=250),
        EncounterSpec("brute_den", "Brute's den", (SpawnSpec("brute", 690, 520),), trigger_range=190,
                      clear_reward=Reward(xp=60, currency=40, items=(("iron_scrap", 2),))),
        EncounterSpec("goblin_training", "Goblin training (MC-002)", (SpawnSpec("goblin", 600, 300),),
                      repeat_on_clear=True),
    )
}


def get_encounter(encounter_id: str) -> EncounterSpec:
    try:
        return ENCOUNTERS[encounter_id]
    except KeyError:
        raise ValueError(f"unknown encounter {encounter_id!r}") from None
