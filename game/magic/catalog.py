"""Small prototype spell set, one per attribute, across several ranks.

Names and numbers are PROTOTYPE CONTENT - NON-FINAL, not game canon.
There is deliberately no S-rank spell here; tests build their own.
"""

from __future__ import annotations

from typing import Dict

from game.magic.attributes import MagicAttribute as M
from game.magic.ranks import SpellRank as R
from game.magic.spells import Spell

_PROTOTYPE_SPELLS = (
    Spell("fire_bolt", "Fire Bolt", R.E, M.FIRE, base_power=10, magic_scaling=1.2, mana_cost=12, cooldown=0.9, reach=260),
    Spell("water_shot", "Water Shot", R.E, M.WATER, base_power=9, magic_scaling=1.1, mana_cost=10, cooldown=0.8, reach=240),
    Spell("air_burst", "Air Burst", R.E, M.AIR, base_power=7, magic_scaling=1.0, mana_cost=8, cooldown=0.6, reach=150),
    Spell("ice_shard", "Ice Shard", R.D, M.ICE, base_power=14, magic_scaling=1.3, mana_cost=15, cooldown=1.0, reach=260),
    Spell("wind_cutter", "Wind Cutter", R.D, M.WIND, base_power=13, magic_scaling=1.3, mana_cost=14, cooldown=0.9, reach=280),
    Spell("stone_strike", "Stone Strike", R.D, M.EARTH, base_power=18, magic_scaling=1.2, mana_cost=18, cooldown=1.4, reach=180),
    Spell("lightning_bolt", "Lightning Bolt", R.C, M.LIGHTNING, base_power=22, magic_scaling=1.5, mana_cost=22, cooldown=1.2, reach=320),
    Spell("thunder_strike", "Thunder Strike", R.B, M.THUNDER, base_power=32, magic_scaling=1.7, mana_cost=30, cooldown=2.0, reach=220),
    Spell("light_bolt", "Light Bolt", R.A, M.LIGHT, base_power=40, magic_scaling=2.0, mana_cost=35, cooldown=2.0, reach=300),
)

SPELLS: Dict[str, Spell] = {spell.spell_id: spell for spell in _PROTOTYPE_SPELLS}


def get_spell(spell_id: str) -> Spell:
    try:
        return SPELLS[spell_id]
    except KeyError:
        raise ValueError(f"unknown spell {spell_id!r}") from None
