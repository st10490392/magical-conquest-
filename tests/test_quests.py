"""MC-005: events, NPCs, dialogue, quests, rewards and their persistence."""

import json
import random
import tempfile
import unittest
from pathlib import Path

from game.campaign import Campaign, CampaignContext
from game.core.vector import Vec2
from game.dialogue.catalog import DIALOGUES
from game.dialogue.conversation import Conversation
from game.dialogue.model import (
    Condition, ConditionKind, Dialogue, DialogueEntry, DialogueNode, DialogueResponse, Effect, EffectKind,
)
from game.entities.player import Player
from game.events.bus import EventBus
from game.events.events import EnemyDefeated, GameEvent, ItemObtained, LocationReached, NpcInteracted, QuestProgressed
from game.items.actions import give_item
from game.items.catalog import get_item
from game.npcs.catalog import NPCS, get_npc
from game.npcs.definitions import NpcRegistry, can_interact
from game.persistence.save_manager import LoadStatus, SaveManager
from game.progression.rewards import GrantStatus, Reward, RewardLedger, grant_reward
from game.quests.catalog import QUESTS
from game.quests.log import QuestActionStatus, QuestLog
from game.quests.model import ObjectiveType, QuestDefinition, QuestObjective, QuestStatus
from game.quests.service import TurnInStatus, turn_in
from game.session import GameSession, PlayerInput
from game.world.world_state import WorldState

Q1, Q2 = "proto_clear_camp", "proto_strange_bones"
DT = 1 / 60

TEST_QUESTS = {
    q.quest_id: q
    for q in (
        QuestDefinition("reach_tower", "Reach", "", (QuestObjective("r", ObjectiveType.REACH, "tower"),),
                        Reward(xp=10)),
        QuestDefinition("risky", "Risky", "", (QuestObjective("k", ObjectiveType.DEFEAT, "brute"),),
                        Reward(xp=10), fail_on_death=True),
        QuestDefinition("gift", "Gift", "", (QuestObjective("t", ObjectiveType.TALK, "proto_scout"),),
                        Reward(items=(("iron_helm", 1),))),
    )
}


class EventBusTests(unittest.TestCase):
    def test_dispatch_order_and_queueing(self):
        bus = EventBus()
        seen = []
        bus.subscribe(NpcInteracted, lambda e: (seen.append(("a", e.npc_id)), bus.publish(LocationReached("x"))))
        bus.subscribe(NpcInteracted, lambda e: seen.append(("b", e.npc_id)))
        bus.subscribe(LocationReached, lambda e: seen.append(("loc", e.location_id)))
        bus.subscribe(GameEvent, lambda e: seen.append(("any", type(e).__name__)))
        bus.publish(NpcInteracted("n"))
        # The nested event is delivered after all handlers of the first one.
        self.assertEqual(seen, [("a", "n"), ("b", "n"), ("any", "NpcInteracted"),
                                ("loc", "x"), ("any", "LocationReached")])
        with self.assertRaises(TypeError):
            bus.publish("not an event")


class NpcTests(unittest.TestCase):
    def test_catalog_and_interaction_range(self):
        elder = get_npc("proto_elder")
        self.assertTrue(elder.is_quest_giver)
        self.assertIn(elder.dialogue_id, DIALOGUES)
        self.assertTrue(can_interact(elder, elder.position + Vec2(30, 0), True))
        self.assertFalse(can_interact(elder, elder.position + Vec2(300, 0), True))
        self.assertFalse(can_interact(elder, elder.position, False))
        with self.assertRaises(ValueError):
            get_npc("king")

    def test_registry_round_trip_and_validation(self):
        registry = NpcRegistry()
        registry.record_interaction("proto_elder")
        registry.record_interaction("proto_elder")
        clone = NpcRegistry.from_dict(registry.to_dict(), NPCS)
        self.assertEqual(clone.times_talked("proto_elder"), 2)
        for bad in ({"ghost": {"times_talked": 1}}, {"proto_elder": {"times_talked": -1}},
                    {"proto_elder": {"times_talked": 1.5}}, {"proto_elder": 3}):
            with self.subTest(bad=bad), self.assertRaises((TypeError, ValueError)):
                NpcRegistry.from_dict(bad, NPCS)


class FakeContext:
    def __init__(self, flags=()):
        self.flags = set(flags)
        self.applied = []

    def check(self, condition):
        if condition.kind is ConditionKind.FLAG:
            return condition.key in self.flags
        if condition.kind is ConditionKind.NOT_FLAG:
            return condition.key not in self.flags
        return False

    def apply(self, effect):
        self.applied.append(effect)
        if effect.kind is EffectKind.SET_FLAG:
            self.flags.add(effect.key)
        return f"applied {effect.key}"


SAMPLE = Dialogue(
    "sample",
    entries=(DialogueEntry("vip", (Condition(ConditionKind.FLAG, "vip"),)), DialogueEntry("start")),
    nodes=(
        DialogueNode("start", "Hello.", (
            DialogueResponse("Secret", "vip", conditions=(Condition(ConditionKind.FLAG, "knows"),)),
            DialogueResponse("Join", "vip", effects=(Effect(EffectKind.SET_FLAG, "vip"),)),
            DialogueResponse("Bye"),
        )),
        DialogueNode("vip", "Welcome back.", (DialogueResponse("Thanks"),)),
    ),
)


class DialogueTests(unittest.TestCase):
    def test_transitions_effects_and_end(self):
        context = FakeContext()
        talk = Conversation(SAMPLE, context)
        self.assertEqual(talk.node.node_id, "start")
        self.assertEqual([o.text for o in talk.options()], ["Join", "Bye"])  # "Secret" hidden
        result = talk.choose(0)
        self.assertTrue(result.ok)
        self.assertEqual(result.messages, ("applied vip",))
        self.assertEqual(talk.node.node_id, "vip")
        self.assertTrue(talk.choose(0).ended)
        self.assertEqual(talk.options(), [])

    def test_conditional_entry_and_invalid_choice(self):
        talk = Conversation(SAMPLE, FakeContext(flags={"vip"}))
        self.assertEqual(talk.node.node_id, "vip")
        self.assertFalse(talk.choose(5).ok)

    def test_hidden_option_cannot_be_chosen_by_index(self):
        context = FakeContext()
        talk = Conversation(SAMPLE, context)
        talk.choose(1)  # "Bye" is index 1 because "Secret" is hidden
        self.assertTrue(talk.ended)
        self.assertEqual(context.applied, [])

    def test_validation(self):
        with self.assertRaises(ValueError):
            Dialogue("d", (DialogueEntry("x"),), (DialogueNode("y", "?"),))
        with self.assertRaises(ValueError):
            Dialogue("d", (DialogueEntry("y", (Condition(ConditionKind.FLAG, "f"),)),), (DialogueNode("y", "?"),))
        with self.assertRaises(ValueError):
            Dialogue("d", (DialogueEntry("y"),), (DialogueNode("y", "?", (DialogueResponse("go", "nowhere"),)),))

    def test_catalog_dialogues_are_valid(self):
        for dialogue in DIALOGUES.values():
            self.assertTrue(dialogue.nodes)


def make_log(definitions=QUESTS):
    log = QuestLog(definitions)
    events = []
    log.attach(events.append)
    return log, events


class QuestLogTests(unittest.TestCase):
    def test_availability_and_prerequisites(self):
        log, _ = make_log()
        self.assertEqual(log.status(Q1), QuestStatus.AVAILABLE)
        self.assertEqual(log.status(Q2), QuestStatus.UNAVAILABLE)
        self.assertEqual(log.accept(Q2), QuestActionStatus.NOT_AVAILABLE)
        self.assertEqual(log.accept("nope"), QuestActionStatus.UNKNOWN_QUEST)

    def test_accept_and_kill_progress(self):
        log, events = make_log()
        self.assertEqual(log.accept(Q1), QuestActionStatus.OK)
        self.assertEqual(log.accept(Q1), QuestActionStatus.ALREADY_ACTIVE)
        log.handle(EnemyDefeated("e1", "archer"))  # wrong target
        log.handle(EnemyDefeated("e2", "striker"))
        self.assertEqual(log.objective_progress(Q1, "defeat_strikers", lambda i: 0), (1, 2))
        self.assertEqual(log.status(Q1, lambda i: 0), QuestStatus.ACTIVE)
        log.handle(EnemyDefeated("e3", "striker"))
        log.handle(EnemyDefeated("e4", "striker"))  # capped
        self.assertEqual(log.objective_progress(Q1, "defeat_strikers", lambda i: 0), (2, 2))
        self.assertEqual(log.status(Q1, lambda i: 0), QuestStatus.READY_TO_TURN_IN)
        self.assertEqual([e.count for e in events if isinstance(e, QuestProgressed)], [1, 2])

    def test_events_before_accepting_do_not_count(self):
        log, _ = make_log()
        log.handle(EnemyDefeated("e", "striker"))
        log.accept(Q1)
        self.assertEqual(log.objective_progress(Q1, "defeat_strikers", lambda i: 0), (0, 2))

    def test_collect_and_talk_objectives(self):
        log, _ = make_log()
        log.accept(Q1)
        log.handle(EnemyDefeated("a", "striker"))
        log.handle(EnemyDefeated("b", "striker"))
        log.mark_completed(Q1)
        self.assertEqual(log.accept(Q2), QuestActionStatus.OK)
        held = {"bone_shard": 3}
        count = lambda item_id: held.get(item_id, 0)  # noqa: E731
        self.assertEqual(log.status(Q2, count), QuestStatus.ACTIVE)  # has not talked yet
        log.handle(NpcInteracted("proto_scout"))
        self.assertEqual(log.status(Q2, count), QuestStatus.READY_TO_TURN_IN)
        held["bone_shard"] = 2  # sold one: no longer ready
        self.assertEqual(log.status(Q2, count), QuestStatus.ACTIVE)
        self.assertEqual(log.objective_progress(Q2, "collect_shards", count), (2, 3))

    def test_reach_objective(self):
        log, _ = make_log(TEST_QUESTS)
        log.accept("reach_tower")
        log.handle(LocationReached("elsewhere"))
        self.assertEqual(log.status("reach_tower", lambda i: 0), QuestStatus.ACTIVE)
        log.handle(LocationReached("tower"))
        self.assertEqual(log.status("reach_tower", lambda i: 0), QuestStatus.READY_TO_TURN_IN)

    def test_failure_on_death_and_retry(self):
        log, _ = make_log(TEST_QUESTS)
        log.accept("risky")
        log.accept("reach_tower")
        self.assertEqual(log.on_player_death(), ["risky"])
        self.assertEqual(log.status("risky"), QuestStatus.FAILED)
        self.assertEqual(log.stored_status("reach_tower"), QuestStatus.ACTIVE)  # unaffected
        self.assertEqual(log.accept("risky"), QuestActionStatus.OK)  # can retry
        self.assertEqual(log.fail("gift"), QuestActionStatus.NOT_ACTIVE)

    def test_definition_validation(self):
        with self.assertRaises(ValueError):
            QuestObjective("x", ObjectiveType.DEFEAT, "brute", 0)
        with self.assertRaises(ValueError):
            QuestDefinition("q", "Q", "", ())
        with self.assertRaises(ValueError):
            QuestDefinition("q", "Q", "", (QuestObjective("a", ObjectiveType.TALK, "x"),) * 2)
        with self.assertRaises(ValueError):
            QuestDefinition("q", "Q", "", (QuestObjective("a", ObjectiveType.TALK, "x"),), prerequisites=("q",))

    def test_persistence_validation(self):
        log, _ = make_log()
        log.accept(Q1)
        log.handle(EnemyDefeated("a", "striker"))
        clone = QuestLog.from_dict(log.to_dict(), QUESTS)
        self.assertEqual(clone.objective_progress(Q1, "defeat_strikers", lambda i: 0), (1, 2))
        bad = [
            {"ghost": {"status": "active", "counts": {}}},
            {Q1: {"status": "ready_to_turn_in", "counts": {}}},
            {Q1: {"status": "active", "counts": {"defeat_strikers": 99}}},
            {Q1: {"status": "active", "counts": {"defeat_strikers": -1}}},
            {Q1: {"status": "active", "counts": {"nope": 1}}},
            {Q1: {"status": "completed", "counts": {"defeat_strikers": 1}}},
            {Q2: {"status": "active", "counts": {"collect_shards": 2}}},  # collect is not stored
            {Q2: {"status": "active", "counts": {}}},  # prerequisite not completed
            {Q1: "active"},
        ]
        for data in bad:
            with self.subTest(data=data), self.assertRaises((TypeError, ValueError, KeyError)):
                QuestLog.from_dict(data, QUESTS)


class RewardTests(unittest.TestCase):
    def test_reward_once(self):
        player = Player("P")
        ledger = RewardLedger()
        reward = Reward(xp=50, items=(("minor_health_potion", 2),))
        self.assertTrue(grant_reward(player, reward, "k", ledger, get_item).ok)
        again = grant_reward(player, reward, "k", ledger, get_item)
        self.assertEqual(again.status, GrantStatus.ALREADY_CLAIMED)
        self.assertEqual(player.xp, 50)
        self.assertEqual(player.inventory.count("minor_health_potion"), 2)

    def test_full_inventory_grants_nothing(self):
        player = Player("P", inventory_capacity=1)
        give_item(player, get_item("iron_scrap"), 20)
        ledger = RewardLedger()
        result = grant_reward(player, Reward(xp=50, items=(("iron_helm", 1),)), "k", ledger, get_item)
        self.assertEqual(result.status, GrantStatus.INVENTORY_FULL)
        self.assertEqual(player.xp, 0)
        self.assertFalse(ledger.is_claimed("k"))

    def test_currency_needs_a_wallet(self):
        with self.assertRaises(ValueError):
            grant_reward(Player("P"), Reward(currency=5), "k", RewardLedger(), get_item)
        with self.assertRaises(ValueError):
            Reward(xp=-1)


class TurnInTests(unittest.TestCase):
    # MC-007: quest rewards now pay currency, so turn_in needs the campaign
    # wallet (paying coins without a wallet is refused rather than dropped).
    def ready_q2(self, capacity=20):
        player = Player("P", inventory_capacity=capacity)
        campaign = Campaign()
        campaign.quests.accept(Q1)
        for i in range(2):
            campaign.quests.handle(EnemyDefeated(str(i), "striker"))
        self.assertTrue(turn_in(Q1, player, campaign.quests, campaign.ledger, get_item, wallet=campaign.wallet).ok)
        campaign.quests.accept(Q2)
        campaign.quests.handle(NpcInteracted("proto_scout"))
        give_item(player, get_item("bone_shard"), 4)
        return player, campaign

    def test_turn_in_consumes_items_and_rewards_once(self):
        player, campaign = self.ready_q2()
        xp_before = player.xp
        result = turn_in(Q2, player, campaign.quests, campaign.ledger, get_item, npc_id="proto_elder", wallet=campaign.wallet)
        self.assertTrue(result.ok)
        self.assertEqual(player.inventory.count("bone_shard"), 1)
        self.assertEqual(player.inventory.count("leather_jerkin"), 1)
        self.assertEqual(campaign.quests.status(Q2), QuestStatus.COMPLETED)
        self.assertGreater(player.xp + player.level * 1000, xp_before)
        again = turn_in(Q2, player, campaign.quests, campaign.ledger, get_item, npc_id="proto_elder", wallet=campaign.wallet)
        self.assertEqual(again.status, TurnInStatus.ALREADY_COMPLETED)
        self.assertEqual(player.inventory.count("leather_jerkin"), 1)
        self.assertEqual(campaign.quests.accept(Q2), QuestActionStatus.ALREADY_COMPLETED)

    def test_wrong_npc_and_not_ready(self):
        player, campaign = self.ready_q2()
        self.assertEqual(turn_in(Q2, player, campaign.quests, campaign.ledger, get_item, npc_id="proto_scout", wallet=campaign.wallet).status,
                         TurnInStatus.WRONG_NPC)
        player.inventory.remove("bone_shard", 2)
        self.assertEqual(turn_in(Q2, player, campaign.quests, campaign.ledger, get_item, wallet=campaign.wallet).status, TurnInStatus.NOT_READY)

    def test_inventory_full_changes_nothing(self):
        player, campaign = self.ready_q2(capacity=2)
        # Slot 1: the Q1 reward potions, slot 2: 4 shards. Handing over 3 of
        # the 4 shards frees no slot, so the jerkin cannot fit.
        self.assertEqual(player.inventory.free_slots, 0)
        result = turn_in(Q2, player, campaign.quests, campaign.ledger, get_item, wallet=campaign.wallet)
        self.assertEqual(result.status, TurnInStatus.INVENTORY_FULL)
        self.assertEqual(player.inventory.count("bone_shard"), 4)
        self.assertEqual(campaign.quests.status(Q2, player.inventory.count), QuestStatus.READY_TO_TURN_IN)
        player.inventory.remove("minor_health_potion", 2)
        self.assertTrue(turn_in(Q2, player, campaign.quests, campaign.ledger, get_item, wallet=campaign.wallet).ok)

    def test_ledger_blocks_turn_in_even_if_log_disagrees(self):
        player, campaign = self.ready_q2()
        campaign.ledger._record(QUESTS[Q2].reward_key)
        self.assertEqual(turn_in(Q2, player, campaign.quests, campaign.ledger, get_item, wallet=campaign.wallet).status,
                         TurnInStatus.ALREADY_COMPLETED)


class CampaignPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "save.json"
        self.manager = SaveManager(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip(self):
        campaign = Campaign()
        campaign.quests.accept(Q1)
        campaign.quests.handle(EnemyDefeated("a", "striker"))
        campaign.npcs.record_interaction("proto_elder")
        campaign.set_flag("met_elder")
        self.manager.save(Player("P"), WorldState(), campaign)
        loaded = self.manager.load()
        self.assertEqual(loaded.status, LoadStatus.OK, loaded.error)
        self.assertEqual(loaded.campaign.to_dict(), campaign.to_dict())

    def test_inconsistent_or_malformed_campaign(self):
        self.manager.save(Player("P"), WorldState(), Campaign())
        base = json.loads(self.path.read_text())
        patches = [
            {"ledger": ["quest:proto_clear_camp"]},  # claimed but not completed
            {"quests": {Q1: {"status": "completed", "counts": {}}}},  # completed but unclaimed
            {"ledger": ["quest:ghost"]},
            {"ledger": ["x", "x"]},
            {"flags": ["Bad Flag!"]},
            {"flags": "vip"},
            {"npcs": {"ghost": {"times_talked": 1}}},
        ]
        for patch in patches:
            with self.subTest(patch=patch):
                data = json.loads(json.dumps(base))
                data["campaign"].update(patch)
                self.path.write_text(json.dumps(data))
                self.assertEqual(self.manager.load().status, LoadStatus.MALFORMED)

    def test_v3_migrates_to_empty_campaign(self):
        self.manager.save(Player("P"), WorldState())
        data = json.loads(self.path.read_text())
        data["schema_version"] = 3
        del data["campaign"]
        self.path.write_text(json.dumps(data))
        loaded = self.manager.load()
        self.assertEqual(loaded.status, LoadStatus.OK, loaded.error)
        self.assertEqual(loaded.campaign.quests.active(), [])


class QuestSimulationTests(unittest.TestCase):
    """The whole MC-005 loop through public session APIs, headless."""

    def fight_until(self, session, predicate, seconds=120):
        import sys
        sys.path.insert(0, "tests")
        from test_encounters import fighting_player_input
        for _ in range(round(seconds / DT)):
            session.update(DT, fighting_player_input(session))
            if predicate():
                return
        self.fail("condition not reached")

    def walk_to(self, session, point):
        for _ in range(600):
            if session.player.position.distance_to(point) < 40:
                return
            session.update(DT, PlayerInput(move=point - session.player.position))
        self.fail("could not reach point")

    def talk(self, session, npc_id):
        self.walk_to(session, get_npc(npc_id).position)
        session.update(DT, PlayerInput(interact=True))
        self.assertIsNotNone(session.conversation)
        self.assertEqual(session.talking_to.npc_id, npc_id)

    def test_full_quest_chain(self):
        session = GameSession.new(encounter_id="quest_camp")
        session.rng = random.Random(3)
        quests = session.campaign.quests
        count = session.player.inventory.count

        self.talk(session, "proto_elder")
        self.assertEqual(session.choose_dialogue(0).messages, ("Quest accepted: Clear the Raider Camp",))
        session.end_conversation()
        self.fight_until(session, lambda: quests.status(Q1, count) is QuestStatus.READY_TO_TURN_IN)

        # Collect the raiders' loot (bone shards) before going back.
        while session.ground.drops:
            self.walk_to(session, session.ground.drops[0].position)
            session.update(DT, PlayerInput(interact=True))
        xp_level = (session.player.level, session.player.xp)
        self.talk(session, "proto_elder")
        result = session.choose_dialogue(0)
        self.assertIn("Quest complete: Clear the Raider Camp (+120 XP)", result.messages)
        self.assertGreater((session.player.level, session.player.xp), xp_level)
        session.end_conversation()

        # Chain: Q2 unlocked by Q1.
        self.talk(session, "proto_elder")
        self.assertIn("Strange Bones", session.choose_dialogue(0).messages[0])
        session.end_conversation()
        self.talk(session, "proto_scout")  # TALK objective
        session.end_conversation()
        self.fight_until(session, lambda: count("bone_shard") >= 3 or session.ground.drops, 60)
        while count("bone_shard") < 3:
            if session.ground.drops:
                self.walk_to(session, session.ground.drops[0].position)
                session.update(DT, PlayerInput(interact=True))
            else:
                self.fight_until(session, lambda: bool(session.ground.drops), 60)
        self.assertEqual(quests.status(Q2, count), QuestStatus.READY_TO_TURN_IN)
        self.talk(session, "proto_elder")
        self.assertTrue(any(m.startswith("Quest complete: Strange Bones") for m in session.choose_dialogue(0).messages))
        session.end_conversation()
        self.assertEqual(session.player.inventory.count("leather_jerkin"), 1)

        # Talking again cannot re-award anything.
        self.talk(session, "proto_elder")
        self.assertEqual(session.conversation.node.node_id, "greet")
        self.assertEqual(session.campaign.ledger.claimed, ("quest:proto_clear_camp", "quest:proto_strange_bones"))

    def test_item_events_published(self):
        session = GameSession.new(encounter_id="brute_drill")
        seen = []
        session.bus.subscribe(ItemObtained, seen.append)
        session.enemies[0].receive_damage(10_000)
        session.update(DT, PlayerInput())
        session.player.position = session.ground.drops[0].position
        session.update(DT, PlayerInput(interact=True))
        self.assertTrue(seen and all(e.source == "loot" for e in seen))

    def test_death_fails_fail_on_death_quests_only(self):
        session = GameSession.new(encounter_id="quest_camp")
        session.campaign.quests.accept(Q1)
        session.player.receive_damage(10_000)
        session.update(DT, PlayerInput())
        self.assertEqual(session.campaign.quests.stored_status(Q1), QuestStatus.ACTIVE)
        self.assertIsNotNone(session.last_player_death)

    def test_dialogue_context_turn_in_inventory_full_message(self):
        player = Player("P", inventory_capacity=1)
        campaign = Campaign()
        campaign.quests.accept(Q1)
        for i in range(2):
            campaign.quests.handle(EnemyDefeated(str(i), "striker"))
        give_item(player, get_item("iron_scrap"), 20)
        context = CampaignContext(player, campaign, "proto_elder")
        message = context.apply(Effect(EffectKind.TURN_IN_QUEST, Q1))
        self.assertIn("full", message)
        self.assertFalse(campaign.ledger.is_claimed(QUESTS[Q1].reward_key))


if __name__ == "__main__":
    unittest.main()
