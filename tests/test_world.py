"""MC-006: zones, world graph, travel, placement, discovery and persistence."""

import json
import tempfile
import unittest
from pathlib import Path

from game.campaign import Campaign
from game.core.vector import Vec2
from game.events.events import LocationReached, ZoneEntered, ZoneLeft
from game.persistence.save_manager import LoadStatus, SaveManager
from game.quests.model import QuestStatus
from game.session import PlayerInput
from game.world.exploration import Exploration, Location
from game.world.zone_catalog import WORLD, npcs_in
from game.world.zones import (
    EncounterPlacement, PointOfInterest, Rect, RespawnRule, WorldGraph, ZoneDefinition, ZoneExit, ZoneKind,
)
from game.world_session import TravelStatus, WorldSession

DT = 1 / 60


def zone(zone_id, kind=ZoneKind.WILD, exits=(), encounters=(), spawns=(("default", Vec2(100, 100)),)):
    return ZoneDefinition(zone_id, zone_id.title(), kind, spawns, exits, encounters)


class ZoneDefinitionTests(unittest.TestCase):
    def test_catalog_world(self):
        self.assertEqual(set(WORLD.zones), {"proto_village", "proto_road", "proto_wilds"})
        self.assertEqual(WORLD.neighbours("proto_road"), ["proto_village", "proto_wilds"])
        self.assertTrue(WORLD.connected("proto_village", "proto_road"))
        self.assertFalse(WORLD.connected("proto_village", "proto_wilds"))
        self.assertTrue(WORLD.zone("proto_village").is_safe)
        self.assertFalse(WORLD.zone("proto_wilds").is_safe)
        with self.assertRaises(ValueError):
            WORLD.zone("atlantis")

    def test_validation(self):
        with self.assertRaises(ValueError):  # safe zones cannot host encounters
            zone("town", ZoneKind.SAFE, encounters=(EncounterPlacement("p", "striker_drill"),))
        with self.assertRaises(ValueError):  # needs a default spawn
            zone("x", spawns=(("north", Vec2(1, 1)),))
        with self.assertRaises(ValueError):  # spawn outside the zone
            zone("x", spawns=(("default", Vec2(-5, 1)),))
        with self.assertRaises(ValueError):  # exit to an unknown zone
            WorldGraph([zone("a", exits=(ZoneExit("e", Rect(0, 0, 10, 10), "b", "default"),))], "a")
        with self.assertRaises(ValueError):  # exit to an unknown spawn
            WorldGraph([zone("a", exits=(ZoneExit("e", Rect(0, 0, 10, 10), "b", "north"),)), zone("b")], "a")
        with self.assertRaises(ValueError):  # arrival spawn inside an exit would loop forever
            WorldGraph([zone("a", exits=(ZoneExit("e", Rect(90, 90, 20, 20), "a", "default"),))], "a")
        with self.assertRaises(ValueError):
            WorldGraph([zone("a")], "missing")

    def test_spawns_exits_and_placements(self):
        road = WORLD.zone("proto_road")
        self.assertEqual(road.spawn("from_village"), Vec2(80, 300))
        with self.assertRaises(KeyError):
            road.spawn("nowhere")
        self.assertEqual(road.exit_at(Vec2(5, 300)).target_zone, "proto_village")
        self.assertIsNone(road.exit_at(Vec2(400, 300)))
        self.assertEqual(WORLD.zone("proto_wilds").placement("den").respawn, RespawnRule.NEVER)

    def test_npc_placement(self):
        # MC-007 added the shopkeeper and blacksmith to the village.
        self.assertEqual([n.npc_id for n in npcs_in("proto_village")], ["proto_elder", "proto_merchant", "proto_smith"])
        self.assertEqual([n.npc_id for n in npcs_in("proto_road")], ["proto_scout"])
        self.assertEqual(npcs_in("proto_wilds"), [])


def walk(session, direction, until, seconds=10):
    for _ in range(round(seconds / DT)):
        session.update(DT, PlayerInput(move=direction))
        if until():
            return
    raise AssertionError("never arrived")


class TravelTests(unittest.TestCase):
    def test_starts_in_village_with_elder(self):
        session = WorldSession.new()
        self.assertEqual(session.zone.zone_id, "proto_village")
        self.assertEqual([n.npc_id for n in session.npcs], ["proto_elder", "proto_merchant", "proto_smith"])
        self.assertEqual(session.encounters, [])  # safe zone: no encounters

    def test_walking_into_exits_travels_and_publishes_events(self):
        session = WorldSession.new()
        seen = []
        for event_type in (ZoneEntered, ZoneLeft, LocationReached):
            session.bus.subscribe(event_type, seen.append)
        walk(session, Vec2(1, 0), lambda: session.zone.zone_id == "proto_road")
        self.assertEqual(session.player.position, WORLD.zone("proto_road").spawn("from_village"))
        self.assertIn(ZoneLeft("proto_village"), seen)
        self.assertIn(ZoneEntered("proto_road"), seen)
        self.assertIn(LocationReached("proto_road"), seen)
        self.assertEqual(len(session.encounters), 1)
        walk(session, Vec2(-1, 0), lambda: session.zone.zone_id == "proto_village")
        self.assertEqual(session.player.position, WORLD.zone("proto_village").spawn("from_road"))

    def test_travel_api_validation(self):
        session = WorldSession.new()
        self.assertEqual(session.travel("to_wilds"), TravelStatus.UNKNOWN_EXIT)  # not adjacent
        self.assertEqual(session.zone.zone_id, "proto_village")
        session.player.receive_damage(10_000)
        self.assertEqual(session.travel("to_road"), TravelStatus.DEAD)
        self.assertEqual(session.zone.zone_id, "proto_village")

    def test_encounters_reset_on_reentry(self):
        session = WorldSession.new()
        session.travel("to_road")
        ambush = session.encounters[0]
        ambush.enemies[0].receive_damage(20)
        session.travel("to_village")
        session.travel("to_road")
        fresh = session.encounters[0]
        self.assertIsNot(fresh, ambush)
        self.assertEqual(fresh.enemies[0].stats.health, fresh.enemies[0].stats.max_health)

    def test_never_respawn_encounter_stays_cleared(self):
        session = WorldSession.new()
        session.travel("to_road")
        session.travel("to_wilds")
        den = next(e for e in session.encounters if e.spec.encounter_id == "brute_den")
        den.start()
        den.enemies[0].receive_damage(100_000)
        session.update(DT, PlayerInput())
        self.assertIn("proto_wilds/den", session.campaign.exploration.cleared)
        session.travel("to_road")
        session.travel("to_wilds")
        self.assertEqual([e.spec.encounter_id for e in session.encounters], ["raider_camp"])

    def test_safe_zone_disables_attacks(self):
        session = WorldSession.new()
        stamina = session.player.stats.stamina
        session.update(DT, PlayerInput(melee=True, block=True))
        self.assertFalse(session.player.defense.blocking)
        self.assertEqual(session.player.stats.stamina, stamina)

    def test_world_time_continues_across_travel(self):
        session = WorldSession.new()
        session.world.day_length = 2.0
        walk(session, Vec2(1, 0), lambda: session.zone.zone_id == "proto_road")
        after_travel = session.world.time
        self.assertGreater(after_travel, 0)
        for _ in range(round(3 / DT)):
            session.update(DT, PlayerInput())
        self.assertAlmostEqual(session.world.time, after_travel + 3, places=5)
        self.assertGreaterEqual(session.world.day, 2)

    def test_respawn_after_death(self):
        session = WorldSession.new()
        session.travel("to_road")
        session.player.receive_damage(10_000)
        session.update(DT, PlayerInput())
        self.assertIsNotNone(session.last_player_death)
        self.assertTrue(session.respawn())
        self.assertEqual(session.zone.zone_id, "proto_village")
        self.assertEqual(session.player.stats.health, session.player.stats.max_health)
        self.assertIsNone(session.last_player_death)
        self.assertFalse(session.respawn())  # alive: nothing to do


class DiscoveryTests(unittest.TestCase):
    def test_discovery_event_xp_once(self):
        session = WorldSession.new()
        session.travel("to_road")
        milestone = WORLD.zone("proto_road").points_of_interest[0]
        seen = []
        session.bus.subscribe(LocationReached, seen.append)
        session.player.position = milestone.position
        session.update(DT, PlayerInput())
        self.assertIn("old_milestone", session.campaign.exploration.discovered)
        self.assertEqual(session.player.xp, milestone.discovery_xp)
        self.assertEqual(seen, [LocationReached("old_milestone")])
        for _ in range(5):
            session.update(DT, PlayerInput())
        session.travel("to_village")
        session.travel("to_road")
        session.player.position = milestone.position
        session.update(DT, PlayerInput())
        self.assertEqual(session.player.xp, milestone.discovery_xp)  # no second reward

    def test_reach_quest_objective_by_exploring(self):
        session = WorldSession.new()
        quests = session.campaign.quests
        session.travel("to_road")
        quests.accept("proto_watchtower")
        session.travel("to_wilds")
        tower = WORLD.zone("proto_wilds").points_of_interest[0]
        session.player.position = tower.position
        session.update(DT, PlayerInput())
        self.assertEqual(quests.status("proto_watchtower", session.player.inventory.count), QuestStatus.READY_TO_TURN_IN)


class WorldPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "save.json"
        self.manager = SaveManager(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_load_location_and_exploration(self):
        session = WorldSession.new()
        session.travel("to_road")
        session.player.position = Vec2(400, 540)
        session.update(DT, PlayerInput())  # discovers the milestone, records location
        self.manager.save(session.player, session.world, session.campaign)
        result = self.manager.load()
        self.assertEqual(result.status, LoadStatus.OK, result.error)
        restored = WorldSession(player=result.player, world=result.world, campaign=result.campaign)
        self.assertEqual(restored.zone.zone_id, "proto_road")
        self.assertEqual(restored.player.position, session.player.position)
        self.assertIn("old_milestone", restored.campaign.exploration.discovered)
        self.assertEqual(restored.world.time, session.world.time)

    def test_malformed_world_data(self):
        self.manager.save(WorldSession.new().player, WorldState_(), Campaign())
        base = json.loads(self.path.read_text())
        patches = [
            {"location": {"zone": "atlantis", "x": 1, "y": 1}},
            {"location": {"zone": "proto_road", "x": 9000, "y": 1}},
            {"location": {"zone": "proto_road", "x": "1", "y": 1}},
            {"location": {"zone": "proto_road"}},
            {"exploration": {"visited_zones": ["atlantis"], "discovered": [], "cleared": []}},
            {"exploration": {"visited_zones": [], "discovered": ["moon"], "cleared": []}},
            {"exploration": {"visited_zones": [], "discovered": [], "cleared": ["proto_road/ambush"]}},
            {"exploration": {"visited_zones": [], "discovered": []}},
            {"ledger": ["discovery:old_milestone"]},  # reward claimed but never discovered
        ]
        for patch in patches:
            with self.subTest(patch=patch):
                data = json.loads(json.dumps(base))
                data["campaign"].update(patch)
                self.path.write_text(json.dumps(data))
                self.assertEqual(self.manager.load().status, LoadStatus.MALFORMED)

    def test_v4_save_migrates_to_village_start(self):
        self.manager.save(WorldSession.new().player, WorldState_(), Campaign())
        data = json.loads(self.path.read_text())
        data["schema_version"] = 4
        del data["campaign"]["exploration"]
        del data["campaign"]["location"]
        self.path.write_text(json.dumps(data))
        result = self.manager.load()
        self.assertEqual(result.status, LoadStatus.OK, result.error)
        restored = WorldSession(player=result.player, world=result.world, campaign=result.campaign)
        self.assertEqual(restored.zone.zone_id, "proto_village")

    def test_location_and_exploration_round_trip_objects(self):
        location = Location("proto_wilds", Vec2(10, 20))
        self.assertEqual(Location.from_dict(location.to_dict(), WORLD), location)
        exploration = Exploration({"proto_road"}, {"watchtower"}, {"proto_wilds/den"})
        self.assertEqual(Exploration.from_dict(exploration.to_dict(), WORLD), exploration)


def WorldState_():
    from game.world.world_state import WorldState
    return WorldState()


class TravelSimulationTests(unittest.TestCase):
    def test_headless_journey_village_to_watchtower_and_back(self):
        session = WorldSession.new()
        session.player.stats.max_health = session.player.stats.health = 100_000  # a tourist, not a fight
        walk(session, Vec2(1, 0), lambda: session.zone.zone_id == "proto_road")
        walk(session, Vec2(1, 0), lambda: session.zone.zone_id == "proto_wilds", seconds=20)
        tower = WORLD.zone("proto_wilds").points_of_interest[0].position
        walk(session, tower - session.player.position,
             lambda: "watchtower" in session.campaign.exploration.discovered, seconds=20)
        walk(session, Vec2(-1, 0), lambda: session.zone.zone_id == "proto_road", seconds=20)
        walk(session, Vec2(-1, 0), lambda: session.zone.zone_id == "proto_village", seconds=20)
        self.assertEqual(session.campaign.exploration.visited_zones, {"proto_village", "proto_road", "proto_wilds"})
        self.assertGreater(session.world.time, 5)


if __name__ == "__main__":
    unittest.main()
