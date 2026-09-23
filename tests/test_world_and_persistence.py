import json
import tempfile
import unittest
from pathlib import Path

from game.core.vector import Vec2
from game.entities.player import Player
from game.persistence.save_manager import SAVE_SCHEMA_VERSION, LoadStatus, SaveManager
from game.session import GameSession, PlayerInput
from game.world.world_state import WorldState


class WorldStateTests(unittest.TestCase):
    def test_time_and_day(self):
        world = WorldState(day_length=100)
        self.assertEqual(world.day, 1)
        world.tick(250)
        self.assertEqual(world.day, 3)
        self.assertAlmostEqual(world.time_of_day, 0.5)

    def test_events_expire(self):
        world = WorldState()
        world.start_event("raid-1", "dragon_attack", duration=30)
        world.start_event("fair", "market", duration=None)
        self.assertEqual(len(world.active_events), 2)
        expired = world.tick(31)
        self.assertEqual([e.event_id for e in expired], ["raid-1"])
        self.assertEqual([e.event_id for e in world.active_events], ["fair"])

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            WorldState().tick(-1)
        with self.assertRaises(ValueError):
            WorldState(day_length=0)
        world = WorldState()
        world.start_event("x", "k")
        with self.assertRaises(ValueError):
            world.start_event("x", "k")


class SaveManagerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "nested" / "save.json"
        self.manager = SaveManager(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip(self):
        player = Player("Aria", level=3, xp=42, position=Vec2(12.5, 7))
        player.stats.take_damage(20)
        player.stats.consume_mana(5)
        world = WorldState(time=1234.5)
        world.start_event("raid", "dragon_attack", "Red dragon sighted", duration=60, data={"region": "north"})

        self.manager.save(player, world)
        result = self.manager.load()

        self.assertEqual(result.status, LoadStatus.OK)
        loaded = result.player
        self.assertEqual(loaded.entity_id, player.entity_id)
        self.assertEqual((loaded.name, loaded.level, loaded.xp), ("Aria", 3, 42))
        self.assertEqual(loaded.stats, player.stats)
        self.assertEqual(loaded.position, player.position)
        self.assertEqual(result.world.time, 1234.5)
        self.assertEqual(result.world.day, world.day)
        self.assertEqual([e.to_dict() for e in result.world.active_events], [e.to_dict() for e in world.active_events])

        raw = json.loads(self.path.read_text())
        self.assertEqual(raw["schema_version"], SAVE_SCHEMA_VERSION)

    def test_missing_file(self):
        result = self.manager.load()
        self.assertEqual(result.status, LoadStatus.MISSING)
        self.assertIsNone(result.player)

    def test_invalid_json(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        self.assertEqual(self.manager.load().status, LoadStatus.MALFORMED)

    def test_malformed_structure(self):
        self.path.parent.mkdir(parents=True)
        cases = [
            [],
            {"schema_version": SAVE_SCHEMA_VERSION},
            {"schema_version": SAVE_SCHEMA_VERSION, "player": {"name": "x"}, "world": {"time": 0}},
            {
                "schema_version": SAVE_SCHEMA_VERSION,
                "player": {"id": "a", "name": "x", "level": 0, "xp": 0, "stats": {}},
                "world": {"time": 0},
            },
            {
                "schema_version": SAVE_SCHEMA_VERSION,
                "player": {"id": "a", "name": "x", "level": 1, "xp": 0, "stats": {"health": -4}},
                "world": {"time": 0},
            },
        ]
        for case in cases:
            with self.subTest(case=case):
                self.path.write_text(json.dumps(case))
                result = self.manager.load()
                self.assertEqual(result.status, LoadStatus.MALFORMED)
                self.assertIsNotNone(result.error)

    def test_unsupported_version(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"schema_version": 999, "player": {}, "world": {}}))
        self.assertEqual(self.manager.load().status, LoadStatus.UNSUPPORTED_VERSION)


class SessionTests(unittest.TestCase):
    """Drives the full demo loop headlessly - no Pygame involved."""

    def test_player_can_kill_enemy_and_gain_xp(self):
        session = GameSession.new()
        for _ in range(60 * 30):
            session.update(1 / 60, PlayerInput(move=Vec2(1, 0), melee=True))
            if session.kills:
                break
        self.assertEqual(session.kills, 1)
        self.assertGreater(session.player.xp + session.player.level, 1)

    def test_idle_player_eventually_dies(self):
        session = GameSession.new()
        for _ in range(60 * 120):
            session.update(1 / 60, PlayerInput())
            if not session.player.is_alive:
                break
        self.assertFalse(session.player.is_alive)
        self.assertIsNotNone(session.player.death)
        self.assertGreater(session.world.time, 0)


if __name__ == "__main__":
    unittest.main()
