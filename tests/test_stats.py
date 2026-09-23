import unittest

from game.core.stats import Stats


class StatsTests(unittest.TestCase):
    def test_pools_start_full(self):
        stats = Stats(max_health=80, max_mana=30, max_stamina=40)
        self.assertEqual((stats.health, stats.mana, stats.stamina), (80, 30, 40))

    def test_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            Stats(max_health=0)
        with self.assertRaises(ValueError):
            Stats(durability=-1)
        with self.assertRaises(ValueError):
            Stats(max_health=10, health=11)
        with self.assertRaises(ValueError):
            Stats(speed=float("nan"))
        with self.assertRaises(TypeError):
            Stats(agility="fast")
        with self.assertRaises(ValueError):
            Stats().take_damage(-5)

    def test_damage_clamps_at_zero_and_kills(self):
        stats = Stats(max_health=50)
        self.assertEqual(stats.take_damage(70), 50)
        self.assertEqual(stats.health, 0)
        self.assertFalse(stats.is_alive)

    def test_healing_limited_to_max(self):
        stats = Stats(max_health=100, health=90)
        self.assertEqual(stats.heal(25), 10)
        self.assertEqual(stats.health, 100)

    def test_dead_cannot_be_healed(self):
        stats = Stats(max_health=100)
        stats.take_damage(100)
        self.assertEqual(stats.heal(50), 0)
        self.assertEqual(stats.health, 0)

    def test_mana_limits(self):
        stats = Stats(max_mana=20)
        self.assertTrue(stats.consume_mana(15))
        self.assertFalse(stats.consume_mana(10))  # all-or-nothing
        self.assertEqual(stats.mana, 5)
        self.assertEqual(stats.restore_mana(100), 15)
        self.assertEqual(stats.mana, 20)

    def test_stamina_limits(self):
        stats = Stats(max_stamina=30)
        self.assertTrue(stats.consume_stamina(30))
        self.assertEqual(stats.stamina, 0)
        self.assertFalse(stats.consume_stamina(1))
        stats.restore_stamina(45)
        self.assertEqual(stats.stamina, 30)

    def test_round_trip_and_unknown_fields(self):
        stats = Stats(max_health=70, health=33, durability=4)
        self.assertEqual(Stats.from_dict(stats.to_dict()), stats)
        with self.assertRaises(ValueError):
            Stats.from_dict({"max_health": 10, "luck": 7})


if __name__ == "__main__":
    unittest.main()
