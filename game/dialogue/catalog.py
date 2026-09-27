"""Prototype dialogue. PROTOTYPE / NON-CANON CONTENT."""

from __future__ import annotations

from typing import Dict

from game.dialogue.model import (
    Condition as C,
    ConditionKind as K,
    Dialogue,
    DialogueEntry as Entry,
    DialogueNode as Node,
    DialogueResponse as Reply,
    Effect,
    EffectKind as E,
)

Q1, Q2, Q3 = "proto_clear_camp", "proto_strange_bones", "proto_watchtower"


def quest_is(quest_id: str, status: str) -> C:
    return C(K.QUEST_STATUS, quest_id, status)


BYE = Reply("Farewell.")

DIALOGUES: Dict[str, Dialogue] = {
    d.dialogue_id: d
    for d in (
        Dialogue(
            "elder",
            entries=(
                Entry("q1_turn_in", (quest_is(Q1, "ready_to_turn_in"),)),
                Entry("q1_waiting", (quest_is(Q1, "active"),)),
                Entry("q1_offer", (quest_is(Q1, "available|failed"),)),
                Entry("q2_turn_in", (quest_is(Q2, "ready_to_turn_in"),)),
                Entry("q2_waiting", (quest_is(Q2, "active"),)),
                Entry("q2_offer", (quest_is(Q2, "available|failed"),)),
                Entry("greet"),
            ),
            nodes=(
                Node("greet", "Welcome, traveller. All is quiet, for now.", (BYE,)),
                Node("q1_offer", "Raiders have camped east of here and strike anyone who passes. "
                                 "Will you drive two of them off?", (
                    Reply("I'll handle it.", "q1_accepted", effects=(Effect(E.ACCEPT_QUEST, Q1),)),
                    Reply("Not now."),
                )),
                Node("q1_accepted", "Thank you. Come back when it is done.", (Reply("On my way."),)),
                Node("q1_waiting", "The raiders still hold the camp.", (Reply("I'm working on it."),)),
                Node("q1_turn_in", "You drove them off! Please, take this.", (
                    Reply("Glad to help.", effects=(Effect(E.TURN_IN_QUEST, Q1),)),
                )),
                Node("q2_offer", "Our scout found strange bones by the camp. Hear the scout out, "
                                 "then bring me three bone shards.", (
                    Reply("I'll look into it.", "q2_accepted", effects=(Effect(E.ACCEPT_QUEST, Q2),)),
                    Reply("Maybe later."),
                )),
                Node("q2_accepted", "The scout keeps watch on the road east of here.", (Reply("Understood."),)),
                Node("q2_waiting", "Have you spoken with the scout and found three bone shards?", (
                    Reply("Not yet."),
                )),
                Node("q2_turn_in", "Three shards... old ones. Thank you.", (
                    Reply("Here they are.", effects=(Effect(E.TURN_IN_QUEST, Q2),)),
                )),
            ),
        ),
        Dialogue(
            "scout",
            entries=(
                Entry("bones", (quest_is(Q2, "active|ready_to_turn_in"),)),
                Entry("tower_turn_in", (quest_is(Q3, "ready_to_turn_in"),)),
                Entry("tower_waiting", (quest_is(Q3, "active"),)),
                Entry("tower_offer", (quest_is(Q3, "available|failed"),)),
                Entry("greet"),
            ),
            nodes=(
                Node("greet", "Keep your voice down. Raiders patrol the road.", (BYE,)),
                Node("bones", "The bones? They're scattered around the raider camp. "
                              "The raiders carry shards too.", (Reply("Thanks."),)),
                Node("tower_offer", "There's an old watchtower past the raider camp in the wilds. "
                                    "Get eyes on it for me?", (
                    Reply("I'll go.", "tower_accepted", effects=(Effect(E.ACCEPT_QUEST, Q3),)),
                    Reply("Not today."),
                )),
                Node("tower_accepted", "Head east through the wilds. Watch for a brute near the den.",
                     (Reply("Understood."),)),
                Node("tower_waiting", "Reached the watchtower yet?", (Reply("Not yet."),)),
                Node("tower_turn_in", "You made it there and back. Take these.", (
                    Reply("Thanks.", effects=(Effect(E.TURN_IN_QUEST, Q3),)),
                )),
            ),
        ),
    )
}


def get_dialogue(dialogue_id: str) -> Dialogue:
    try:
        return DIALOGUES[dialogue_id]
    except KeyError:
        raise ValueError(f"unknown dialogue {dialogue_id!r}") from None
