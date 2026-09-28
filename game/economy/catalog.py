"""Prototype merchants. PROTOTYPE / NON-CANON; prices are NON-FINAL."""

from __future__ import annotations

from typing import Dict

from game.economy.merchant import MerchantDefinition, ServiceType, StockEntry as S
from game.economy.pricing import PricePolicy
from game.items.catalog import ITEMS
from game.items.definitions import ItemCategory as C

MERCHANTS: Dict[str, MerchantDefinition] = {
    m.merchant_id: m
    for m in (
        MerchantDefinition(
            "proto_general_store", "General Store", "proto_merchant",
            stock=(
                S("minor_health_potion"), S("minor_mana_potion"), S("stamina_tonic"),
                S("leather_cap", 2), S("leather_gloves", 2), S("traveler_boots", 1),
            ),
            pricing=PricePolicy(markup=1.0, buyback=0.4),
        ),
        MerchantDefinition(
            "proto_smithy", "Blacksmith", "proto_smith",
            stock=(
                S("steel_dagger", 2), S("ash_spear", 1), S("iron_greatsword", 1),
                S("iron_helm", 1), S("leather_jerkin", 2), S("leather_greaves", 2),
            ),
            pricing=PricePolicy(markup=1.2, buyback=0.5),
            buys=(C.WEAPON, C.ARMOR, C.MATERIAL),
            services=(ServiceType.SHOP, ServiceType.INSPECT),
        ),
    )
}

for _merchant in MERCHANTS.values():
    for _entry in _merchant.stock:
        if _entry.item_id not in ITEMS:
            raise ValueError(f"{_merchant.merchant_id} stocks unknown item {_entry.item_id}")


def get_merchant(merchant_id: str) -> MerchantDefinition:
    try:
        return MERCHANTS[merchant_id]
    except KeyError:
        raise ValueError(f"unknown merchant {merchant_id!r}") from None
