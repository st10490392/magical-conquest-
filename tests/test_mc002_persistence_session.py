import json
import tempfile
import unittest
from pathlib import Path

from game.core.vector import Vec2
from game.entities.enemy import EnemyState
from game.entities.player import Player
from game.equipment.catalog import WEAPONS
from game.magic.attributes import MagicAttribute
from game.magic.catalog import SPELLS
from game.persistence.save_manager import SAVE_SCHEMA_VERSION, LoadStatus, SaveManager
from game.session import GameSession, PlayerInput
from game.world.world_state import WorldState

V1_SAVE = {
    "schema_version": 1,
    "player": {
        "id": "abc123",
        "name": "Veteran of MC-001",
        "level": 3,
        "xp": 25,
        "position": {"x": 10, "y": 20},
        "stats": {"max_health": 150, "health": 90, "magic_power": 14},
    },
    "world": {"time": 700.0, "day_length": 600.0, "events": []},
}


class SaveV2Tests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "save.json"
        self.manager = SaveManager(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, data):
        self.path.write_text(json.dumps(data))

    def test_round_trip_mc002_state(self):
        player = Player("Aria", magic_attributes=[MagicAttribute.WIND, MagicAttribute.THUNDER])
        player.equip(WEAPONS["ash_spear"])
        player.learn_spell(SPELLS["wind_cutter"])
        player.learn_spell(SPELLS["thunder_strike"])
        player.spellbook.select("thunder_strike")
        self.manager.save(player, WorldState())

        self.assertEqual(json.loads(self.path.read_text())["schema_version"], SAVE_SCHEMA_VERSION)
        loaded = self.manager.load().player
        self.assertEqual(loaded.magic_attributes, {MagicAttribute.WIND, MagicAttribute.THUNDER})
        self.assertIs(loaded.weapon, WEAPONS["ash_spear"])
        self.assertEqual([s.spell_id for s in loaded.spellbook.spells], ["wind_cutter", "thunder_strike"])
        self.assertEqual(loaded.spellbook.selected_id, "thunder_strike")

    def test_round_trip_unarmed_without_spells(self):
        self.manager.save(Player("Plain"), WorldState())
        loaded = self.manager.load().player
        self.assertIsNone(loaded.weapon)
        self.assertEqual(loaded.spellbook.spells, [])
        self.assertIsNone(loaded.spellbook.selected)
        self.assertEqual(loaded.magic_attributes, set())

    def test_migrates_mc001_v1_save(self):
        self.write(V1_SAVE)
        result = self.manager.load()
        self.assertEqual(result.status, LoadStatus.OK, result.error)
        player = result.player
        self.assertEqual((player.entity_id, player.name, player.level, player.xp), ("abc123", "Veteran of MC-001", 3, 25))
        self.assertEqual(player.stats.health, 90)
        self.assertEqual(player.position, Vec2(10, 20))
        self.assertEqual(result.world.day, 2)
        # MC-001 characters could cast Fire Bolt and fought unarmed.
        self.assertEqual(player.magic_attributes, {MagicAttribute.FIRE})
        self.assertEqual(player.spellbook.selected_id, "fire_bolt")
        self.assertIsNone(player.weapon)

    def test_malformed_mc002_fields(self):
        base = {
            "schema_version": 2,
            "player": {
                "id": "x", "name": "x", "level": 1, "xp": 0, "stats": {},
                "magic_attributes": [], "equipped_weapon": None,
                "known_spells": [], "selected_spell": None,
            },
            "world": {"time": 0},
        }
        bad_fields = [
            {"magic_attributes": ["plasma"]},
            {"magic_attributes": "fire"},
            {"equipped_weapon": "dragon_slayer"},
            {"known_spells": ["ice_age"]},
            {"known_spells": "fire_bolt"},
            {"selected_spell": "fire_bolt"},  # not known
        ]
        for patch in bad_fields:
            with self.subTest(patch=patch):
                data = json.loads(json.dumps(base))
                data["player"].update(patch)
                self.write(data)
                self.assertEqual(self.manager.load().status, LoadStatus.MALFORMED)
        missing = json.loads(json.dumps(base))
        del missing["player"]["known_spells"]
        self.write(missing)
        self.assertEqual(self.manager.load().status, LoadStatus.MALFORMED)

    def test_malformed_v1_save(self):
        self.write({"schema_version": 1, "player": "nope", "world": {}})
        self.assertEqual(self.manager.load().status, LoadStatus.MALFORMED)

    def test_future_or_weird_versions(self):
        for version in (3, 0, "2", True, None, [1]):
            with self.subTest(version=version):
                self.write({"schema_version": version, "player": {}, "world": {}})
                self.assertEqual(self.manager.load().status, LoadStatus.UNSUPPORTED_VERSION)


class SessionMC002Tests(unittest.TestCase):
    """The demo loop with the new mechanics, driven headlessly."""

    def approach(self, session):
        for _ in range(600):
            if session.enemy.state is EnemyState.WINDUP:
                return
            session.update(1 / 60, PlayerInput(move=Vec2(1, 0)))
        self.fail("enemy never started an attack")

    def test_new_session_loadout(self):
        session = GameSession.new()
        player = session.player
        self.assertIs(player.weapon, WEAPONS["iron_sword"])
        self.assertEqual(len(player.spellbook.spells), len(SPELLS))
        self.assertNotIn(MagicAttribute.WATER, player.magic_attributes)

    def test_parry_timed_to_the_strike(self):
        session = GameSession.new()
        self.approach(session)
        while session.enemy.windup_remaining > 0.1:
            session.update(1 / 60, PlayerInput())
        hp = session.player.stats.health
        session.update(1 / 60, PlayerInput(parry=True))
        for _ in range(15):
            session.update(1 / 60, PlayerInput())
        self.assertIn("Parried!", session.messages)
        self.assertEqual(session.player.stats.health, hp)

    def test_parry_too_early_fails(self):
        session = GameSession.new()
        self.approach(session)
        hp = session.player.stats.health
        session.update(1 / 60, PlayerInput(parry=True))  # windup is longer than the window
        for _ in range(30):
            session.update(1 / 60, PlayerInput())
        self.assertNotIn("Parried!", session.messages)
        self.assertLess(session.player.stats.health, hp)

    def test_dodge_during_windup(self):
        session = GameSession.new()
        self.approach(session)
        # Wait until the claw is about to land, then dodge.
        while session.enemy.windup_remaining > 0.1:
            session.update(1 / 60, PlayerInput())
        session.update(1 / 60, PlayerInput(dodge=True))
        for _ in range(10):
            session.update(1 / 60, PlayerInput())
        self.assertIn("Dodged!", session.messages)

    def test_block_while_held(self):
        session = GameSession.new()
        self.approach(session)
        for _ in range(40):
            session.update(1 / 60, PlayerInput(block=True))
        self.assertTrue(any(m.startswith("Blocked") for m in session.messages))
        self.assertLess(session.player.stats.stamina, session.player.stats.max_stamina)
        session.update(1 / 60, PlayerInput())
        self.assertFalse(session.player.defense.blocking)

    def test_spell_selection_and_requirement_feedback(self):
        session = GameSession.new()
        session.update(1 / 60, PlayerInput(select_spell=1))  # Water Shot: missing attribute
        self.assertIn("missing attribute", session.messages[-1])
        session.update(1 / 60, PlayerInput(select_spell=0))
        self.assertEqual(session.player.spellbook.selected_id, "fire_bolt")

    def test_weapon_cycle_reaches_unarmed(self):
        session = GameSession.new()
        seen = set()
        for _ in range(len(WEAPONS) + 1):
            session.update(1 / 60, PlayerInput(cycle_weapon=True))
            seen.add(session.player.weapon.weapon_id if session.player.weapon else None)
        self.assertEqual(seen, set(WEAPONS) | {None})

    def test_casting_kills_enemy(self):
        session = GameSession.new()
        for _ in range(60 * 60):
            session.update(1 / 60, PlayerInput(move=Vec2(1, 0), magic=True))
            if session.kills:
                break
        self.assertEqual(session.kills, 1)

    def test_player_death_records_context(self):
        session = GameSession.new()
        for _ in range(60 * 180):
            session.update(1 / 60, PlayerInput())
            if not session.player.is_alive:
                break
        self.assertIsNotNone(session.last_player_death)
        self.assertEqual(session.last_player_death.context.value, "open_world")

    def test_no_attacks_while_blocking(self):
        session = GameSession.new()
        self.approach(session)
        hp = session.enemy.stats.health
        for _ in range(20):
            session.update(1 / 60, PlayerInput(block=True, melee=True))
        self.assertEqual(session.enemy.stats.health, hp)


if __name__ == "__main__":
    unittest.main()
