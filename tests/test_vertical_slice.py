"""MC-008: the connected vertical slice, end to end and headless.

new player -> talk to the elder -> accept the quest -> travel -> fight
(MC-003 AI, weapons, parries) -> loot -> quest progress -> return -> turn in
-> reward -> merchant (sell + buy) -> equip -> save -> reload -> verify.

Driven only through public APIs (see ``slice_driver.py``).
"""

import json
import random
import tempfile
import unittest
from pathlib import Path

from slice_driver import SliceDriver

from game.equipment.slots import EquipSlot
from game.persistence.save_manager import SAVE_SCHEMA_VERSION, SaveManager
from game.persistence.session_io import load_world_session, save_session
from game.quests.model import QuestStatus
from game.world_session import WorldSession

Q1 = "proto_clear_camp"


class VerticalSliceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.saves = SaveManager(Path(self._tmp.name) / "slice.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_full_slice(self):
        session = WorldSession.new()
        session.rng = random.Random(8)
        game = SliceDriver(session)
        player, campaign, quests = session.player, session.campaign, session.campaign.quests
        count = player.inventory.count

        # 1-6: settlement, NPC, dialogue, accept the quest.
        self.assertEqual(session.zone.zone_id, "proto_village")
        self.assertEqual(session.npc_marker(session.npcs[0]), "!")
        game.talk("proto_elder")
        self.assertIn("Raiders", session.conversation.node.text)
        self.assertEqual(game.choose("I'll handle it").messages, ("Quest accepted: Clear the Raider Camp",))
        game.leave_conversation()
        self.assertEqual(quests.status(Q1), QuestStatus.ACTIVE)

        # 7-13: leave, travel through the road (ambush) into the wilds, fight.
        game.travel_via("to_road")
        self.assertEqual(session.zone.zone_id, "proto_road")
        game.walk_to(session.zone_definition.spawn("from_wilds"))  # the ambush engages on the way
        game.loot_everything()
        game.travel_via("to_wilds")
        camp = next(e for e in session.encounters if e.spec.encounter_id == "raider_camp")
        game.walk_to(camp.enemies[0].position, radius=200)
        game.clear_threats()
        self.assertTrue(all(not e.is_alive for e in camp.enemies))

        # 14-15: XP, quest progress and loot.
        self.assertGreater((player.level, player.xp), (1, 0))
        self.assertEqual(quests.status(Q1, count), QuestStatus.READY_TO_TURN_IN)
        game.loot_everything()
        self.assertGreater(count("bone_shard"), 0)
        self.assertGreater(session.coins, 0)

        # 16-18: return and turn in.
        game.travel_via("to_road")
        game.travel_via("to_village")
        self.assertEqual(session.npc_marker(session.npcs[0]), "?")
        game.talk("proto_elder")
        coins_before, potions_before = session.coins, count("minor_health_potion")
        messages = game.choose("Glad to help").messages
        game.leave_conversation()
        self.assertEqual(messages, ("Quest complete: Clear the Raider Camp (+120 XP)",))
        self.assertEqual(quests.status(Q1), QuestStatus.COMPLETED)
        self.assertEqual(session.coins, coins_before + 30)
        self.assertEqual(count("minor_health_potion"), potions_before + 2)

        # 19-21: sell unwanted loot to the smith, buy boots from the shop, equip.
        game.talk("proto_smith")
        game.choose("Show me your wares")
        self.assertEqual(session.shop, "proto_smithy")
        shards, coins = count("bone_shard"), session.coins
        self.assertTrue(session.sell("bone_shard", shards).ok)
        self.assertGreater(session.coins, coins)
        session.close_shop()
        game.talk("proto_merchant")
        game.choose("Let's trade")
        coins = session.coins
        self.assertTrue(session.buy("traveler_boots").ok)
        self.assertEqual(session.coins, coins - 15)
        session.close_shop()
        speed = player.stats.speed
        self.assertTrue(session.use_or_equip("traveler_boots").ok)
        self.assertEqual(player.stats.speed, speed + 15)

        # 22: save.
        self.assertTrue(save_session(self.saves, session).ok)
        snapshot = {
            "level": player.level, "xp": player.xp, "coins": session.coins,
            "stats": player.stats.to_dict(), "inventory": player.inventory.stacks,
            "equipment": {s: i.item_id for s, i in player.equipment.items().items()},
            "quests": quests.to_dict(), "ledger": campaign.ledger.claimed,
            "zone": session.zone.zone_id, "position": player.position,
            "time": session.world.time, "stock": campaign.merchant("proto_general_store").state.to_dict(),
        }
        self.assertEqual(json.loads(self.saves.path.read_text())["schema_version"], SAVE_SCHEMA_VERSION)

        # 23-24: "quit" (drop the session) and reload; the state is intact.
        del session, game
        result, restored = load_world_session(self.saves)
        self.assertTrue(result.ok, result.error)
        p = restored.player
        self.assertEqual(p.level, snapshot["level"])
        self.assertEqual(p.xp, snapshot["xp"])
        self.assertEqual(restored.coins, snapshot["coins"])
        self.assertEqual(p.stats.to_dict(), snapshot["stats"])  # boots bonus applied exactly once
        self.assertEqual(p.inventory.stacks, snapshot["inventory"])
        self.assertEqual({s: i.item_id for s, i in p.equipment.items().items()}, snapshot["equipment"])
        self.assertEqual(p.equipment.get(EquipSlot.FEET).item_id, "traveler_boots")
        self.assertEqual(restored.campaign.quests.to_dict(), snapshot["quests"])
        self.assertEqual(restored.campaign.ledger.claimed, snapshot["ledger"])
        self.assertEqual(restored.zone.zone_id, snapshot["zone"])
        self.assertEqual(p.position, snapshot["position"])
        self.assertEqual(restored.world.time, snapshot["time"])
        self.assertEqual(restored.campaign.merchant("proto_general_store").state.to_dict(), snapshot["stock"])

        # The reloaded game keeps working: the completed quest cannot pay twice
        # and the next quest in the chain is on offer.
        again = SliceDriver(restored)
        self.assertEqual(restored.npc_marker(restored.npcs[0]), "!")
        again.talk("proto_elder")
        self.assertIn("Strange Bones", again.choose("I'll look into it").messages[0])
        again.leave_conversation()
        self.assertEqual(restored.campaign.ledger.claimed, snapshot["ledger"])


if __name__ == "__main__":
    unittest.main()
