"""MC-003 enemy AI: perception, lifecycle, archetypes and defensive interplay.

Everything is headless and deterministic.
"""

import unittest

from game.ai.attacks import AttackLifecycle, AttackPhase, EnemyAttack
from game.ai.coordination import AttackCoordinator
from game.ai.perception import PerceptionConfig, perceive
from game.ai.projectiles import ProjectileSystem
from game.ai.space import CombatSpace
from game.ai.states import AIState
from game.core.combat import Attack, AttackOutcome, DamageType
from game.core.stats import Stats
from game.core.vector import Vec2
from game.entities.archetypes import ARCHER, ARCHETYPES, BRUTE, STRIKER, create_enemy
from game.entities.player import Player
from game.equipment.catalog import WEAPONS

DT = 1 / 60
BOUNDS = (0.0, 0.0, 800.0, 600.0)


def player_at(x=0.0, y=300.0, weapon="iron_sword", **stats):
    player = Player("Tester", Stats(**stats) if stats else None, position=Vec2(x, y))
    if weapon:
        player.equip(WEAPONS[weapon])
    return player


def tick(enemy, player, seconds, space=None, player_update=True):
    """Advance enemy (and player timers) in DT steps; collect results."""
    results = []
    for _ in range(round(seconds / DT)):
        if player_update:
            player.update(DT)
        result = enemy.update(DT, player, space=space)
        if result is not None:
            results.append(result)
        if space is not None and space.projectiles is not None:
            results.extend(hit.result for hit in space.projectiles.update(DT))
    return results


def run_until(enemy, player, predicate, limit=20.0, space=None):
    for _ in range(round(limit / DT)):
        player.update(DT)
        enemy.update(DT, player, space=space)
        if space is not None and space.projectiles is not None:
            space.projectiles.update(DT)
        if predicate():
            return
    raise AssertionError("condition never reached")


def space():
    return CombatSpace(BOUNDS, ProjectileSystem(), AttackCoordinator(1))


class PerceptionTests(unittest.TestCase):
    def test_detection_and_hysteresis(self):
        config = PerceptionConfig(detection_range=100, disengage_range=200)
        observer = create_enemy("striker", position=Vec2(0, 0))
        target = player_at(150, 0)
        self.assertFalse(perceive(observer, target, config, was_engaged=False).engaged)
        self.assertTrue(perceive(observer, target, config, was_engaged=True).engaged)
        target.position = Vec2(250, 0)
        self.assertFalse(perceive(observer, target, config, was_engaged=True).engaged)

    def test_invalid_targets(self):
        observer = create_enemy("striker")
        config = PerceptionConfig()
        self.assertFalse(perceive(observer, None, config, False).valid)
        dead = player_at(10, 0)
        dead.receive_damage(10_000)
        self.assertFalse(perceive(observer, dead, config, True).valid)
        self.assertFalse(perceive(observer, observer, config, True).valid)

    def test_bad_config(self):
        with self.assertRaises(ValueError):
            PerceptionConfig(detection_range=300, disengage_range=200)

    def test_enemy_ignores_target_outside_detection(self):
        enemy = create_enemy("striker", position=Vec2(700, 300))
        player = player_at(100, 300)
        tick(enemy, player, 2.0)
        self.assertEqual(enemy.state, AIState.IDLE)
        self.assertEqual(enemy.position, Vec2(700, 300))

    def test_alert_then_approach(self):
        enemy = create_enemy("striker", position=Vec2(400, 300))
        player = player_at(100, 300)
        enemy.update(DT, player)
        self.assertEqual(enemy.state, AIState.ALERT)
        start = enemy.position
        tick(enemy, player, STRIKER.alert_time + 2 * DT)
        self.assertEqual(enemy.state, AIState.APPROACH)
        self.assertLess(enemy.distance_to(player), start.distance_to(player.position))

    def test_disengages_when_target_escapes(self):
        enemy = create_enemy("striker", position=Vec2(400, 300))
        player = player_at(100, 300)
        tick(enemy, player, 0.5)
        self.assertTrue(enemy.engaged)
        player.position = Vec2(enemy.position.x - 2000, 300)
        tick(enemy, player, DT)
        self.assertFalse(enemy.engaged)
        self.assertEqual(enemy.state, AIState.IDLE)


class LifecycleTests(unittest.TestCase):
    def test_lifecycle_phases(self):
        profile = EnemyAttack(Attack("x", DamageType.PHYSICAL, 1), telegraph=0.5, recovery=0.3)
        life = AttackLifecycle()
        life.start(profile)
        self.assertEqual(life.phase, AttackPhase.TELEGRAPH)
        self.assertFalse(life.tick_telegraph(0.4))
        self.assertTrue(life.tick_telegraph(0.1))
        life.begin_recovery()
        self.assertEqual(life.phase, AttackPhase.RECOVERY)
        self.assertFalse(life.tick_recovery(0.2))
        self.assertTrue(life.tick_recovery(0.1))
        self.assertFalse(life.busy)

    def test_invalid_profiles(self):
        attack = Attack("x", DamageType.PHYSICAL, 1)
        with self.assertRaises(ValueError):
            EnemyAttack(attack, telegraph=-1)
        with self.assertRaises(ValueError):
            EnemyAttack(attack, projectile_speed=0)

    def test_telegraph_before_damage_then_hit_then_recovery(self):
        enemy = create_enemy("striker", position=Vec2(140, 300))
        player = player_at(100, 300)
        run_until(enemy, player, lambda: enemy.state is AIState.TELEGRAPH)
        hp = player.stats.health
        # Nothing lands during the wind-up.
        results = tick(enemy, player, STRIKER.attack.telegraph - 2 * DT)
        self.assertEqual(results, [])
        self.assertEqual(player.stats.health, hp)
        self.assertEqual(enemy.state, AIState.TELEGRAPH)
        # It resolves at the end of the wind-up through normal combat.
        results = tick(enemy, player, 3 * DT)
        self.assertEqual([r.outcome for r in results], [AttackOutcome.HIT])
        self.assertLess(player.stats.health, hp)
        # Then it is committed to its recovery: no movement, no attacks.
        self.assertEqual(enemy.state, AIState.RECOVER)
        position = enemy.position
        player.position = Vec2(player.position.x - 60, 300)
        tick(enemy, player, STRIKER.attack.recovery - 3 * DT)
        self.assertEqual(enemy.state, AIState.RECOVER)
        self.assertEqual(enemy.position, position)

    def test_cooldown_spaces_attacks(self):
        enemy = create_enemy("striker", position=Vec2(140, 300))
        player = player_at(100, 300, max_health=5000)
        results = tick(enemy, player, 6.0)
        hits = [r for r in results if r.landed]
        self.assertGreaterEqual(len(hits), 3)
        # telegraph + cooldown (from release) bound the rate of attacks
        interval = STRIKER.attack.telegraph + STRIKER.attack.attack.cooldown
        self.assertLessEqual(len(hits), int(6.0 / interval) + 1)

    def test_whiff_when_target_leaves_reach(self):
        enemy = create_enemy("brute", position=Vec2(200, 300))
        player = player_at(100, 300, max_health=5000)
        run_until(enemy, player, lambda: enemy.state is AIState.TELEGRAPH)
        player.position = Vec2(player.position.x, 450)  # sidestep away from the aim point
        results = tick(enemy, player, BRUTE.attack.telegraph + DT)
        self.assertEqual([r.outcome for r in results], [AttackOutcome.OUT_OF_RANGE])
        self.assertEqual(player.stats.health, player.stats.max_health)
        self.assertEqual(enemy.state, AIState.RECOVER)

    def test_telegraph_cancelled_if_target_dies(self):
        enemy = create_enemy("striker", position=Vec2(140, 300))
        player = player_at(100, 300)
        run_until(enemy, player, lambda: enemy.state is AIState.TELEGRAPH)
        player.receive_damage(10_000)
        enemy.update(DT, player)
        self.assertEqual(enemy.state, AIState.IDLE)
        self.assertFalse(enemy.lifecycle.busy)


class ArchetypeTests(unittest.TestCase):
    def test_catalog(self):
        self.assertEqual(set(ARCHETYPES), {"striker", "archer", "brute"})
        with self.assertRaises(ValueError):
            create_enemy("dragon")
        self.assertGreater(create_enemy("brute", 5).stats.max_health, create_enemy("brute", 1).stats.max_health)

    def test_striker_tracks_during_telegraph(self):
        enemy = create_enemy("striker", position=Vec2(140, 300))
        player = player_at(100, 300, max_health=5000)
        run_until(enemy, player, lambda: enemy.state is AIState.TELEGRAPH)
        player.position = Vec2(player.position.x - 30, 300)  # small backstep
        before = enemy.position
        tick(enemy, player, 0.2)
        self.assertLess(enemy.position.x, before.x)  # it follows

    def test_brute_is_rooted_during_telegraph_and_slower(self):
        enemy = create_enemy("brute", position=Vec2(250, 300))
        player = player_at(100, 300, max_health=5000)
        run_until(enemy, player, lambda: enemy.state is AIState.TELEGRAPH)
        before = enemy.position
        player.position = Vec2(player.position.x - 30, 300)
        tick(enemy, player, BRUTE.attack.telegraph / 2)
        self.assertEqual(enemy.position, before)  # committed: no tracking
        self.assertLess(BRUTE.stats["speed"], STRIKER.stats["speed"])
        self.assertGreater(BRUTE.attack.telegraph, STRIKER.attack.telegraph)
        self.assertGreater(BRUTE.attack.recovery, STRIKER.attack.recovery)

    def test_brute_lunges_to_its_aim_point(self):
        enemy = create_enemy("brute", position=Vec2(200, 300))
        player = player_at(100, 300, max_health=5000)
        run_until(enemy, player, lambda: enemy.state is AIState.TELEGRAPH)
        start = enemy.position
        results = tick(enemy, player, BRUTE.attack.telegraph + DT)
        self.assertLess(enemy.position.x, start.x)
        self.assertTrue(results[0].landed)
        self.assertEqual(enemy.state, AIState.RECOVER)
        self.assertGreater(results[0].damage, 25)  # the slam is the heavy hit

    def test_archer_retreats_when_too_close(self):
        enemy = create_enemy("archer", position=Vec2(400, 300))
        player = player_at(300, 300)
        tick(enemy, player, ARCHER.alert_time + 0.5, space=space())
        self.assertEqual(enemy.state, AIState.RETREAT)
        self.assertGreater(enemy.distance_to(player), 100)

    def test_archer_slides_along_walls_when_cornered(self):
        enemy = create_enemy("archer", position=Vec2(770, 300))
        player = player_at(680, 300)
        tick(enemy, player, 1.0, space=space())
        self.assertNotEqual(enemy.position.y, 300)  # escaped sideways
        self.assertLessEqual(enemy.position.x, 800 - enemy.size / 2)

    def test_archer_approaches_to_band_and_shoots(self):
        enemy = create_enemy("archer", position=Vec2(560, 300))
        player = player_at(100, 300, max_health=5000)
        arena = space()
        run_until(enemy, player, lambda: enemy.state is AIState.TELEGRAPH, space=arena)
        distance = enemy.distance_to(player)
        self.assertGreaterEqual(distance, 170)
        self.assertLessEqual(distance, 360)
        tick(enemy, player, ARCHER.attack.telegraph + DT, space=arena)
        self.assertEqual(len(arena.projectiles.projectiles), 1)  # an arrow is in flight
        hp = player.stats.health
        results = tick(enemy, player, 1.0, space=arena)
        self.assertTrue(any(r.landed for r in results))
        self.assertLess(player.stats.health, hp)

    def test_arrow_can_be_sidestepped(self):
        enemy = create_enemy("archer", position=Vec2(400, 300))
        player = player_at(100, 300, max_health=5000)
        arena = space()
        run_until(enemy, player, lambda: enemy.state is AIState.RECOVER, space=arena)
        player.position = Vec2(player.position.x, 380)  # step off the arrow's line
        results = tick(enemy, player, 1.0, space=arena)
        self.assertFalse(any(r.landed for r in results))
        self.assertEqual(player.stats.health, player.stats.max_health)

    def test_archer_cooldown(self):
        enemy = create_enemy("archer", position=Vec2(350, 300))
        player = player_at(100, 300, max_health=5000)
        arena = space()
        tick(enemy, player, 5.0, space=arena)
        launched = 0
        results = tick(enemy, player, 0.0, space=arena)
        self.assertEqual(results, [])
        # Count telegraph starts over a fixed window.
        for _ in range(round(6.0 / DT)):
            before = enemy.state
            enemy.update(DT, player, space=arena)
            arena.projectiles.update(DT)
            if enemy.state is AIState.TELEGRAPH and before is not AIState.TELEGRAPH:
                launched += 1
        interval = ARCHER.attack.telegraph + ARCHER.attack.attack.cooldown
        self.assertLessEqual(launched, int(6.0 / interval) + 1)
        self.assertGreaterEqual(launched, 2)


class DefensiveInteractionTests(unittest.TestCase):
    def ready_to_strike(self, archetype="striker"):
        enemy = create_enemy(archetype, position=Vec2(140, 300))
        player = player_at(100, 300, max_health=5000)
        run_until(enemy, player, lambda: enemy.state is AIState.TELEGRAPH)
        # Advance to just before the release.
        while enemy.windup_remaining > 3 * DT:
            player.update(DT)
            enemy.update(DT, player)
        return enemy, player

    def test_dodge_avoids_enemy_attack(self):
        enemy, player = self.ready_to_strike()
        player.dodge()
        results = tick(enemy, player, 5 * DT)
        self.assertEqual([r.outcome for r in results], [AttackOutcome.DODGED])
        self.assertEqual(player.stats.health, player.stats.max_health)

    def test_block_reduces_enemy_attack(self):
        enemy, player = self.ready_to_strike()
        player.start_block()
        results = tick(enemy, player, 5 * DT)
        self.assertEqual(results[0].outcome, AttackOutcome.BLOCKED)
        self.assertGreater(results[0].damage, 0)
        self.assertLess(player.stats.stamina, player.stats.max_stamina)

    def test_parry_negates_and_staggers(self):
        enemy, player = self.ready_to_strike()
        player.parry()
        results = tick(enemy, player, 5 * DT)
        self.assertEqual(results[0].outcome, AttackOutcome.PARRIED)
        self.assertEqual(player.stats.health, player.stats.max_health)
        self.assertEqual(enemy.state, AIState.STAGGERED)
        self.assertGreater(enemy.stagger_remaining, STRIKER.parry_stagger - 0.1)
        # Staggered enemies do nothing, which opens a punish window.
        position = enemy.position
        tick(enemy, player, STRIKER.parry_stagger - 0.1)
        self.assertEqual(enemy.state, AIState.STAGGERED)
        self.assertEqual(enemy.position, position)
        tick(enemy, player, 0.2)
        self.assertNotEqual(enemy.state, AIState.STAGGERED)

    def test_parry_too_early_is_not_a_parry(self):
        enemy = create_enemy("brute", position=Vec2(140, 300))
        player = player_at(100, 300, max_health=5000)
        run_until(enemy, player, lambda: enemy.state is AIState.TELEGRAPH)
        player.parry()  # the brute's wind-up is far longer than the parry window
        results = tick(enemy, player, BRUTE.attack.telegraph + DT)
        self.assertEqual(results[0].outcome, AttackOutcome.HIT)
        self.assertNotEqual(enemy.state, AIState.STAGGERED)

    def test_player_punishes_recovery(self):
        enemy = create_enemy("brute", position=Vec2(200, 300))
        player = player_at(100, 300, max_health=5000, physical_strength=10)
        run_until(enemy, player, lambda: enemy.state is AIState.RECOVER)
        hp = enemy.stats.health
        swings = 0
        while enemy.state is AIState.RECOVER:
            if player.weapon_attack(enemy).landed:
                swings += 1
            tick(enemy, player, DT)
        self.assertGreaterEqual(swings, 2)
        self.assertLess(enemy.stats.health, hp)

    def test_enemy_death_through_combat(self):
        enemy = create_enemy("striker", position=Vec2(140, 300))
        player = player_at(100, 300, max_health=5000, physical_strength=30)
        while enemy.is_alive:
            player.update(10.0)
            player.stats.restore_stamina(1000)
            player.weapon_attack(enemy)
        self.assertIsNone(enemy.update(DT, player))
        self.assertEqual(enemy.state, AIState.DEAD)

    def test_player_death_by_enemy(self):
        enemy = create_enemy("brute", position=Vec2(140, 300))
        player = player_at(100, 300, max_health=50)
        results = tick(enemy, player, 10.0)
        self.assertFalse(player.is_alive)
        self.assertTrue(results[-1].killed)
        self.assertEqual(player.death.killer_id, enemy.entity_id)
        tick(enemy, player, 1.0)
        self.assertEqual(enemy.state, AIState.IDLE)

    def test_weak_player_can_kill_brute_given_enough_hits(self):
        brute = create_enemy("brute", level=50, position=Vec2(140, 300))
        novice = player_at(100, 300, weapon="steel_dagger", physical_strength=1)
        hits = 0
        while brute.is_alive and hits < 100_000:
            novice.update(10.0)
            novice.stats.restore_stamina(1000)
            result = novice.weapon_attack(brute)
            self.assertGreater(result.damage, 0)
            hits += 1
        self.assertFalse(brute.is_alive)


class CoordinatorTests(unittest.TestCase):
    def test_tokens(self):
        coordinator = AttackCoordinator(1)
        a, b = create_enemy("striker"), create_enemy("brute")
        self.assertTrue(coordinator.try_acquire(a))
        self.assertTrue(coordinator.try_acquire(a))  # re-entrant
        self.assertFalse(coordinator.try_acquire(b))
        coordinator.release(a)
        self.assertTrue(coordinator.try_acquire(b))
        with self.assertRaises(ValueError):
            AttackCoordinator(0)

    def test_two_melee_enemies_take_turns(self):
        arena = space()
        player = player_at(300, 300, max_health=100_000)
        a = create_enemy("striker", position=Vec2(345, 300))
        b = create_enemy("striker", position=Vec2(255, 300))
        overlaps = 0
        for _ in range(round(8 / DT)):
            player.update(DT)
            a.update(DT, player, space=arena)
            b.update(DT, player, space=arena)
            if a.state is AIState.TELEGRAPH and b.state is AIState.TELEGRAPH:
                overlaps += 1
        self.assertEqual(overlaps, 0)
        self.assertLess(player.stats.health, player.stats.max_health)

    def test_dead_enemy_releases_token(self):
        arena = space()
        player = player_at(100, 300, max_health=5000)
        enemy = create_enemy("striker", position=Vec2(140, 300))
        run_until(enemy, player, lambda: enemy.state is AIState.TELEGRAPH, space=arena)
        self.assertTrue(arena.coordinator.holds(enemy))
        enemy.receive_damage(10_000)
        enemy.update(DT, player, space=arena)
        self.assertFalse(arena.coordinator.holds(enemy))


if __name__ == "__main__":
    unittest.main()
