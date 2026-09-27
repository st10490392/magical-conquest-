"""Prototype loot tables per enemy archetype. PROTOTYPE / NON-FINAL."""

from __future__ import annotations

from typing import Dict

from game.items.catalog import ITEMS
from game.items.loot import LootEntry as E, LootTable, WeightedPick as W, validate_tables

LOOT_TABLES: Dict[str, LootTable] = {
    table.table_id: table
    for table in (
        LootTable("goblin", (E("bone_shard"), E("old_coin", 0.5, 1, 2))),
        LootTable("striker", (
            E("bone_shard", 1.0, 1, 2),
            E("minor_health_potion", 0.3),
            E("leather_gloves", 0.15),
        )),
        LootTable("archer", (
            E("tattered_cloth", 1.0, 1, 2),
            E("stamina_tonic", 0.35),
            E("old_coin", 0.25, 1, 3),
            E("traveler_boots", 0.1),
        )),
        LootTable(
            "brute",
            (E("iron_scrap", 1.0, 2, 3), E("minor_health_potion")),
            pool=(W("iron_helm", 2), W("leather_jerkin", 3), W("warding_hood", 1), W(None, 4)),
            pool_picks=1,
        ),
    )
}

validate_tables(LOOT_TABLES, lambda item_id: item_id in ITEMS)


def get_loot_table(table_id: str) -> LootTable:
    try:
        return LOOT_TABLES[table_id]
    except KeyError:
        raise ValueError(f"unknown loot table {table_id!r}") from None
