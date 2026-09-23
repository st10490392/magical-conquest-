"""Headless PvP: two Player objects fighting through the normal combat rules."""

import unittest

from game.core.combat import AttackOutcome
from game.core.entity import DeathContext
from game.core.stats import Stats
from game.core.vector import Vec2
from game.entities.enemy import create_goblin
from game.entities.player import Player
from game.equipment.catalog import WEAPONS
from game.magic.attributes import MagicAttribute
from game.magic.catalog import SPELLS


def duelist(name, level=1, position=Vec2(), weapon="iron_sword", **stats):
    player = Player(name, Stats(**stats) if stats else None, level=level, position=position,
                    magic_attributes=[MagicAttribute.FIRE])
    if weapon:
        player.equip(WEAPONS[weapon])
    player.learn_spell(SPELLS["fire_bolt"])
    return player


def refresh(*players):
    """Skip cooldowns and top up stamina/mana between swings."""
    for player in players:
        player.update(10.0)
        player.stats.restore_stamina(1000)
        player.stats.restore_mana(1000)


class PvPTests(unittest.TestCase):
    def test_player_damages_player(self):
        a = duelist("A")
        b = duelist("B", position=Vec2(50, 0))
        hp = b.stats.health
        result = a.weapon_attack(b)
        self.assertTrue(result.landed)
        self.assertLess(b.stats.health, hp)
        refresh(a, b)
        self.assertTrue(b.weapon_attack(a).landed)
        refresh(a, b)
        self.assertTrue(a.cast(b).landed)

    def test_pvp_defenses_work(self):
        a = duelist("A")
        b = duelist("B", position=Vec2(50, 0))
        b.parry()
        self.assertEqual(a.weapon_attack(b).outcome, AttackOutcome.PARRIED)

    def test_player_death_in_pvp(self):
        a = duelist("A", max_health=100, physical_strength=40)
        b = duelist("B", position=Vec2(50, 0), max_health=60, durability=0)
        while b.is_alive:
            refresh(a)
            a.weapon_attack(b)
        self.assertEqual(b.death.context, DeathContext.PVP)
        self.assertEqual(b.death.killer_id, a.entity_id)
        refresh(a)
        self.assertEqual(a.weapon_attack(b).outcome, AttackOutcome.TARGET_DEAD)
        self.assertEqual(b.weapon_attack(a).outcome, AttackOutcome.ATTACKER_DEAD)

    def test_pve_death_is_open_world(self):
        player = duelist("A", max_health=20, durability=0)
        goblin = create_goblin(position=Vec2(30, 0))
        while player.is_alive:
            goblin.update(5.0, player)
        self.assertEqual(player.death.context, DeathContext.OPEN_WORLD)

    def test_explicit_context_overrides_inference(self):
        a = duelist("A", physical_strength=500)
        b = duelist("B", position=Vec2(50, 0), max_health=10)
        a.weapon_attack(b, context=DeathContext.DUNGEON)
        self.assertEqual(b.death.context, DeathContext.DUNGEON)

    def test_low_level_player_kills_much_stronger_player(self):
        novice = duelist("Novice", level=1, weapon="steel_dagger", physical_strength=3)
        veteran = duelist(
            "Veteran", level=900, position=Vec2(40, 0), weapon="iron_greatsword",
            max_health=50_000, durability=8_000, magic_resistance=8_000,
        )
        hits = 0
        while veteran.is_alive and hits < 200_000:
            refresh(novice)
            result = novice.weapon_attack(veteran)
            self.assertGreater(result.damage, 0)
            hits += 1
        self.assertFalse(veteran.is_alive)
        self.assertEqual(veteran.death.context, DeathContext.PVP)
        self.assertEqual(veteran.death.killer_id, novice.entity_id)

    def test_block_cannot_make_a_player_immortal(self):
        novice = duelist("Novice", physical_strength=3)
        veteran = duelist("Veteran", level=500, position=Vec2(50, 0), max_health=2_000,
                          max_stamina=100_000, durability=1_000)
        veteran.start_block()
        while veteran.is_alive:
            refresh(novice)
            result = novice.weapon_attack(veteran)
            self.assertEqual(result.outcome, AttackOutcome.BLOCKED)
            self.assertGreater(result.damage, 0)
        self.assertFalse(veteran.is_alive)


if __name__ == "__main__":
    unittest.main()
