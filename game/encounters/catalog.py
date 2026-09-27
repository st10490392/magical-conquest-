"""Prototype encounters for the demo and tests (800x600 arena coordinates).

PROTOTYPE CONTENT - NON-FINAL.
"""

from __future__ import annotations

from typing import Dict

from game.encounters.encounter import EncounterSpec, SpawnSpec

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
        EncounterSpec("goblin_training", "Goblin training (MC-002)", (SpawnSpec("goblin", 600, 300),),
                      repeat_on_clear=True),
    )
}


def get_encounter(encounter_id: str) -> EncounterSpec:
    try:
        return ENCOUNTERS[encounter_id]
    except KeyError:
        raise ValueError(f"unknown encounter {encounter_id!r}") from None
