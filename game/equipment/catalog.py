"""A few prototype weapons, one per type.

PROTOTYPE CONTENT - NON-FINAL BALANCE. Legendary weapons are out of scope.
"""

from __future__ import annotations

from typing import Dict

from game.equipment.weapons import Weapon, WeaponType as T

_PROTOTYPE_WEAPONS = (
    Weapon("iron_sword", "Iron Sword", T.SWORD, base_power=12, strength_scaling=1.0,
           reach=75, stamina_cost=8, cooldown=0.45, block_capability=0.6, can_parry=True),
    Weapon("iron_greatsword", "Iron Greatsword", T.GREATSWORD, base_power=22, strength_scaling=1.4,
           reach=95, stamina_cost=18, cooldown=1.0, block_capability=0.75, can_parry=False),
    Weapon("steel_dagger", "Steel Dagger", T.DAGGER, base_power=7, strength_scaling=0.8,
           reach=55, stamina_cost=5, cooldown=0.25, block_capability=0.0, can_parry=True),
    Weapon("ash_spear", "Ash Spear", T.SPEAR, base_power=14, strength_scaling=1.1,
           reach=120, stamina_cost=10, cooldown=0.6, block_capability=0.4, can_parry=False),
    Weapon("oak_staff", "Oak Staff", T.STAFF, base_power=6, strength_scaling=0.5,
           reach=85, stamina_cost=6, cooldown=0.5, block_capability=0.4, can_parry=False),
)

WEAPONS: Dict[str, Weapon] = {weapon.weapon_id: weapon for weapon in _PROTOTYPE_WEAPONS}


def get_weapon(weapon_id: str) -> Weapon:
    try:
        return WEAPONS[weapon_id]
    except KeyError:
        raise ValueError(f"unknown weapon {weapon_id!r}") from None
