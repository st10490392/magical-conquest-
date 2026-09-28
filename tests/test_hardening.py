"""MC-008 integration hardening: the awkward cases across systems."""

import json
import random
import tempfile
import unittest
from pathlib import Path

from slice_driver import DT, SliceDriver

from game.core.vector import Vec2
from game.equipment.slots import EquipSlot
from game.events.events import EnemyDefeated
from game.items.actions import give_item
from game.items.catalog import get_item
from game.npcs.catalog import get_npc
from game.persistence.save_manager import LoadStatus, SaveManager
from game.persistence.session_io import load_world_session, save_session
from game.quests.log import QuestActionStatus
from game.quests.model import QuestStatus
from game.session import PlayerInput
from game.world_session import TravelStatus, WorldSession

Q1 = "proto_clear_camp"


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.saves = SaveManager(Path(self._tmp.name) / "save.json")
        self.session = WorldSession.new()
        self.session.rng = random.Random(1)

    def tearDown(self):
        self._tmp.cleanup()

    def reload(self) -> WorldSession:
        self.assertTrue(save_session(self.saves, self.session).ok)
        result, session = load_world_session(self.saves)
        self.assertTrue(result.ok, result.error)
        return session

    def kill_strikers(self, n=1):
        for i in range(n):
            self.session.bus.publish(EnemyDefeated(f"e{i}", "striker"))

    def die(self):
        self.session.player.receive_damage(100_000)
        self.session.update(DT, PlayerInput())


class DeathTests(Base):
    def test_death_during_quest_keeps_progress_and_respawns(self):
        quests = self.session.campaign.quests
        quests.accept(Q1)
        self.session.travel("to_road")
        self.kill_strikers(1)
        self.die()
        self.assertEqual(quests.stored_status(Q1), QuestStatus.ACTIVE)  # not fail_on_death
        self.assertTrue(self.session.respawn())
        self.assertEqual(self.session.zone.zone_id, "proto_village")
        self.assertEqual(quests.objective_progress(Q1, "defeat_strikers", lambda i: 0), (1, 2))

    def test_death_closes_shop_and_conversation(self):
        self.session.shop = None
        self.session.player.position = get_npc("proto_merchant").position
        self.session.talk_to("proto_merchant")
        self.session.choose_dialogue(0)
        self.assertEqual(self.session.shop, "proto_general_store")
        self.die()
        self.assertIsNone(self.session.shop)
        self.assertIsNone(self.session.conversation)

    def test_player_dies_during_encounter_then_it_resets(self):
        self.session.travel("to_road")
        ambush = self.session.encounters[0]
        ambush.start()
        ambush.enemies[0].receive_damage(30)
        self.die()
        self.assertEqual(ambush.status.value, "failed")
        self.session.respawn()
        self.session.travel("to_road")
        fresh = self.session.encounters[0]
        self.assertEqual(fresh.status.value, "pending")
        self.assertEqual(fresh.enemies[0].stats.health, fresh.enemies[0].stats.max_health)

    def test_cannot_save_while_dead(self):
        self.die()
        outcome = save_session(self.saves, self.session)
        self.assertFalse(outcome.ok)
        self.assertIn("dead", outcome.reason)
        self.assertFalse(self.saves.exists())


class InventoryFullTests(Base):
    def fill_bag(self):
        player = self.session.player
        filler = ["iron_scrap", "bone_shard", "tattered_cloth", "old_coin"]
        i = 0
        while player.inventory.free_slots:
            give_item(player, get_item(filler[i % len(filler)]), 1)
            i += 1
            if i > 40:  # stacks fill; add distinct gear instead
                give_item(player, get_item("iron_helm"))

    def test_loot_stays_on_ground_when_full(self):
        self.session.travel("to_road")
        ambush = self.session.encounters[0]
        ambush.start()
        self.fill_bag()
        ambush.enemies[0].receive_damage(10_000)
        self.session.update(DT, PlayerInput())
        drop = self.session.ground.drops[0]
        self.session.player.position = drop.position
        self.session.update(DT, PlayerInput(interact=True))
        self.assertTrue(self.session.ground.drops)  # nothing lost

    def test_reward_waits_when_full(self):
        quests = self.session.campaign.quests
        quests.accept(Q1)
        self.kill_strikers(2)
        self.fill_bag()
        potion = get_item("minor_health_potion")  # top up potion stacks too, so the reward cannot stack in
        give_item(self.session.player, potion, self.session.player.inventory.space_for(potion))
        self.assertEqual(self.session.player.inventory.space_for(potion), 0)
        coins, xp = self.session.coins, self.session.player.xp
        self.session.player.position = get_npc("proto_elder").position
        self.session.talk_to("proto_elder")
        messages = self.session.choose_dialogue(0).messages
        self.assertIn("full", messages[0])
        self.assertEqual((self.session.coins, self.session.player.xp), (coins, xp))
        self.assertEqual(quests.status(Q1, self.session.player.inventory.count), QuestStatus.READY_TO_TURN_IN)
        self.session.end_conversation()
        self.session.player.inventory.remove(self.session.player.inventory.stacks[0][0].item_id,
                                             self.session.player.inventory.stacks[0][1])
        self.session.talk_to("proto_elder")
        self.assertTrue(self.session.choose_dialogue(0).messages[0].startswith("Quest complete"))


class ZoneTests(Base):
    def test_leaving_mid_fight_resets_and_clears_projectiles(self):
        self.session.travel("to_road")
        archer_pos = self.session.encounters[0].enemies[0].position
        goal = archer_pos + Vec2(-150, 100)  # inside the ambush trigger range
        while self.session.player.position.distance_to(goal) > 20:
            self.session.update(DT, PlayerInput(move=goal - self.session.player.position))
        for _ in range(round(1 / DT)):
            self.session.update(DT, PlayerInput())
        self.assertEqual(self.session.encounters[0].status.value, "active")
        exit_centre = self.session.zone_definition.exit("to_village").area.centre
        for _ in range(round(10 / DT)):  # run for the exit mid-fight
            if self.session.zone.zone_id != "proto_road":
                break
            self.session.update(DT, PlayerInput(move=exit_centre - self.session.player.position))
        self.assertEqual(self.session.zone.zone_id, "proto_village")
        self.assertEqual(self.session.encounters, [])
        self.session.travel("to_road")
        self.assertTrue(all(e.stats.health == e.stats.max_health for e in self.session.enemies))
        self.assertEqual(self.session.encounters[0].projectiles.projectiles, [])

    def test_travel_blocked_in_shop(self):
        self.session.player.position = get_npc("proto_merchant").position
        self.session.talk_to("proto_merchant")
        self.session.choose_dialogue(0)
        self.assertEqual(self.session.travel("to_road"), TravelStatus.IN_SHOP)
        self.session.close_shop()
        self.assertEqual(self.session.travel("to_road"), TravelStatus.OK)

    def test_trading_needs_an_open_shop(self):
        self.assertEqual(self.session.buy("minor_health_potion").status.value, "no_shop_open")
        self.assertEqual(self.session.sell("minor_health_potion").status.value, "no_shop_open")
        self.assertEqual(self.session.inspect_gear(), ())


class PersistenceIntegrationTests(Base):
    def test_save_during_active_quest(self):
        quests = self.session.campaign.quests
        quests.accept(Q1)
        self.kill_strikers(1)
        restored = self.reload()
        rq = restored.campaign.quests
        self.assertEqual(rq.objective_progress(Q1, "defeat_strikers", lambda i: 0), (1, 2))
        restored.bus.publish(EnemyDefeated("x", "striker"))  # the reloaded bus is wired
        self.assertEqual(rq.status(Q1, restored.player.inventory.count), QuestStatus.READY_TO_TURN_IN)

    def test_completed_quest_and_claimed_rewards_stay_claimed(self):
        quests = self.session.campaign.quests
        quests.accept(Q1)
        self.kill_strikers(2)
        self.session.player.position = get_npc("proto_elder").position
        self.session.talk_to("proto_elder")
        self.session.choose_dialogue(0)
        self.session.end_conversation()
        coins = self.session.coins
        restored = self.reload()
        self.assertEqual(restored.campaign.quests.accept(Q1), QuestActionStatus.ALREADY_COMPLETED)
        restored.player.position = get_npc("proto_elder").position
        restored.talk_to("proto_elder")
        self.assertNotEqual(restored.conversation.node.node_id, "q1_turn_in")
        self.assertEqual(restored.coins, coins)

    def test_load_after_equipment_change(self):
        player = self.session.player
        give_item(player, get_item("iron_helm"))
        give_item(player, get_item("leather_jerkin"))
        self.session.use_or_equip("iron_helm")
        self.session.use_or_equip("leather_jerkin")
        self.session.unequip_slot(EquipSlot.CHEST)
        restored = self.reload()
        self.assertEqual(restored.player.stats.to_dict(), player.stats.to_dict())
        restored.unequip_slot(EquipSlot.HEAD)
        self.assertEqual(restored.player.stats.durability, player.base_stats().durability)
        for _ in range(3):  # save/load cycles never inflate stats
            self.session = restored
            restored = self.reload()
        self.assertEqual(restored.player.stats.durability, player.base_stats().durability)

    def test_load_after_merchant_transaction(self):
        self.session.campaign.wallet.earn(200)  # test setup: starting funds
        self.session.player.position = get_npc("proto_smith").position
        self.session.talk_to("proto_smith")
        self.session.choose_dialogue(0)
        self.assertTrue(self.session.buy("iron_helm").ok)
        self.session.close_shop()
        restored = self.reload()
        self.assertEqual(restored.coins, 200 - 63)
        restored.player.position = get_npc("proto_smith").position
        restored.talk_to("proto_smith")
        restored.choose_dialogue(0)
        self.assertEqual(restored.buy("iron_helm").status.value, "out_of_stock")
        self.assertEqual(restored.coins, 200 - 63)

    def test_dead_boss_stays_dead_and_pays_once_across_saves(self):
        self.session.travel("to_road")
        self.session.travel("to_wilds")
        den = next(e for e in self.session.encounters if e.spec.encounter_id == "brute_den")
        den.start()
        den.enemies[0].receive_damage(100_000)
        self.session.update(DT, PlayerInput())
        coins = self.session.coins
        restored = self.reload()
        self.assertEqual([e.spec.encounter_id for e in restored.encounters], ["raider_camp"])
        self.assertEqual(restored.coins, coins)
        self.assertTrue(restored.campaign.ledger.is_claimed("encounter:proto_wilds/den"))

    def test_world_time_and_location_after_travel_and_reload(self):
        self.session.world.day_length = 5.0
        game = SliceDriver(self.session)
        game.travel_via("to_road")
        for _ in range(round(6 / DT)):
            self.session.update(DT, PlayerInput())
        restored = self.reload()
        self.assertAlmostEqual(restored.world.time, self.session.world.time)
        self.assertEqual(restored.world.day, self.session.world.day)
        self.assertEqual(restored.zone.zone_id, "proto_road")
        self.assertEqual(restored.player.position, self.session.player.position)

    def test_missing_and_corrupt_saves(self):
        result, session = load_world_session(self.saves)
        self.assertEqual((result.status, session), (LoadStatus.MISSING, None))
        for content in ("", "{", "null", "[]", "\x00\x01garbage", '{"schema_version": 6}'):
            with self.subTest(content=content):
                self.saves.path.write_text(content)
                result, session = load_world_session(self.saves)
                self.assertIn(result.status, (LoadStatus.MALFORMED, LoadStatus.UNSUPPORTED_VERSION))
                self.assertIsNone(session)
        self.saves.path.write_bytes(b"\xff\xfe\x00")
        self.assertEqual(load_world_session(self.saves)[0].status, LoadStatus.MALFORMED)

    def test_tampered_save_values(self):
        self.assertTrue(save_session(self.saves, self.session).ok)
        base = json.loads(self.saves.path.read_text())
        tampering = [
            lambda d: d["campaign"].update(wallet=-100),
            lambda d: d["player"]["inventory"].append({"item": "minor_health_potion", "qty": 999}),
            lambda d: d["campaign"]["ledger"].extend(["quest:proto_clear_camp", "quest:proto_clear_camp"]),
            lambda d: d["campaign"]["quests"].update({Q1: {"status": "completed", "counts": {}}}),
            lambda d: d["player"]["equipment"].update(main_hand="iron_helm"),
            lambda d: d["player"]["stats"].update(health=1e309),
            lambda d: d["player"].update(level=0),
            lambda d: d["player"].update(xp=-5),
            lambda d: d["campaign"].update(location={"zone": "proto_road", "x": float("nan"), "y": 1}),
        ]
        for index, tamper in enumerate(tampering):
            with self.subTest(case=index):
                data = json.loads(json.dumps(base))
                tamper(data)
                self.saves.path.write_text(json.dumps(data))
                result, session = load_world_session(self.saves)
                self.assertEqual(result.status, LoadStatus.MALFORMED)
                self.assertIsNone(session)

    def test_mc001_save_migrates_all_the_way(self):
        v1 = {
            "schema_version": 1,
            "player": {"id": "old", "name": "Veteran", "level": 2, "xp": 10, "position": {"x": 1, "y": 2},
                       "stats": {"max_health": 130}},
            "world": {"time": 42.0},
        }
        self.saves.path.write_text(json.dumps(v1))
        result, session = load_world_session(self.saves)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(session.zone.zone_id, "proto_village")
        self.assertEqual(session.player.spellbook.selected_id, "fire_bolt")
        self.assertEqual(session.coins, 0)
        self.assertEqual(session.world.time, 42.0)
        self.assertTrue(save_session(self.saves, session).ok)  # and it re-saves as current


class SaveRuleTests(Base):
    def test_save_blocked_in_conversation_and_shop(self):
        self.session.player.position = get_npc("proto_merchant").position
        self.session.talk_to("proto_merchant")
        self.assertFalse(save_session(self.saves, self.session).ok)
        self.session.choose_dialogue(0)  # opens the shop
        self.assertFalse(save_session(self.saves, self.session).ok)
        self.session.close_shop()
        self.assertTrue(save_session(self.saves, self.session).ok)


if __name__ == "__main__":
    unittest.main()
