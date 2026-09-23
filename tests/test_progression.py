import unittest

from game.entities.player import Player
from game.progression.experience import Experience, ProgressionCurve


class ExperienceTests(unittest.TestCase):
    def test_curve_is_formula_based(self):
        curve = ProgressionCurve(base=100, exponent=1.5)
        self.assertEqual(curve.xp_to_next(1), 100)
        self.assertEqual(curve.xp_to_next(4), 800)
        # Very high levels are just arithmetic, no table.
        self.assertGreater(curve.xp_to_next(500_000), curve.xp_to_next(499_999))

    def test_gain_without_level_up(self):
        exp = Experience()
        result = exp.add(1, 40)
        self.assertEqual((result.new_level, exp.xp), (1, 40))

    def test_single_level_up_carries_remainder(self):
        exp = Experience(curve=ProgressionCurve(base=100, exponent=1.0))
        result = exp.add(1, 130)
        self.assertEqual((result.new_level, exp.xp), (2, 30))

    def test_multiple_level_ups(self):
        exp = Experience(curve=ProgressionCurve(base=100, exponent=1.0))
        # 100 (L1) + 200 (L2) + 300 (L3) = 600 -> level 4 with 50 left over.
        result = exp.add(1, 650)
        self.assertEqual(result.levels_gained, 3)
        self.assertEqual((result.new_level, exp.xp), (4, 50))

    def test_max_level_cap(self):
        exp = Experience(curve=ProgressionCurve(base=10, exponent=0, max_level=3))
        result = exp.add(1, 1000)
        self.assertEqual((result.new_level, exp.xp), (3, 0))

    def test_rejects_invalid_xp(self):
        with self.assertRaises(ValueError):
            Experience(-1)
        with self.assertRaises(ValueError):
            Experience().add(1, -5)


class PlayerProgressionTests(unittest.TestCase):
    def test_player_level_up_grows_stats(self):
        player = Player("Aria", curve=ProgressionCurve(base=100, exponent=1.0))
        before = player.stats.max_health
        player.stats.take_damage(50)
        result = player.gain_xp(300)  # L1 -> L3
        self.assertEqual(result.levels_gained, 2)
        self.assertEqual(player.level, 3)
        self.assertEqual(player.stats.max_health, before + 2 * player.growth.max_health)
        self.assertEqual(player.stats.health, player.stats.max_health)


if __name__ == "__main__":
    unittest.main()
