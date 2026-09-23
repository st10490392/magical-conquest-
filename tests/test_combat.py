import unittest

from game.core.combat import (
    MIN_DAMAGE,
    Attack,
    AttackOutcome,
    Cooldown,
    DamageType,
    calculate_damage,
    mitigate,
    resolve_attack,
    try_attack,
)
from game.core.entity import Entity
from game.core.stats import Stats
from game.core.vector import Vec2

PUNCH = Attack("punch", DamageType.PHYSICAL, base_power=10, scaling=1.0, reach=100)
SPARK = Attack("spark", DamageType.MAGIC, base_power=10, scaling=1.0, reach=100, mana_cost=5)


def make(name="E", level=1, **stats):
    return Entity(name, Stats(**stats), level=level)


class DamageCalculationTests(unittest.TestCase):
    def test_physical_damage_without_defense(self):
        attacker = make(physical_strength=15)
        defender = make(durability=0)
        self.assertAlmostEqual(calculate_damage(attacker, defender, PUNCH), 25)

    def test_durability_reduces_physical_damage(self):
        attacker = make(physical_strength=15)
        defender = make(durability=100)
        self.assertAlmostEqual(calculate_damage(attacker, defender, PUNCH), 12.5)

    def test_magic_resistance_reduces_magic_only(self):
        attacker = make(physical_strength=10, magic_power=10)
        resistant = make(magic_resistance=300, durability=0)
        self.assertAlmostEqual(calculate_damage(attacker, resistant, SPARK), 5.0)
        self.assertAlmostEqual(calculate_damage(attacker, resistant, PUNCH), 20.0)

    def test_mitigation_never_reaches_zero(self):
        self.assertGreater(mitigate(10, 1_000_000), 0)
        self.assertGreaterEqual(mitigate(0.1, 1_000_000), MIN_DAMAGE)
        self.assertEqual(mitigate(0, 50), 0)

    def test_level_is_not_a_damage_input(self):
        attacker = make(physical_strength=10)
        low = make(level=1, durability=20)
        high = make(level=500, durability=20)
        self.assertEqual(calculate_damage(attacker, low, PUNCH), calculate_damage(attacker, high, PUNCH))


class ResolveAttackTests(unittest.TestCase):
    def test_hit_applies_damage_and_costs(self):
        attacker = make(magic_power=10, max_mana=20)
        defender = make(max_health=100)
        result = resolve_attack(attacker, defender, SPARK)
        self.assertEqual(result.outcome, AttackOutcome.HIT)
        self.assertAlmostEqual(defender.stats.health, 80)
        self.assertEqual(attacker.stats.mana, 15)

    def test_not_enough_mana_costs_nothing(self):
        attacker = make(max_mana=3)
        defender = make()
        result = resolve_attack(attacker, defender, SPARK)
        self.assertEqual(result.outcome, AttackOutcome.NOT_ENOUGH_MANA)
        self.assertEqual(attacker.stats.mana, 3)
        self.assertEqual(defender.stats.health, defender.stats.max_health)

    def test_out_of_range(self):
        attacker = make()
        defender = Entity("far", Stats(), position=Vec2(500, 0))
        self.assertEqual(resolve_attack(attacker, defender, PUNCH).outcome, AttackOutcome.OUT_OF_RANGE)

    def test_death_detection_and_dead_targets_ignored(self):
        attacker = make(physical_strength=100)
        defender = make(max_health=50)
        result = resolve_attack(attacker, defender, PUNCH)
        self.assertTrue(result.killed)
        self.assertFalse(defender.is_alive)
        self.assertEqual(defender.death.killer_id, attacker.entity_id)
        self.assertEqual(defender.death.cause, "physical:punch")

        again = resolve_attack(attacker, defender, PUNCH)
        self.assertEqual(again.outcome, AttackOutcome.TARGET_DEAD)
        self.assertEqual(defender.stats.health, 0)
        self.assertEqual(defender.receive_damage(10), 0)

    def test_dead_attacker_cannot_attack(self):
        attacker = make(max_health=10)
        attacker.receive_damage(10)
        defender = make()
        self.assertEqual(resolve_attack(attacker, defender, PUNCH).outcome, AttackOutcome.ATTACKER_DEAD)

    def test_cooldown_gates_attacks(self):
        attacker, defender = make(), make(max_health=1000)
        cooldown = Cooldown()
        self.assertTrue(try_attack(attacker, defender, PUNCH, cooldown).landed)
        self.assertEqual(try_attack(attacker, defender, PUNCH, cooldown).outcome, AttackOutcome.ON_COOLDOWN)
        cooldown.tick(10)
        self.assertTrue(try_attack(attacker, defender, PUNCH, cooldown).landed)

    def test_lower_level_can_kill_much_higher_level(self):
        weakling = make("novice", level=1, physical_strength=5)
        titan = make(
            "titan",
            level=1000,
            max_health=20_000,
            durability=5_000,
            magic_resistance=5_000,
        )
        hits = 0
        while titan.is_alive and hits < 100_000:
            result = resolve_attack(weakling, titan, PUNCH)
            self.assertGreater(result.damage, 0)
            hits += 1
        self.assertFalse(titan.is_alive)
        self.assertEqual(titan.death.killer_id, weakling.entity_id)


if __name__ == "__main__":
    unittest.main()
