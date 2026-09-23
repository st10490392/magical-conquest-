import unittest

from game.core.combat import Attack, AttackOutcome, DamageType, resolve_attack
from game.core.defense import DefenseAction, DefenseConfig, GuardProfile
from game.core.entity import Entity
from game.core.stats import Stats
from game.core.vector import Vec2
from game.entities.player import MELEE_STRIKE, Player
from game.equipment.catalog import WEAPONS, get_weapon
from game.equipment.weapons import Weapon, WeaponType

HEAVY_BLOW = Attack("heavy_blow", DamageType.PHYSICAL, base_power=40, scaling=0.0, reach=100)
SPARK = Attack("spark", DamageType.MAGIC, base_power=40, scaling=0.0, reach=100)


def fighter(weapon_id=None, stamina=100.0, **stats):
    player = Player("Fighter", Stats(max_health=500, max_stamina=stamina, durability=0, **stats))
    if weapon_id:
        player.equip(get_weapon(weapon_id))
    return player


def attacker():
    return Entity("Brute", Stats(max_health=500), position=Vec2(30, 0))


class WeaponTests(unittest.TestCase):
    def test_catalog_covers_weapon_types(self):
        self.assertEqual({w.weapon_type for w in WEAPONS.values()}, set(WeaponType))
        with self.assertRaises(ValueError):
            get_weapon("dragon_slayer")

    def test_invalid_weapon_rejected(self):
        with self.assertRaises(ValueError):
            Weapon("w", "W", WeaponType.SWORD, base_power=5, block_capability=1.0)  # total block
        with self.assertRaises(ValueError):
            Weapon("w", "W", WeaponType.SWORD, base_power=-1)

    def test_equip_and_unequip(self):
        player = fighter()
        self.assertIsNone(player.weapon)
        sword, spear = WEAPONS["iron_sword"], WEAPONS["ash_spear"]
        self.assertIsNone(player.equip(sword))
        self.assertIs(player.weapon, sword)
        self.assertIs(player.equip(spear), sword)
        self.assertIs(player.unequip(), spear)
        self.assertIsNone(player.weapon)
        self.assertIsNone(player.unequip())

    def test_weapon_attack_damage_and_stamina(self):
        player = fighter("iron_greatsword", physical_strength=10)
        target = Entity("Dummy", Stats(max_health=500, durability=0), position=Vec2(80, 0))
        greatsword = player.weapon
        result = player.weapon_attack(target)
        self.assertTrue(result.landed)
        self.assertAlmostEqual(result.damage, greatsword.base_power + 10 * greatsword.strength_scaling)
        self.assertEqual(player.stats.stamina, 100 - greatsword.stamina_cost)

    def test_weapon_reach_differs(self):
        target = Entity("Dummy", Stats(max_health=500), position=Vec2(110, 0))
        self.assertEqual(fighter("iron_sword").weapon_attack(target).outcome, AttackOutcome.OUT_OF_RANGE)
        self.assertTrue(fighter("ash_spear").weapon_attack(target).landed)

    def test_weapon_attack_needs_stamina(self):
        player = fighter("iron_greatsword", stamina=10)
        target = Entity("Dummy", Stats(max_health=500), position=Vec2(50, 0))
        self.assertEqual(player.weapon_attack(target).outcome, AttackOutcome.NOT_ENOUGH_STAMINA)
        self.assertEqual(player.stats.stamina, 10)

    def test_unarmed_fallback(self):
        player = fighter(physical_strength=10)
        target = Entity("Dummy", Stats(max_health=500), position=Vec2(50, 0))
        result = player.weapon_attack(target)
        self.assertAlmostEqual(result.damage, MELEE_STRIKE.base_power + 10)


class BlockTests(unittest.TestCase):
    def test_block_requires_capable_weapon(self):
        self.assertEqual(fighter().start_block(), DefenseAction.NOT_CAPABLE)
        self.assertEqual(fighter("steel_dagger").start_block(), DefenseAction.NOT_CAPABLE)
        self.assertEqual(fighter("iron_sword").start_block(), DefenseAction.STARTED)

    def test_block_reduces_damage_and_costs_stamina(self):
        defender = fighter("iron_sword")  # block_capability 0.6
        defender.start_block()
        result = resolve_attack(attacker(), defender, HEAVY_BLOW)
        self.assertEqual(result.outcome, AttackOutcome.BLOCKED)
        self.assertAlmostEqual(result.absorbed, 24.0)
        self.assertAlmostEqual(result.damage, 16.0)  # never fully invulnerable
        self.assertAlmostEqual(defender.stats.stamina, 100 - 24.0 * defender.defense.config.block_stamina_per_damage)
        self.assertTrue(defender.defense.blocking)

    def test_block_breaks_when_stamina_runs_out(self):
        defender = fighter("iron_sword", stamina=4)  # can only afford 8 points of absorption
        defender.start_block()
        result = resolve_attack(attacker(), defender, HEAVY_BLOW)
        self.assertEqual(result.outcome, AttackOutcome.BLOCKED)
        self.assertTrue(result.guard_broken)
        self.assertAlmostEqual(result.absorbed, 8.0)
        self.assertAlmostEqual(result.damage, 32.0)
        self.assertEqual(defender.stats.stamina, 0)
        self.assertFalse(defender.defense.blocking)
        self.assertEqual(defender.start_block(), DefenseAction.NOT_ENOUGH_STAMINA)
        self.assertEqual(resolve_attack(attacker(), defender, HEAVY_BLOW).outcome, AttackOutcome.HIT)

    def test_block_not_applied_when_not_blocking(self):
        defender = fighter("iron_sword")
        self.assertEqual(resolve_attack(attacker(), defender, HEAVY_BLOW).outcome, AttackOutcome.HIT)

    def test_guard_cannot_be_total(self):
        with self.assertRaises(ValueError):
            GuardProfile(block_capability=1.0)


class ParryTests(unittest.TestCase):
    def test_successful_parry_negates_attack(self):
        defender = fighter("iron_sword")
        self.assertEqual(defender.parry(), DefenseAction.STARTED)
        self.assertEqual(defender.stats.stamina, 100 - defender.defense.config.parry_stamina_cost)
        result = resolve_attack(attacker(), defender, HEAVY_BLOW)
        self.assertEqual(result.outcome, AttackOutcome.PARRIED)
        self.assertEqual(result.damage, 0)
        self.assertEqual(defender.stats.health, defender.stats.max_health)

    def test_attack_after_window_hits(self):
        defender = fighter("iron_sword")
        defender.parry()
        defender.update(defender.defense.config.parry_window + 0.01)
        result = resolve_attack(attacker(), defender, HEAVY_BLOW)
        self.assertEqual(result.outcome, AttackOutcome.HIT)
        self.assertAlmostEqual(result.damage, 40.0)

    def test_parry_requires_capable_weapon_and_recovery(self):
        self.assertEqual(fighter("iron_greatsword").parry(), DefenseAction.NOT_CAPABLE)
        self.assertEqual(fighter().parry(), DefenseAction.NOT_CAPABLE)
        defender = fighter("steel_dagger")
        self.assertEqual(defender.parry(), DefenseAction.STARTED)
        self.assertEqual(defender.parry(), DefenseAction.ON_COOLDOWN)
        defender.update(defender.defense.config.parry_recovery)
        self.assertEqual(defender.parry(), DefenseAction.STARTED)

    def test_parry_needs_stamina(self):
        defender = fighter("iron_sword", stamina=5)
        self.assertEqual(defender.parry(), DefenseAction.NOT_ENOUGH_STAMINA)

    def test_weapons_do_not_parry_spells_by_default(self):
        defender = fighter("iron_sword")
        defender.parry()
        self.assertEqual(resolve_attack(attacker(), defender, SPARK).outcome, AttackOutcome.HIT)

    def test_parry_config_is_adjustable(self):
        config = DefenseConfig(parry_damage_ratio=0.25, parry_affects_magic=True)
        defender = Player("Custom", Stats(max_health=500, durability=0, magic_resistance=0))
        defender.defense.config = config
        defender.equip(WEAPONS["iron_sword"])
        defender.parry()
        result = resolve_attack(attacker(), defender, SPARK)
        self.assertEqual(result.outcome, AttackOutcome.PARRIED)
        self.assertAlmostEqual(result.damage, 10.0)


class DodgeTests(unittest.TestCase):
    def test_dodge_evades_inside_window(self):
        defender = fighter()
        self.assertEqual(defender.dodge(), DefenseAction.STARTED)
        self.assertEqual(defender.stats.stamina, 100 - defender.defense.config.dodge_stamina_cost)
        result = resolve_attack(attacker(), defender, HEAVY_BLOW)
        self.assertEqual(result.outcome, AttackOutcome.DODGED)
        self.assertEqual(defender.stats.health, defender.stats.max_health)
        magic = resolve_attack(attacker(), defender, SPARK)
        self.assertEqual(magic.outcome, AttackOutcome.DODGED)

    def test_attack_after_dodge_window_hits(self):
        defender = fighter()
        defender.dodge()
        defender.update(defender.defense.config.dodge_duration + 0.01)
        self.assertEqual(resolve_attack(attacker(), defender, HEAVY_BLOW).outcome, AttackOutcome.HIT)

    def test_dodge_cooldown_prevents_spam(self):
        defender = fighter()
        config = defender.defense.config
        self.assertEqual(defender.dodge(), DefenseAction.STARTED)
        defender.update(config.dodge_duration + 0.01)
        self.assertEqual(defender.dodge(), DefenseAction.ON_COOLDOWN)
        defender.update(config.dodge_cooldown)
        self.assertEqual(defender.dodge(), DefenseAction.STARTED)

    def test_dodge_needs_stamina_and_drops_block(self):
        tired = fighter("iron_sword", stamina=10)
        self.assertEqual(tired.dodge(), DefenseAction.NOT_ENOUGH_STAMINA)
        blocker = fighter("iron_sword")
        blocker.start_block()
        blocker.dodge()
        self.assertFalse(blocker.defense.blocking)

    def test_dodged_attack_still_costs_attacker(self):
        defender = fighter()
        striker = Player("Striker", position=Vec2(30, 0))
        striker.equip(WEAPONS["iron_sword"])
        defender.dodge()
        result = striker.weapon_attack(defender)
        self.assertEqual(result.outcome, AttackOutcome.DODGED)
        self.assertTrue(result.executed)
        self.assertFalse(result.landed)
        self.assertEqual(striker.stats.stamina, striker.stats.max_stamina - WEAPONS["iron_sword"].stamina_cost)
        self.assertFalse(striker.attack_cooldown.ready)

    def test_invalid_config(self):
        with self.assertRaises(ValueError):
            DefenseConfig(dodge_duration=1.0, dodge_cooldown=0.5)


if __name__ == "__main__":
    unittest.main()
