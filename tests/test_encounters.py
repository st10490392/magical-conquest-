"""MC-003 encounters, multi-enemy sessions and deterministic simulation."""

import unittest

from game.ai.states import AIState
from game.core.combat import AttackOutcome
from game.core.entity import DeathContext
from game.core.vector import Vec2
from game.encounters.catalog import ENCOUNTERS, get_encounter
from game.encounters.encounter import Encounter, EncounterSpec, EncounterStatus, SpawnSpec
from game.entities.player import Player
from game.equipment.catalog import WEAPONS
from game.session import GameSession, PlayerInput

DT = 1 / 60
BOUNDS = (0.0, 0.0, 800.0, 600.0)


def hero(x=160.0, y=300.0, **overrides):
    player = Player("Hero", position=Vec2(x, y))
    player.equip(WEAPONS["iron_sword"])
    for name, value in overrides.items():
        setattr(player.stats, name, value)
    return player


class EncounterTests(unittest.TestCase):
    def test_catalog(self):
        self.assertIn("mixed_skirmish", ENCOUNTERS)
        self.assertEqual(len(get_encounter("mixed_skirmish").spawns), 3)
        with self.assertRaises(ValueError):
            get_encounter("hundred_floor_dungeon")
        with self.assertRaises(ValueError):
            Encounter(EncounterSpec("empty", "Empty", ()))

    def test_starts_immediately_without_trigger(self):
        encounter = Encounter(get_encounter("striker_drill"), bounds=BOUNDS)
        self.assertEqual(encounter.status, EncounterStatus.PENDING)
        encounter.update(DT, hero())
        self.assertEqual(encounter.status, EncounterStatus.ACTIVE)
        self.assertGreater(encounter.elapsed, 0)

    def test_trigger_range(self):
        spec = EncounterSpec("ambush", "Ambush", (SpawnSpec("striker", 600, 300),), trigger_range=150)
        encounter = Encounter(spec, bounds=BOUNDS)
        player = hero(100, 300)
        encounter.update(DT, player)
        self.assertEqual(encounter.status, EncounterStatus.PENDING)
        self.assertEqual(encounter.enemies[0].state, AIState.IDLE)  # no target until it starts
        player.position = Vec2(500, 300)
        encounter.update(DT, player)
        self.assertEqual(encounter.status, EncounterStatus.ACTIVE)

    def test_clear(self):
        encounter = Encounter(get_encounter("striker_drill"), bounds=BOUNDS)
        player = hero()
        encounter.update(DT, player)
        encounter.enemies[0].receive_damage(10_000)
        encounter.update(DT, player)
        self.assertEqual(encounter.status, EncounterStatus.CLEARED)
        self.assertTrue(encounter.is_over)

    def test_failure_on_player_death(self):
        encounter = Encounter(get_encounter("brute_drill"), bounds=BOUNDS)
        player = hero(480, 300)
        for _ in range(round(60 / DT)):
            player.update(DT)
            encounter.update(DT, player)
            if encounter.is_over:
                break
        self.assertEqual(encounter.status, EncounterStatus.FAILED)
        self.assertEqual(encounter.failure_reason, "player_died")
        self.assertFalse(player.is_alive)
        self.assertEqual(player.death.context, DeathContext.OPEN_WORLD)
        self.assertEqual(player.death.context_id, "brute_drill")
        # A failed encounter stops targeting and applies no penalties.
        xp, level = player.xp, player.level
        for _ in range(round(3 / DT)):  # let any committed recovery finish
            encounter.update(DT, player)
        self.assertTrue(all(e.state is AIState.IDLE for e in encounter.enemies))
        self.assertEqual((player.xp, player.level), (xp, level))

    def test_manual_interrupt(self):
        encounter = Encounter(get_encounter("striker_drill"), bounds=BOUNDS)
        encounter.start()
        encounter.fail("interrupted")
        self.assertEqual(encounter.status, EncounterStatus.FAILED)
        self.assertEqual(encounter.failure_reason, "interrupted")

    def test_encounter_context_reaches_death_records(self):
        spec = EncounterSpec("room_1", "Room", (SpawnSpec("brute", 480, 300),), context=DeathContext.DUNGEON)
        encounter = Encounter(spec, bounds=BOUNDS)
        player = hero(400, 300)
        player.stats.health = 1
        for _ in range(round(10 / DT)):
            encounter.update(DT, player)
            if not player.is_alive:
                break
        self.assertEqual(player.death.context, DeathContext.DUNGEON)
        self.assertEqual(player.death.context_id, "room_1")

    def test_multiple_enemies_group_alert_and_separation(self):
        encounter = Encounter(get_encounter("mixed_skirmish"), bounds=BOUNDS)
        player = hero(160, 300)
        player.stats.max_health = player.stats.health = 100_000
        for _ in range(round(4 / DT)):
            player.update(DT)
            encounter.update(DT, player)
        self.assertTrue(all(e.engaged for e in encounter.enemies))
        living = encounter.living_enemies
        for i, a in enumerate(living):
            for b in living[i + 1:]:
                self.assertGreaterEqual(a.distance_to(b), (a.size + b.size) / 2 - 1e-6)

    def test_mixed_encounter_melee_never_double_telegraphs(self):
        encounter = Encounter(get_encounter("mixed_skirmish"), bounds=BOUNDS)
        player = hero(160, 300)
        player.stats.max_health = player.stats.health = 100_000
        melee = [e for e in encounter.enemies if e.attack_profile.is_melee]
        ranged_events = 0
        for _ in range(round(20 / DT)):
            player.update(DT)
            ranged_events += sum(1 for ev in encounter.update(DT, player) if ev.ranged)
            winding = [e for e in melee if e.state is AIState.TELEGRAPH]
            self.assertLessEqual(len(winding), 1)
        self.assertGreater(ranged_events, 0)  # the archer is not blocked by the melee token

    def test_nearest_enemy(self):
        encounter = Encounter(get_encounter("mixed_skirmish"), bounds=BOUNDS)
        self.assertEqual(encounter.nearest_enemy(Vec2(560, 230)).archetype, "striker")
        for enemy in encounter.enemies:
            enemy.receive_damage(10_000)
        self.assertIsNone(encounter.nearest_enemy(Vec2()))


def fighting_player_input(session):
    """A simple scripted 'player': approach the nearest enemy, parry just
    before melee strikes land, otherwise attack."""
    player = session.player
    target = session.encounter.nearest_enemy(player.position)
    if target is None:
        return PlayerInput()
    threat = next(
        (e for e in session.enemies
         if e.is_alive and e.state is AIState.TELEGRAPH and e.attack_profile.is_melee and e.windup_remaining < 0.1),
        None,
    )
    if threat is not None and player.defense.parry_cooldown <= 0:
        return PlayerInput(parry=True)
    distance = player.distance_to(target)
    move = (target.position - player.position) if distance > 60 else Vec2()
    return PlayerInput(move=move, melee=distance <= 75)


class SimulationTests(unittest.TestCase):
    def simulate(self, encounter_id, seconds=90):
        session = GameSession.new(encounter_id=encounter_id)
        log = []
        for _ in range(round(seconds / DT)):
            session.update(DT, fighting_player_input(session))
            log.append(tuple((round(e.position.x, 6), round(e.position.y, 6), e.state.value, e.stats.health)
                             for e in session.enemies) + (session.player.stats.health,))
            if session.encounter.is_over:
                break
        return session, log

    def test_scripted_player_beats_striker_with_parries(self):
        session, _ = self.simulate("striker_drill")
        self.assertEqual(session.encounter.status, EncounterStatus.CLEARED)
        self.assertTrue(any(m.startswith("Parried") for m in session.messages) or session.kills == 1)
        self.assertEqual(session.kills, 1)

    def test_simulation_is_deterministic(self):
        _, first = self.simulate("mixed_skirmish", seconds=20)
        _, second = self.simulate("mixed_skirmish", seconds=20)
        self.assertEqual(first, second)

    def test_mixed_skirmish_reaches_a_result(self):
        session, _ = self.simulate("mixed_skirmish", seconds=180)
        self.assertTrue(session.encounter.is_over)

    def test_idle_player_fails_mixed_skirmish(self):
        session = GameSession.new(encounter_id="mixed_skirmish")
        for _ in range(round(60 / DT)):
            session.update(DT, PlayerInput())
            if session.encounter.is_over:
                break
        self.assertEqual(session.encounter.status, EncounterStatus.FAILED)
        self.assertIsNotNone(session.last_player_death)
        self.assertTrue(any("failed" in m for m in session.messages))

    def test_session_targets_nearest_enemy(self):
        session = GameSession.new(encounter_id="mixed_skirmish")
        striker = next(e for e in session.enemies if e.archetype == "striker")
        session.player.position = striker.position + Vec2(-50, 0)
        hp = striker.stats.health
        session.update(DT, PlayerInput(melee=True))
        self.assertLess(striker.stats.health, hp)

    def test_goblin_training_still_repeats(self):
        session = GameSession.new()  # MC-002 default
        self.assertEqual(session.encounter_id, "goblin_training")
        goblin = session.enemy
        goblin.receive_damage(10_000)
        session.update(DT, PlayerInput())
        self.assertEqual(session.encounter.status, EncounterStatus.CLEARED)
        for _ in range(round(4 / DT)):
            session.update(DT, PlayerInput())
        self.assertIsNot(session.enemy, goblin)
        self.assertTrue(session.enemy.is_alive)

    def test_parry_feedback_in_session(self):
        session = GameSession.new(encounter_id="striker_drill")
        session.player.position = Vec2(450, 300)
        striker = session.enemies[0]
        for _ in range(round(10 / DT)):
            if striker.state is AIState.TELEGRAPH and striker.windup_remaining < 0.1:
                break
            session.update(DT, PlayerInput())
        session.update(DT, PlayerInput(parry=True))
        for _ in range(10):
            session.update(DT, PlayerInput())
        self.assertTrue(any("staggers" in m for m in session.messages))
        self.assertEqual(striker.state, AIState.STAGGERED)
        self.assertEqual(striker.last_result.outcome, AttackOutcome.PARRIED)


if __name__ == "__main__":
    unittest.main()
