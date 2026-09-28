"""MC-007: wallet, pricing, merchants, blacksmith, reward hooks, persistence."""

import json
import random
import tempfile
import unittest
from pathlib import Path

from game.campaign import Campaign
from game.core.vector import Vec2
from game.economy.blacksmith import inspect_equipment
from game.economy.catalog import MERCHANTS, get_merchant
from game.economy.merchant import (
    Merchant, MerchantDefinition, MerchantState, ServiceType, StockEntry, TransactionStatus,
)
from game.economy.pricing import PricePolicy
from game.economy.wallet import MAX_BALANCE, Wallet, WalletStatus
from game.entities.player import Player
from game.items.actions import give_item
from game.items.catalog import get_item
from game.items.definitions import ItemCategory, ItemDefinition, Rarity
from game.npcs.catalog import get_npc
from game.persistence.save_manager import LoadStatus, SaveManager
from game.progression.rewards import GrantStatus, Reward, RewardSource, reward_key
from game.session import PlayerInput
from game.world.world_state import WorldState
from game.world_session import WorldSession

DT = 1 / 60


def store(pricing=PricePolicy(1.0, 0.4)):
    definition = MerchantDefinition(
        "test_store", "Test Store", "proto_merchant",
        stock=(StockEntry("minor_health_potion"), StockEntry("iron_helm", 1)),
        pricing=pricing,
        buys=(ItemCategory.MATERIAL, ItemCategory.ARMOR, ItemCategory.CONSUMABLE),
    )
    return Merchant(definition, MerchantState.fresh(definition), get_item)


class WalletTests(unittest.TestCase):
    def test_earn_and_spend(self):
        wallet = Wallet()
        self.assertTrue(wallet.earn(50).ok)
        self.assertTrue(wallet.spend(20).ok)
        self.assertEqual(wallet.balance, 30)

    def test_insufficient_funds_and_invalid_amounts(self):
        wallet = Wallet(10)
        self.assertEqual(wallet.spend(11).status, WalletStatus.INSUFFICIENT_FUNDS)
        self.assertEqual(wallet.balance, 10)
        for bad in (0, -5, 2.5, True, "3"):
            self.assertEqual(wallet.earn(bad).status, WalletStatus.INVALID_AMOUNT)
            self.assertEqual(wallet.spend(bad).status, WalletStatus.INVALID_AMOUNT)
        self.assertEqual(wallet.balance, 10)

    def test_limits(self):
        with self.assertRaises(ValueError):
            Wallet(-1)
        with self.assertRaises(ValueError):
            Wallet(MAX_BALANCE + 1)
        wallet = Wallet(MAX_BALANCE)
        self.assertEqual(wallet.earn(1).status, WalletStatus.OVER_LIMIT)


class PricingTests(unittest.TestCase):
    def test_prices_use_value_rarity_and_margins(self):
        policy = PricePolicy(markup=1.2, buyback=0.5)
        helm = get_item("iron_helm")  # uncommon (1.5x), base 35
        self.assertEqual(policy.buy_price(helm), 63)  # ceil(35 * 1.5 * 1.2)
        self.assertEqual(policy.sell_price(helm), 26)  # floor(35 * 1.5 * 0.5)
        common = ItemDefinition("x", "X", ItemCategory.MISC, base_value=10)
        rare = ItemDefinition("y", "Y", ItemCategory.MISC, base_value=10, rarity=Rarity.RARE)
        self.assertGreater(policy.buy_price(rare), policy.buy_price(common))

    def test_no_arbitrage_and_minimum_price(self):
        with self.assertRaises(ValueError):
            PricePolicy(markup=1.0, buyback=1.5)
        free = ItemDefinition("f", "F", ItemCategory.MISC, base_value=0)
        self.assertEqual(PricePolicy().buy_price(free), 1)
        self.assertEqual(PricePolicy().sell_price(get_item("sealed_letter")), 0)
        for merchant in MERCHANTS.values():
            for offer in Merchant(merchant, MerchantState.fresh(merchant), get_item).offers():
                self.assertGreater(offer.price, merchant.pricing.sell_price(offer.item))


class MerchantTests(unittest.TestCase):
    def test_buy(self):
        merchant, player, wallet = store(), Player("P"), Wallet(100)
        result = merchant.buy(player, wallet, "minor_health_potion", 3)
        self.assertTrue(result.ok)
        self.assertEqual(result.total, 45)
        self.assertEqual(wallet.balance, 55)
        self.assertEqual(player.inventory.count("minor_health_potion"), 3)

    def test_limited_stock(self):
        merchant, player, wallet = store(), Player("P"), Wallet(1000)
        self.assertTrue(merchant.buy(player, wallet, "iron_helm").ok)
        self.assertEqual(merchant.buy(player, wallet, "iron_helm").status, TransactionStatus.OUT_OF_STOCK)
        self.assertEqual(merchant.offers()[1].available, 0)

    def test_insufficient_funds_changes_nothing(self):
        merchant, player, wallet = store(), Player("P"), Wallet(10)
        result = merchant.buy(player, wallet, "minor_health_potion")
        self.assertEqual(result.status, TransactionStatus.INSUFFICIENT_FUNDS)
        self.assertEqual(wallet.balance, 10)
        self.assertEqual(player.inventory.count("minor_health_potion"), 0)

    def test_inventory_full_purchase_changes_nothing(self):
        merchant, player, wallet = store(), Player("P", inventory_capacity=1), Wallet(1000)
        give_item(player, get_item("iron_scrap"), 20)
        result = merchant.buy(player, wallet, "iron_helm")
        self.assertEqual(result.status, TransactionStatus.INVENTORY_FULL)
        self.assertEqual(wallet.balance, 1000)
        self.assertEqual(merchant.state.remaining["iron_helm"], 1)  # stock untouched

    def test_buy_validation(self):
        merchant, player, wallet = store(), Player("P"), Wallet(1000)
        self.assertEqual(merchant.buy(player, wallet, "iron_greatsword").status, TransactionStatus.NOT_SOLD_HERE)
        for bad in (0, -2, 1.5, True):
            self.assertEqual(merchant.buy(player, wallet, "minor_health_potion", bad).status,
                             TransactionStatus.INVALID_QUANTITY)
        player.receive_damage(10_000)
        self.assertEqual(merchant.buy(player, wallet, "minor_health_potion").status, TransactionStatus.DEAD)
        self.assertEqual(wallet.balance, 1000)

    def test_sell(self):
        merchant, player, wallet = store(), Player("P"), Wallet()
        give_item(player, get_item("iron_scrap"), 5)
        result = merchant.sell(player, wallet, "iron_scrap", 3)
        self.assertTrue(result.ok)
        self.assertEqual(result.total, 3 * 3)  # floor(6 * 1.5 * 0.4) = 3 each
        self.assertEqual(wallet.balance, 9)
        self.assertEqual(player.inventory.count("iron_scrap"), 2)

    def test_invalid_sales_change_nothing(self):
        merchant, player, wallet = store(), Player("P"), Wallet(5)
        give_item(player, get_item("sealed_letter"))
        give_item(player, get_item("old_coin"), 3)
        player.equip(get_item("iron_sword"))
        cases = [
            ("sealed_letter", 1, TransactionStatus.UNSELLABLE),  # quest item
            ("old_coin", 1, TransactionStatus.NOT_BUYING),  # misc: this store does not buy it
            ("iron_scrap", 1, TransactionStatus.NOT_OWNED),
            ("old_coin", 9, TransactionStatus.NOT_OWNED),
            ("iron_sword", 1, TransactionStatus.NOT_OWNED),  # equipped gear is not for sale
            ("ghost_item", 1, TransactionStatus.UNKNOWN_ITEM),
            ("old_coin", 0, TransactionStatus.INVALID_QUANTITY),
        ]
        for item_id, quantity, expected in cases:
            with self.subTest(item=item_id):
                self.assertEqual(merchant.sell(player, wallet, item_id, quantity).status, expected)
        self.assertEqual(wallet.balance, 5)
        self.assertEqual(player.inventory.count("old_coin"), 3)
        self.assertEqual(player.inventory.count("sealed_letter"), 1)

    def test_transaction_integrity_over_random_trades(self):
        """Coins + stock never appear from nowhere across many trades."""
        merchant, player, wallet = store(), Player("P", inventory_capacity=3), Wallet(200)
        rng = random.Random(5)
        for _ in range(300):
            before = (wallet.balance, player.inventory.count("minor_health_potion"))
            if rng.random() < 0.5:
                result = merchant.buy(player, wallet, "minor_health_potion", rng.randint(1, 4))
                if result.ok:
                    self.assertEqual(wallet.balance, before[0] - result.total)
                    self.assertEqual(player.inventory.count("minor_health_potion"), before[1] + result.quantity)
            else:
                result = merchant.sell(player, wallet, "minor_health_potion", rng.randint(1, 4))
                if result.ok:
                    self.assertEqual(wallet.balance, before[0] + result.total)
                    self.assertEqual(player.inventory.count("minor_health_potion"), before[1] - result.quantity)
            if not result.ok:
                self.assertEqual((wallet.balance, player.inventory.count("minor_health_potion")), before)
            self.assertGreaterEqual(wallet.balance, 0)

    def test_definition_validation(self):
        with self.assertRaises(ValueError):
            StockEntry("x", 0)
        with self.assertRaises(ValueError):
            MerchantDefinition("m", "M", "n", (StockEntry("x"), StockEntry("x")))
        with self.assertRaises(ValueError):
            MerchantDefinition("m", "M", "n", (), buys=(ItemCategory.QUEST,))


class BlacksmithTests(unittest.TestCase):
    def test_inspect_equipped_gear(self):
        campaign = Campaign()
        smith = campaign.merchant("proto_smithy")
        player = Player("P")
        player.equip(get_item("iron_sword"))
        player.equip(get_item("leather_jerkin"))
        reports = inspect_equipment(smith, player)
        self.assertEqual([r.slot for r in reports], ["main_hand", "chest"])
        self.assertIn("parry yes", reports[0].details)
        self.assertIn("durability", reports[1].details)
        general = campaign.merchant("proto_general_store")
        self.assertFalse(general.has_service(ServiceType.INSPECT))
        self.assertEqual(inspect_equipment(general, player), ())

    def test_no_upgrade_service_is_invented(self):
        self.assertEqual({s.value for s in ServiceType}, {"shop", "inspect"})
        self.assertEqual(get_merchant("proto_smithy").services, (ServiceType.SHOP, ServiceType.INSPECT))


class RewardHookTests(unittest.TestCase):
    def test_reward_keys(self):
        self.assertEqual(reward_key(RewardSource.QUEST, "q"), "quest:q")
        self.assertEqual(reward_key(RewardSource.EXPLORATION, "p"), "discovery:p")
        with self.assertRaises(ValueError):
            reward_key(RewardSource.ENCOUNTER, "")

    def test_encounter_clear_reward_once(self):
        session = WorldSession.new()
        session.travel("to_road")
        session.travel("to_wilds")
        den = next(e for e in session.encounters if e.spec.encounter_id == "brute_den")
        den.start()
        coins, xp_level = session.coins, (session.player.level, session.player.xp)
        den.enemies[0].receive_damage(100_000)
        session.update(DT, PlayerInput())
        # brute kill coins (12) + den clear reward (40)
        self.assertEqual(session.coins, coins + 12 + 40)
        self.assertGreater((session.player.level, session.player.xp), xp_level)
        self.assertTrue(session.campaign.ledger.is_claimed("encounter:proto_wilds/den"))
        again = session.grant(RewardSource.ENCOUNTER, "proto_wilds/den", den.spec.clear_reward)
        self.assertEqual(again.status, GrantStatus.ALREADY_CLAIMED)
        self.assertEqual(session.coins, coins + 52)

    def test_quest_reward_pays_coins(self):
        session = WorldSession.new()
        quests = session.campaign.quests
        quests.accept("proto_clear_camp")
        from game.events.events import EnemyDefeated
        for i in range(2):
            session.bus.publish(EnemyDefeated(str(i), "striker"))
        session.player.position = get_npc("proto_elder").position
        session.talk_to("proto_elder")
        session.choose_dialogue(0)
        self.assertEqual(session.coins, 30)

    def test_enemy_kill_pays_coins_once(self):
        session = WorldSession.new()
        session.travel("to_road")
        ambush = session.encounters[0]
        ambush.start()
        for enemy in ambush.enemies:
            enemy.receive_damage(10_000)
        session.update(DT, PlayerInput())
        session.update(DT, PlayerInput())
        self.assertEqual(session.coins, 4 + 5)  # striker + archer, counted once


class EconomyPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "save.json"
        self.manager = SaveManager(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_wallet_and_stock_round_trip(self):
        campaign = Campaign()
        campaign.wallet.earn(500)
        player = Player("P")
        smith = campaign.merchant("proto_smithy")
        self.assertTrue(smith.buy(player, campaign.wallet, "iron_helm").ok)
        self.manager.save(player, WorldState(), campaign)
        result = self.manager.load()
        self.assertEqual(result.status, LoadStatus.OK, result.error)
        self.assertEqual(result.campaign.wallet.balance, campaign.wallet.balance)
        self.assertEqual(result.campaign.merchant("proto_smithy").state.remaining["iron_helm"], 0)
        self.assertEqual(result.player.inventory.count("iron_helm"), 1)

    def test_malformed_economy(self):
        self.manager.save(Player("P"), WorldState(), Campaign())
        base = json.loads(self.path.read_text())
        patches = [
            {"wallet": -10},
            {"wallet": 2.5},
            {"wallet": "100"},
            {"wallet": MAX_BALANCE + 1},
            {"merchants": {"ghost_shop": {}}},
            {"merchants": {"proto_smithy": {"iron_helm": 5}}},  # more than it ever stocked
            {"merchants": {"proto_smithy": {"iron_helm": -1}}},
            {"merchants": []},
        ]
        for patch in patches:
            with self.subTest(patch=patch):
                data = json.loads(json.dumps(base))
                data["campaign"].update(patch)
                self.path.write_text(json.dumps(data))
                self.assertEqual(self.manager.load().status, LoadStatus.MALFORMED)

    def test_v5_migrates_with_empty_wallet(self):
        self.manager.save(Player("P"), WorldState(), Campaign())
        data = json.loads(self.path.read_text())
        data["schema_version"] = 5
        del data["campaign"]["wallet"]
        del data["campaign"]["merchants"]
        self.path.write_text(json.dumps(data))
        result = self.manager.load()
        self.assertEqual(result.status, LoadStatus.OK, result.error)
        self.assertEqual(result.campaign.wallet.balance, 0)


class EconomyLoopTests(unittest.TestCase):
    """quest -> combat -> XP + loot -> return -> sell -> buy -> equip, headless."""

    def test_headless_economy_loop(self):
        import sys
        sys.path.insert(0, "tests")
        from test_encounters import fighting_player_input

        session = WorldSession.new()
        session.rng = random.Random(11)
        quests = session.campaign.quests
        session.player.position = get_npc("proto_elder").position + Vec2(30, 0)
        session.talk_to("proto_elder")
        session.choose_dialogue(0)  # accept "Clear the Raider Camp"
        session.end_conversation()

        session.travel("to_road")
        session.travel("to_wilds")
        count = session.player.inventory.count
        for _ in range(round(120 / DT)):
            session.update(DT, fighting_player_input(session))
            if quests.status("proto_clear_camp", count).value == "ready_to_turn_in" and not any(
                    e.is_alive for enc in session.encounters if enc.spec.encounter_id == "raider_camp" for e in enc.enemies):
                break
        while session.ground.drops:  # loot the camp
            session.player.position = session.ground.drops[0].position
            session.update(DT, PlayerInput(interact=True))
        self.assertGreater(count("bone_shard"), 0)

        session.travel("to_road")
        session.travel("to_village")
        session.player.position = get_npc("proto_elder").position + Vec2(30, 0)
        session.talk_to("proto_elder")
        session.choose_dialogue(0)
        session.end_conversation()
        self.assertEqual(quests.stored_status("proto_clear_camp").value, "completed")

        # Sell the bone shards to the smith, then buy a helm and equip it.
        coins = session.coins
        session.player.position = get_npc("proto_smith").position + Vec2(30, 0)
        session.talk_to("proto_smith")
        session.choose_dialogue(0)
        self.assertEqual(session.shop, "proto_smithy")
        shards = count("bone_shard")
        self.assertTrue(session.sell("bone_shard", shards).ok)
        self.assertGreater(session.coins, coins)
        session.campaign.wallet.earn(max(0, 63 - session.coins))  # top up if the run was poor
        self.assertTrue(session.buy("iron_helm").ok)
        session.close_shop()
        durability = session.player.stats.durability
        self.assertTrue(session.use_or_equip("iron_helm").ok)
        self.assertEqual(session.player.stats.durability, durability + 5)


if __name__ == "__main__":
    unittest.main()
