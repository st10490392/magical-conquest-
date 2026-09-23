import unittest

from game.core.combat import AttackOutcome
from game.core.vector import Vec2
from game.entities.enemy import EnemyState, create_goblin
from game.entities.player import FIRE_BOLT, MELEE_STRIKE, MovementState, Player


class PlayerTests(unittest.TestCase):
    def test_movement_state_and_speed(self):
        player = Player("Aria", position=Vec2(0, 0))
        player.move(Vec2(3, 4), dt=1.0)  # direction is normalized
        self.assertEqual(player.movement_state, MovementState.MOVING)
        self.assertAlmostEqual(player.position.length(), player.stats.speed)
        player.move(Vec2(), dt=1.0)
        self.assertEqual(player.movement_state, MovementState.IDLE)

    def test_dead_player_cannot_move(self):
        player = Player("Aria")
        player.receive_damage(10_000)
        player.move(Vec2(1, 0), dt=1.0)
        self.assertEqual(player.movement_state, MovementState.DEAD)
        self.assertEqual(player.position, Vec2())

    def test_magic_attack_uses_mana(self):
        player = Player("Aria")
        goblin = create_goblin(position=Vec2(100, 0))
        result = player.attack(goblin, FIRE_BOLT)
        self.assertTrue(result.landed)
        self.assertEqual(player.stats.mana, player.stats.max_mana - FIRE_BOLT.mana_cost)


class EnemyTests(unittest.TestCase):
    def test_enemy_chases_target_in_aggro_range(self):
        player = Player("Aria", position=Vec2(0, 0))
        goblin = create_goblin(position=Vec2(300, 0))
        goblin.update(0.5, player)
        self.assertEqual(goblin.state, EnemyState.CHASING)
        self.assertLess(goblin.distance_to(player), 300)

    def test_enemy_ignores_distant_target(self):
        player = Player("Aria", position=Vec2(0, 0))
        goblin = create_goblin(position=Vec2(2000, 0))
        goblin.update(0.5, player)
        self.assertEqual(goblin.state, EnemyState.IDLE)
        self.assertEqual(goblin.position, Vec2(2000, 0))

    def test_enemy_attacks_in_range_with_cooldown(self):
        player = Player("Aria", position=Vec2(0, 0))
        goblin = create_goblin(position=Vec2(30, 0))
        first = goblin.update(0.016, player)
        self.assertTrue(first.landed)
        self.assertLess(player.stats.health, player.stats.max_health)
        self.assertIsNone(goblin.update(0.016, player))  # still cooling down
        second = goblin.update(goblin.attack.cooldown, player)
        self.assertTrue(second.landed)

    def test_enemy_dies_through_combat(self):
        player = Player("Aria", position=Vec2(0, 0))
        goblin = create_goblin(position=Vec2(40, 0))
        swings = 0
        while goblin.is_alive and swings < 100:
            player.attack_cooldown.tick(10)
            player.stats.restore_stamina(100)
            player.attack(goblin, MELEE_STRIKE)
            swings += 1
        self.assertFalse(goblin.is_alive)
        self.assertIsNone(goblin.update(1.0, player))
        self.assertEqual(goblin.state, EnemyState.DEAD)
        player.attack_cooldown.tick(10)
        self.assertEqual(player.attack(goblin, MELEE_STRIKE).outcome, AttackOutcome.TARGET_DEAD)

    def test_higher_level_goblins_are_tougher(self):
        self.assertGreater(create_goblin(5).stats.max_health, create_goblin(1).stats.max_health)


if __name__ == "__main__":
    unittest.main()
