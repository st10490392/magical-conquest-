"""MC-004: items, rarity, inventory, equipment, armor, consumables, loot."""

import json
import random
import tempfile
import unittest
from pathlib import Path

from game.core.combat import AttackOutcome, resolve_attack
from game.core.stats import Stats
from game.core.vector import Vec2
from game.entities.archetypes import create_enemy
from game.entities.player import Player
from game.equipment.catalog import WEAPONS
from game.equipment.slots import EquipSlot, StatModifiers
from game.items.actions import ItemActionStatus, equip_from_inventory, give_item, unequip_to_inventory, use_item
from game.items.catalog import ITEMS, get_item, item_for
from game.items.definitions import ArmorProfile, ConsumableEffect, ItemCategory, ItemDefinition, Rarity
from game.items.ground import GroundLoot, PickupStatus
from game.items.inventory import Inventory, InventoryStatus
from game.items.loot import ItemDrop, LootEntry, LootTable, WeightedPick
from game.items.loot_tables import LOOT_TABLES, get_loot_table
from game.persistence.save_manager import SAVE_SCHEMA_VERSION, LoadStatus, SaveManager
from game.session import GameSession, PlayerInput
from game.world.world_state import WorldState

POTION = get_item("minor_health_potion")
SCRAP = get_item("iron_scrap")
SWORD = get_item("iron_sword")
JERKIN = get_item("leather_jerkin")
HELM = get_item("iron_helm")


class ItemDefinitionTests(unittest.TestCase):
    def test_catalog_categories_and_identity(self):
        categories = {item.category for item in ITEMS.values()}
        self.assertEqual(categories, set(ItemCategory))
        for item_id, item in ITEMS.items():
            self.assertEqual(item.item_id, item_id)
        self.assertIs(get_item("iron_sword"), get_item("iron_sword"))
        self.assertIs(SWORD.weapon, WEAPONS["iron_sword"])  # items reuse MC-002 weapons
        with self.assertRaises(ValueError):
            get_item("dragon_slayer")

    def test_validation(self):
        with self.assertRaises(ValueError):
            ItemDefinition("Bad ID", "x", ItemCategory.MISC)
        with self.assertRaises(ValueError):
            ItemDefinition("x", "X", ItemCategory.CONSUMABLE)  # missing effect
        with self.assertRaises(ValueError):
            ItemDefinition("x", "X", ItemCategory.MISC, max_stack=0)
        with self.assertRaises(ValueError):
            ItemDefinition("x", "X", ItemCategory.MISC, base_value=-1)
        with self.assertRaises(ValueError):
            ItemDefinition("x", "X", ItemCategory.QUEST, sellable=True)
        with self.assertRaises(ValueError):
            ArmorProfile(EquipSlot.MAIN_HAND, StatModifiers.of(durability=1))
        with self.assertRaises(ValueError):
            StatModifiers.of(max_health=10)  # pool modifiers are deferred
        with self.assertRaises(ValueError):
            StatModifiers.of(durability=-3)
        with self.assertRaises(ValueError):
            ConsumableEffect()

    def test_rarity_affects_value_not_power(self):
        self.assertLess(Rarity.COMMON.value_multiplier, Rarity.RARE.value_multiplier)
        # The uncommon warding hood gives no durability; the uncommon iron helm
        # and the common leather cap both do: stats come from the item itself.
        self.assertEqual(get_item("warding_hood").modifiers.as_dict().get("durability", 0), 0)
        self.assertGreater(get_item("leather_cap").modifiers.as_dict()["durability"], 0)

    def test_stackability(self):
        self.assertTrue(POTION.stackable)
        self.assertFalse(SWORD.stackable)
        self.assertEqual(SWORD.equip_slot, EquipSlot.MAIN_HAND)
        self.assertEqual(JERKIN.equip_slot, EquipSlot.CHEST)
        self.assertIsNone(POTION.equip_slot)


class InventoryTests(unittest.TestCase):
    def test_add_stacks_and_limits(self):
        inv = Inventory(capacity=3)
        self.assertTrue(inv.add(POTION, 7).ok)
        self.assertTrue(inv.add(POTION, 5).ok)  # tops up the first stack (10) then a new one
        self.assertEqual([q for _, q in inv.stacks], [10, 2])
        self.assertEqual(inv.count("minor_health_potion"), 12)
        self.assertEqual(inv.space_for(POTION), 8 + 10)

    def test_capacity_and_all_or_nothing(self):
        inv = Inventory(capacity=2)
        inv.add(SWORD)
        inv.add(POTION, 9)
        before = inv.stacks
        result = inv.add(POTION, 2)  # only 1 fits
        self.assertEqual(result.status, InventoryStatus.FULL)
        self.assertEqual(inv.stacks, before)
        self.assertEqual(inv.add(HELM).status, InventoryStatus.FULL)
        self.assertTrue(inv.add(POTION, 1).ok)

    def test_remove(self):
        inv = Inventory()
        inv.add(POTION, 12)
        self.assertTrue(inv.remove("minor_health_potion", 3).ok)
        self.assertEqual(inv.count("minor_health_potion"), 9)
        self.assertEqual(inv.remove("minor_health_potion", 50).status, InventoryStatus.NOT_ENOUGH)
        self.assertEqual(inv.count("minor_health_potion"), 9)
        self.assertEqual(inv.remove("iron_scrap").status, InventoryStatus.NOT_ENOUGH)
        self.assertTrue(inv.remove("minor_health_potion", 9).ok)
        self.assertEqual(inv.used_slots, 0)

    def test_invalid_quantities(self):
        inv = Inventory()
        for bad in (0, -1, 1.5, True, "2"):
            self.assertEqual(inv.add(POTION, bad).status, InventoryStatus.INVALID_QUANTITY)
            self.assertEqual(inv.remove("minor_health_potion", bad).status, InventoryStatus.INVALID_QUANTITY)
        self.assertEqual(inv.used_slots, 0)

    def test_split(self):
        inv = Inventory(capacity=2)
        inv.add(SCRAP, 10)
        self.assertTrue(inv.split(0, 4).ok)
        self.assertEqual([q for _, q in inv.stacks], [6, 4])
        self.assertEqual(inv.split(0, 1).status, InventoryStatus.FULL)
        self.assertEqual(inv.split(0, 6).status, InventoryStatus.INVALID_QUANTITY)
        self.assertEqual(inv.split(5, 1).status, InventoryStatus.INVALID_SLOT)
        self.assertEqual(inv.count("iron_scrap"), 10)

    def test_unique_items(self):
        relic = ItemDefinition("test_relic", "Test Relic", ItemCategory.MISC, unique=True)
        inv = Inventory()
        self.assertTrue(inv.add(relic).ok)
        self.assertEqual(inv.add(relic).status, InventoryStatus.UNIQUE_OWNED)
        self.assertEqual(inv.count("test_relic"), 1)

    def test_serialization_roundtrip_and_validation(self):
        inv = Inventory(capacity=5)
        inv.add(POTION, 3)
        inv.add(SWORD)
        clone = Inventory.from_list(inv.to_list(), get_item, 5)
        self.assertEqual(clone.stacks, inv.stacks)
        bad_payloads = [
            "potions",
            [{"item": "minor_health_potion", "qty": 11}],  # over max stack
            [{"item": "minor_health_potion", "qty": 0}],
            [{"item": "minor_health_potion", "qty": -4}],
            [{"item": "minor_health_potion", "qty": 2.5}],
            [{"item": "dragon_slayer", "qty": 1}],
            [{"item": "iron_sword", "qty": 1, "extra": True}],
            [{"item": "iron_sword", "qty": 1}] * 6,  # more stacks than slots
        ]
        for payload in bad_payloads:
            with self.subTest(payload=payload), self.assertRaises((TypeError, ValueError)):
                Inventory.from_list(payload, get_item, 5)


class EquipmentTests(unittest.TestCase):
    def player(self):
        return Player("Tester", Stats(max_health=100, durability=5, magic_resistance=2, agility=1))

    def test_equip_and_unequip_armor_modifies_stats(self):
        player = self.player()
        player.equip(JERKIN)
        self.assertEqual(player.stats.durability, 9)
        self.assertEqual(player.stats.magic_resistance, 3)
        self.assertIs(player.unequip(EquipSlot.CHEST), JERKIN)
        self.assertEqual(player.stats.durability, 5)
        self.assertEqual(player.stats.magic_resistance, 2)

    def test_replacing_in_same_slot(self):
        player = self.player()
        player.equip(get_item("leather_cap"))
        self.assertIs(player.equip(HELM), get_item("leather_cap"))
        self.assertEqual(player.stats.durability, 10)  # 5 + helm 5, cap removed

    def test_repeated_equip_never_inflates(self):
        player = self.player()
        original = player.stats.to_dict()
        armor = [get_item(i) for i in ("iron_helm", "leather_jerkin", "leather_gloves", "leather_greaves", "traveler_boots")]
        for _ in range(500):
            for piece in armor:
                player.equip(piece)
            for piece in armor:
                player.unequip(piece.equip_slot)
        self.assertEqual(player.stats.to_dict(), original)

    def test_base_stats_exclude_gear_and_growth_survives(self):
        player = self.player()
        player.equip(HELM)
        player.gain_xp(1000)  # level growth while armored
        grown = player.base_stats().durability
        player.unequip(EquipSlot.HEAD)
        self.assertEqual(player.stats.durability, grown)

    def test_weapon_integration_unchanged(self):
        player = Player("Tester", Stats(max_health=500, physical_strength=10, durability=0))
        player.equip(SWORD)
        target = Player("Dummy", Stats(max_health=500, durability=0), position=Vec2(50, 0))
        result = player.weapon_attack(target)
        self.assertTrue(result.landed)
        self.assertAlmostEqual(result.damage, 12 + 10)
        self.assertTrue(player.guard_profile().can_parry)
        player.equip(WEAPONS["ash_spear"])  # bare MC-002 weapons still equip
        self.assertIs(player.weapon, WEAPONS["ash_spear"])

    def test_armor_reduces_damage_but_never_to_zero(self):
        attacker = create_enemy("brute", position=Vec2(50, 0))
        bare = Player("Bare", Stats(max_health=1000, durability=0))
        armored = Player("Armored", Stats(max_health=1000, durability=0))
        for item_id in ("iron_helm", "leather_jerkin", "leather_greaves"):
            armored.equip(get_item(item_id))
        hit_bare = resolve_attack(attacker, bare, attacker.attack, check_range=False)
        hit_armored = resolve_attack(attacker, armored, attacker.attack, check_range=False)
        self.assertLess(hit_armored.damage, hit_bare.damage)
        self.assertGreater(hit_armored.damage, 0)

    def test_main_hand_rejects_armor(self):
        with self.assertRaises(TypeError):
            self.player().equipment.equip(POTION)


class ItemActionTests(unittest.TestCase):
    def test_equip_from_inventory_swaps(self):
        player = Player("Tester")
        player.equip(SWORD)
        give_item(player, get_item("steel_dagger"))
        self.assertTrue(equip_from_inventory(player, "steel_dagger").ok)
        self.assertEqual(player.weapon.weapon_id, "steel_dagger")
        self.assertEqual(player.inventory.count("iron_sword"), 1)
        self.assertEqual(player.inventory.count("steel_dagger"), 0)

    def test_equip_failures(self):
        player = Player("Tester")
        self.assertEqual(equip_from_inventory(player, "iron_helm").status, ItemActionStatus.NOT_IN_INVENTORY)
        give_item(player, POTION)
        self.assertEqual(equip_from_inventory(player, "minor_health_potion").status, ItemActionStatus.NOT_EQUIPPABLE)

    def test_unequip_needs_space(self):
        player = Player("Tester", inventory_capacity=1)
        player.equip(HELM)
        give_item(player, SCRAP, 5)
        self.assertEqual(unequip_to_inventory(player, EquipSlot.HEAD).status, ItemActionStatus.INVENTORY_FULL)
        self.assertIs(player.equipment.get(EquipSlot.HEAD), HELM)  # nothing lost
        player.inventory.remove("iron_scrap", 5)
        self.assertTrue(unequip_to_inventory(player, EquipSlot.HEAD).ok)
        self.assertEqual(unequip_to_inventory(player, EquipSlot.HEAD).status, ItemActionStatus.SLOT_EMPTY)

    def test_consumables_respect_caps(self):
        player = Player("Tester", Stats(max_health=100, max_mana=50))
        give_item(player, POTION, 2)
        self.assertEqual(use_item(player, "minor_health_potion").status, ItemActionStatus.NO_EFFECT)
        self.assertEqual(player.inventory.count("minor_health_potion"), 2)  # kept
        player.stats.take_damage(10)
        self.assertTrue(use_item(player, "minor_health_potion").ok)
        self.assertEqual(player.stats.health, 100)  # capped, not 130
        self.assertEqual(player.inventory.count("minor_health_potion"), 1)

    def test_mana_and_stamina_consumables(self):
        player = Player("Tester", Stats(max_health=100, max_mana=50, max_stamina=100))
        give_item(player, get_item("minor_mana_potion"))
        give_item(player, get_item("stamina_tonic"))
        player.stats.consume_mana(40)
        player.stats.consume_stamina(90)
        self.assertTrue(use_item(player, "minor_mana_potion").ok)
        self.assertTrue(use_item(player, "stamina_tonic").ok)
        self.assertEqual(player.stats.mana, 40)
        self.assertEqual(player.stats.stamina, 60)

    def test_invalid_consumption(self):
        player = Player("Tester")
        player.stats.take_damage(10)
        self.assertEqual(use_item(player, "minor_health_potion").status, ItemActionStatus.NOT_IN_INVENTORY)
        give_item(player, SCRAP)
        self.assertEqual(use_item(player, "iron_scrap").status, ItemActionStatus.NOT_CONSUMABLE)
        give_item(player, POTION)
        player.receive_damage(10_000)
        self.assertEqual(use_item(player, "minor_health_potion").status, ItemActionStatus.DEAD)
        self.assertEqual(player.inventory.count("minor_health_potion"), 1)

    def test_unique_across_inventory_and_equipment(self):
        relic = ItemDefinition(
            "test_relic_helm", "Relic Helm", ItemCategory.ARMOR, unique=True,
            armor=ArmorProfile(EquipSlot.HEAD, StatModifiers.of(durability=1)),
        )
        player = Player("Tester")
        player.equip(relic)
        self.assertEqual(give_item(player, relic).status, InventoryStatus.UNIQUE_OWNED)


class LootTests(unittest.TestCase):
    def test_guaranteed_loot_needs_no_randomness(self):
        table = LootTable("t", (LootEntry("bone_shard", 1.0, 2, 2), LootEntry("old_coin")))

        class NoRandom(random.Random):
            def random(self):
                raise AssertionError("guaranteed drops must not roll")

            def randint(self, a, b):
                raise AssertionError("fixed quantities must not roll")

        self.assertEqual(table.roll(NoRandom()), [ItemDrop("bone_shard", 2), ItemDrop("old_coin", 1)])

    def test_seeded_rolls_are_deterministic(self):
        table = get_loot_table("brute")
        first = [table.roll(random.Random(42)) for _ in range(5)]
        second = [table.roll(random.Random(42)) for _ in range(5)]
        self.assertEqual(first, second)

    def test_chance_and_weights_over_many_seeds(self):
        table = LootTable("t", (LootEntry("old_coin", 0.25),),
                          pool=(WeightedPick("iron_helm", 1), WeightedPick(None, 3)), pool_picks=1)
        rng = random.Random(7)
        coins = helms = 0
        for _ in range(4000):
            ids = {d.item_id for d in table.roll(rng)}
            coins += "old_coin" in ids
            helms += "iron_helm" in ids
        self.assertAlmostEqual(coins / 4000, 0.25, delta=0.03)
        self.assertAlmostEqual(helms / 4000, 0.25, delta=0.03)

    def test_quantities_within_bounds(self):
        table = LootTable("t", (LootEntry("iron_scrap", 1.0, 2, 3),))
        rng = random.Random(1)
        seen = {table.roll(rng)[0].quantity for _ in range(200)}
        self.assertEqual(seen, {2, 3})

    def test_tables_reference_real_items(self):
        for table in LOOT_TABLES.values():
            for item_id in table.item_ids():
                self.assertIn(item_id, ITEMS)
        with self.assertRaises(ValueError):
            LootEntry("x", chance=0)
        with self.assertRaises(ValueError):
            LootEntry("x", min_qty=3, max_qty=2)

    def test_brute_always_drops_its_guaranteed_items(self):
        for seed in range(30):
            ids = {d.item_id for d in get_loot_table("brute").roll(random.Random(seed))}
            self.assertTrue({"iron_scrap", "minor_health_potion"} <= ids)


class GroundLootTests(unittest.TestCase):
    def test_pickup_all_and_partial(self):
        ground = GroundLoot()
        drop = ground.spawn(Vec2(10, 10), [ItemDrop("iron_scrap", 3), ItemDrop("iron_helm", 1)], get_item)
        player = Player("Tester", inventory_capacity=1)
        result = ground.pickup(drop.drop_id, lambda item, qty: give_item(player, item, qty))
        self.assertEqual(result.status, PickupStatus.PARTIAL)
        self.assertEqual(result.taken, (("iron_scrap", 3),))
        self.assertEqual(result.left, (("iron_helm", 1),))
        self.assertEqual(len(ground.drops), 1)  # the helm stays on the ground
        player.inventory.remove("iron_scrap", 3)
        result = ground.pickup(drop.drop_id, lambda item, qty: give_item(player, item, qty))
        self.assertEqual(result.status, PickupStatus.ALL)
        self.assertEqual(ground.drops, [])
        self.assertEqual(ground.pickup(drop.drop_id, lambda i, q: None).status, PickupStatus.NO_DROP)

    def test_empty_roll_spawns_nothing_and_nearest(self):
        ground = GroundLoot()
        self.assertIsNone(ground.spawn(Vec2(), [], get_item))
        ground.spawn(Vec2(0, 0), [ItemDrop("old_coin", 1)], get_item)
        far = ground.spawn(Vec2(500, 0), [ItemDrop("old_coin", 1)], get_item)
        self.assertIsNone(ground.nearest(Vec2(300, 0)))
        self.assertIs(ground.nearest(Vec2(480, 0)), far)


class SessionLootTests(unittest.TestCase):
    def test_defeat_drops_loot_once_and_player_picks_it_up(self):
        session = GameSession.new(encounter_id="brute_drill")
        brute = session.enemies[0]
        brute.receive_damage(10_000)
        session.update(1 / 60, PlayerInput())
        session.update(1 / 60, PlayerInput())  # a second tick must not re-drop
        self.assertEqual(len(session.ground.drops), 1)
        self.assertEqual(session.kills, 1)
        self.assertEqual(session.player.xp, brute.xp_reward)
        scrap_before = session.player.inventory.count("iron_scrap")
        session.player.position = session.ground.drops[0].position
        session.update(1 / 60, PlayerInput(interact=True))
        self.assertEqual(session.ground.drops, [])
        self.assertGreaterEqual(session.player.inventory.count("iron_scrap"), scrap_before + 2)

    def test_loot_is_reproducible_per_seed(self):
        def run():
            session = GameSession.new(encounter_id="brute_drill")
            session.enemies[0].receive_damage(10_000)
            session.update(1 / 60, PlayerInput())
            return [(i.item_id, q) for i, q in session.ground.drops[0].items]

        self.assertEqual(run(), run())

    def test_session_equip_and_use(self):
        session = GameSession.new()
        self.assertTrue(session.use_or_equip("leather_cap").ok)
        self.assertEqual(session.player.equipment.get(EquipSlot.HEAD).item_id, "leather_cap")
        self.assertTrue(session.unequip_slot(EquipSlot.HEAD).ok)
        session.player.stats.take_damage(50)
        self.assertTrue(session.use_or_equip("minor_health_potion").ok)


class PersistenceV3Tests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "save.json"
        self.manager = SaveManager(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip_inventory_and_equipment(self):
        player = Player("Aria", Stats(max_health=100, durability=3))
        player.equip(SWORD)
        player.equip(HELM)
        player.equip(JERKIN)
        give_item(player, POTION, 7)
        give_item(player, SCRAP, 3)
        effective = player.stats.to_dict()
        self.manager.save(player, WorldState())
        data = json.loads(self.path.read_text())
        self.assertEqual(data["schema_version"], SAVE_SCHEMA_VERSION)
        self.assertEqual(data["player"]["stats"]["durability"], 3)  # base, not boosted
        loaded = self.manager.load().player
        self.assertEqual(loaded.stats.to_dict(), effective)  # no double bonus
        self.assertEqual(loaded.equipment.get(EquipSlot.HEAD).item_id, "iron_helm")
        self.assertIs(loaded.weapon, WEAPONS["iron_sword"])
        self.assertEqual(loaded.inventory.stacks, player.inventory.stacks)
        loaded.unequip(EquipSlot.HEAD)
        loaded.unequip(EquipSlot.CHEST)
        self.assertEqual(loaded.stats.durability, 3)

    def write_player_patch(self, **patch):
        self.manager.save(Player("Aria"), WorldState())
        data = json.loads(self.path.read_text())
        data["player"].update(patch)
        self.path.write_text(json.dumps(data))
        return self.manager.load()

    def test_malformed_inventory_and_equipment(self):
        cases = [
            {"inventory": [{"item": "minor_health_potion", "qty": 99}]},
            {"inventory": [{"item": "minor_health_potion", "qty": -1}]},
            {"inventory": [{"item": "ghost_item", "qty": 1}]},
            {"inventory": "lots"},
            {"equipment": {"head": "iron_sword"}},
            {"equipment": {"tail": "iron_helm"}},
            {"equipment": {"head": "unknown_hat"}},
            {"equipment": ["iron_helm"]},
        ]
        for patch in cases:
            with self.subTest(patch=patch):
                self.assertEqual(self.write_player_patch(**patch).status, LoadStatus.MALFORMED)

    def test_nan_stats_rejected(self):
        self.manager.save(Player("Aria"), WorldState())
        text = self.path.read_text().replace('"durability": 5.0', '"durability": NaN')
        self.path.write_text(text)
        self.assertEqual(self.manager.load().status, LoadStatus.MALFORMED)

    def test_v2_save_migrates(self):
        v2 = {
            "schema_version": 2,
            "player": {
                "id": "abc", "name": "Old", "level": 2, "xp": 10, "position": {"x": 1, "y": 2},
                "stats": {"max_health": 130, "durability": 7},
                "magic_attributes": ["fire"], "equipped_weapon": "ash_spear",
                "known_spells": ["fire_bolt"], "selected_spell": "fire_bolt",
            },
            "world": {"time": 5.0},
        }
        self.path.write_text(json.dumps(v2))
        result = self.manager.load()
        self.assertEqual(result.status, LoadStatus.OK, result.error)
        self.assertIs(result.player.weapon, WEAPONS["ash_spear"])
        self.assertEqual(result.player.inventory.used_slots, 0)
        self.assertEqual(result.player.stats.durability, 7)

    def test_item_for_bare_weapon(self):
        self.assertIs(item_for(WEAPONS["oak_staff"]), get_item("oak_staff"))


class CombatStillValidTests(unittest.TestCase):
    def test_low_level_player_still_kills_armored_high_level_player(self):
        novice = Player("Novice", Stats(physical_strength=1), position=Vec2())
        novice.equip(get_item("steel_dagger"))
        veteran = Player("Veteran", Stats(max_health=20_000, durability=5_000), level=800, position=Vec2(40, 0))
        for item_id in ("iron_helm", "leather_jerkin", "leather_greaves", "leather_gloves", "traveler_boots"):
            veteran.equip(get_item(item_id))
        hits = 0
        while veteran.is_alive and hits < 100_000:
            novice.update(10)
            novice.stats.restore_stamina(1000)
            result = novice.weapon_attack(veteran)
            self.assertIn(result.outcome, (AttackOutcome.HIT,))
            self.assertGreater(result.damage, 0)
            hits += 1
        self.assertFalse(veteran.is_alive)


if __name__ == "__main__":
    unittest.main()
