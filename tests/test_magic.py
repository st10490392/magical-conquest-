import unittest

from game.core.combat import AttackOutcome, Cooldown
from game.core.entity import Entity
from game.core.stats import Stats
from game.core.vector import Vec2
from game.entities.player import Player
from game.magic.attributes import MagicAttribute, parse_attributes
from game.magic.casting import cast_spell, check_spell_requirements
from game.magic.catalog import SPELLS, get_spell
from game.magic.ranks import RANK_MIN_MAGIC_POWER, SpellRank
from game.magic.spellbook import SpellBook
from game.magic.spells import Spell

# Test-only S-rank spell (the prototype catalog deliberately has none).
TEST_S_SPELL = Spell("test_inferno", "Test Inferno", SpellRank.S, MagicAttribute.FIRE,
                     base_power=100, magic_scaling=3.0, mana_cost=50, cooldown=5.0)


def caster(magic_power=10.0, level=1, attributes=(MagicAttribute.FIRE,), mana=200.0):
    player = Player("Mage", Stats(max_health=100, max_mana=mana, magic_power=magic_power),
                    level=level, magic_attributes=attributes)
    for spell in SPELLS.values():
        player.learn_spell(spell)
    return player


def dummy(distance=100.0, **stats):
    return Entity("Dummy", Stats(max_health=stats.pop("max_health", 10_000), **stats), position=Vec2(distance, 0))


class AttributeTests(unittest.TestCase):
    def test_all_attributes_distinct(self):
        values = {a.value for a in MagicAttribute}
        self.assertEqual(len(values), 9)
        self.assertNotEqual(MagicAttribute.WIND, MagicAttribute.AIR)
        self.assertNotEqual(MagicAttribute.LIGHTNING, MagicAttribute.THUNDER)
        self.assertIn(MagicAttribute.LIGHT, MagicAttribute)

    def test_entity_attribute_ownership(self):
        entity = Entity("E", magic_attributes=[MagicAttribute.WIND, MagicAttribute.THUNDER])
        self.assertTrue(entity.has_attribute(MagicAttribute.WIND))
        self.assertFalse(entity.has_attribute(MagicAttribute.AIR))
        self.assertFalse(entity.has_attribute(MagicAttribute.LIGHTNING))
        entity.grant_attribute(MagicAttribute.AIR)
        entity.revoke_attribute(MagicAttribute.WIND)
        self.assertEqual(entity.magic_attributes, {MagicAttribute.AIR, MagicAttribute.THUNDER})

    def test_parse_attributes(self):
        self.assertEqual(parse_attributes(["ice", "earth"]), {MagicAttribute.ICE, MagicAttribute.EARTH})
        with self.assertRaises(ValueError):
            parse_attributes(["plasma"])
        with self.assertRaises(TypeError):
            parse_attributes("fire")


class RankTests(unittest.TestCase):
    def test_rank_order(self):
        order = [SpellRank.E, SpellRank.D, SpellRank.C, SpellRank.B, SpellRank.A, SpellRank.S]
        self.assertEqual(sorted(reversed(order)), order)
        self.assertGreater(SpellRank.S, SpellRank.A)
        self.assertEqual(SpellRank("S").tier, 5)
        with self.assertRaises(ValueError):
            SpellRank("Z")

    def test_rank_floor_raises_requirement(self):
        # A spell cannot declare a requirement below its rank's floor.
        self.assertEqual(TEST_S_SPELL.required_magic_power, RANK_MIN_MAGIC_POWER[SpellRank.S])
        generous = Spell("x", "X", SpellRank.E, MagicAttribute.FIRE, base_power=1, min_magic_power=40)
        self.assertEqual(generous.required_magic_power, 40)

    def test_catalog_has_multiple_ranks_and_every_attribute(self):
        self.assertGreaterEqual(len({s.rank for s in SPELLS.values()}), 4)
        self.assertEqual({s.element for s in SPELLS.values()}, set(MagicAttribute))
        with self.assertRaises(ValueError):
            get_spell("ice_age")


class RequirementTests(unittest.TestCase):
    def test_new_player_cannot_cast_s_rank(self):
        mage = caster(magic_power=10)
        mage.learn_spell(TEST_S_SPELL)
        target = dummy()
        result = mage.cast(target, TEST_S_SPELL)
        self.assertEqual(result.outcome, AttackOutcome.INSUFFICIENT_MAGIC_POWER)
        self.assertEqual(target.stats.health, target.stats.max_health)
        self.assertEqual(mage.stats.mana, mage.stats.max_mana)  # nothing spent

    def test_qualified_caster_can_cast_s_rank(self):
        mage = caster(magic_power=RANK_MIN_MAGIC_POWER[SpellRank.S])
        mage.learn_spell(TEST_S_SPELL)
        self.assertTrue(mage.cast(dummy(), TEST_S_SPELL).landed)

    def test_missing_attribute(self):
        mage = caster(attributes=(MagicAttribute.FIRE,))
        self.assertEqual(mage.cast(dummy(), SPELLS["water_shot"]).outcome, AttackOutcome.MISSING_ATTRIBUTE)

    def test_min_level(self):
        spell = Spell("lvl", "Level Locked", SpellRank.E, MagicAttribute.FIRE, base_power=5, min_level=10)
        self.assertEqual(check_spell_requirements(caster(level=9), spell), AttackOutcome.INSUFFICIENT_LEVEL)
        self.assertIsNone(check_spell_requirements(caster(level=10), spell))

    def test_unknown_or_unselected_spell(self):
        player = Player("Novice", magic_attributes=[MagicAttribute.FIRE])
        self.assertEqual(player.cast(dummy()).outcome, AttackOutcome.NO_SPELL_SELECTED)
        self.assertEqual(player.cast(dummy(), SPELLS["fire_bolt"]).outcome, AttackOutcome.SPELL_NOT_KNOWN)

    def test_insufficient_mana(self):
        mage = caster(mana=5)
        result = mage.cast(dummy(), SPELLS["fire_bolt"])
        self.assertEqual(result.outcome, AttackOutcome.NOT_ENOUGH_MANA)
        self.assertEqual(mage.stats.mana, 5)

    def test_out_of_range(self):
        mage = caster()
        self.assertEqual(mage.cast(dummy(distance=5000), SPELLS["fire_bolt"]).outcome, AttackOutcome.OUT_OF_RANGE)


class CastingTests(unittest.TestCase):
    def test_spell_cooldown_is_per_spell(self):
        mage = caster(attributes=(MagicAttribute.FIRE, MagicAttribute.ICE), magic_power=20)
        target = dummy()
        fire, ice = SPELLS["fire_bolt"], SPELLS["ice_shard"]
        self.assertTrue(mage.cast(target, fire).landed)
        self.assertEqual(mage.cast(target, fire).outcome, AttackOutcome.ON_COOLDOWN)
        self.assertTrue(mage.cast(target, ice).landed)  # different spell, own cooldown
        mage.update(fire.cooldown)
        self.assertTrue(mage.cast(target, fire).landed)

    def test_elemental_spell_damage(self):
        mage = caster(magic_power=20, attributes=tuple(MagicAttribute))
        spell = SPELLS["wind_cutter"]
        target = dummy(magic_resistance=0, durability=1000)
        result = mage.cast(target, spell)
        self.assertEqual(result.element, MagicAttribute.WIND)
        self.assertAlmostEqual(result.damage, spell.base_power + 20 * spell.magic_scaling)
        self.assertEqual(mage.stats.mana, mage.stats.max_mana - spell.mana_cost)

    def test_magic_resistance_applies_to_spells(self):
        mage = caster(magic_power=10)
        weak = mage.cast(dummy(magic_resistance=100), SPELLS["fire_bolt"])
        self.assertAlmostEqual(weak.damage, (10 + 10 * 1.2) / 2)

    def test_cast_spell_function_directly(self):
        mage = caster()
        cooldown = Cooldown()
        result = cast_spell(mage, dummy(), SPELLS["fire_bolt"], cooldown)
        self.assertTrue(result.landed)
        self.assertFalse(cooldown.ready)

    def test_spellbook_selection(self):
        book = SpellBook()
        self.assertIsNone(book.selected)
        book.learn(SPELLS["fire_bolt"])
        book.learn(SPELLS["ice_shard"])
        self.assertEqual(book.selected.spell_id, "fire_bolt")
        self.assertTrue(book.select_index(1))
        self.assertEqual(book.selected.spell_id, "ice_shard")
        self.assertFalse(book.select_index(7))
        self.assertFalse(book.select("light_bolt"))


if __name__ == "__main__":
    unittest.main()
