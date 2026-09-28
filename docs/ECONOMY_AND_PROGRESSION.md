# Economy and extended progression (MC-007)

All shop content, currency names and numbers are **PROTOTYPE / NON-FINAL**.
Nothing here depends on Pygame.

## Currency (`game/economy/wallet.py`)

- There is one prototype currency, "coins" (a non-canon name).
- `Wallet` holds a whole-number balance from 0 to 1,000,000,000.
- `earn` and `spend` accept positive integers only. They return
  `WalletResult` with one of these statuses: OK, INVALID_AMOUNT,
  INSUFFICIENT_FUNDS or OVER_LIMIT. A failed call leaves the balance
  unchanged, so it can never go negative or be spent twice.
- The wallet lives on the `Campaign` and is saved.

## Prices (`game/economy/pricing.py`)

```
buy  = max(1, ceil(base_value x rarity multiplier x markup))
sell = floor(base_value x rarity multiplier x buyback)     (0 = will not buy)
```

`PricePolicy` requires `buyback <= markup`, so buying and reselling can never
make money. Rarity changes **price only**; an item's usefulness comes from
its own stats.

## Merchants (`game/economy/merchant.py`, `catalog.py`)

- `MerchantDefinition` holds the stock (limited or unlimited entries), a
  `PricePolicy`, the item categories the merchant buys (never quest items),
  and its `services`.
- `MerchantState` is the remaining limited stock, which is saved. There is no
  restocking yet.
- **Buying** checks everything before touching anything: quantity, that the
  player is alive, that the item is sold here, stock, funds, unique
  ownership and inventory space. Only then does it charge coins, add the item
  and reduce the stock, in that order. If adding the item somehow failed, the
  coins would be refunded.
- **Selling** only works from the inventory (equipped gear has to be
  unequipped first). It checks ownership, that the item is sellable, that the
  merchant buys that category, that the price is above 0, and that the wallet
  has room, before removing the item and paying.
- Every transaction returns a `TransactionResult` with an explicit status. A
  randomized 300-trade test checks that coins and items stay consistent.

There are two prototype merchants in the Prototype Village:

- **General Store** (the Shopkeeper): potions and tonics with unlimited stock,
  plus a little leather gear. It buys everything except quest items.
- **Blacksmith** (the Smith): weapons and armor, at a 1.2 markup and 0.5
  buyback. It only buys weapons, armor and materials, and it offers the
  **Inspect** service.

## Blacksmith foundation (`game/economy/blacksmith.py`)

The canon expects players to visit crafters for better gear. For now the
blacksmith **sells** gear (SHOP) and **inspects** your equipped gear
(INSPECT), with a stats readout and what it's worth to them.
**Upgrading, repair, crafting and weapon grades are not designed yet, so they
are not implemented.** `ServiceType` and `blacksmith.py` are the extension
point for them. In dialogue, the smith answers "not yet" when you ask about
improving your weapon.

## Progression hooks (`game/progression/rewards.py`)

XP and levels are unchanged from MC-001 (a formula curve plus per-level
growth); nothing was rebalanced. Rewards come from:

| Source | How it's granted | Once-only key |
|---|---|---|
| Enemy defeat | XP + coins + loot roll, in `PlaySession._on_enemy_defeated` | `Encounter.take_defeated()` reports each death exactly once |
| Quest | `turn_in()`: XP + coins + items | `quest:<id>` |
| Exploration | a point of interest's `discovery_xp` | `discovery:<poi>` |
| Encounter clear | `EncounterSpec.clear_reward`, for NEVER-respawn placements | `encounter:<zone>/<placement>` |

`PlaySession.grant(source, ident, reward)` is the single hook for once-only
rewards. It goes through `RewardLedger` and is all-or-nothing: if the reward
items don't fit, nothing is granted. Loading a save cross-checks the ledger:
a claimed discovery must be discovered, and a claimed encounter must be
cleared.

## Save schema v6

The save adds `campaign.wallet` (an integer) and `campaign.merchants`
(`{merchant_id: {item_id: remaining}}`). Loading rejects a negative, fractional
or oversized balance, unknown merchants, and stock values outside 0 to the
starting stock. Version-5 saves migrate with an empty wallet and untouched
merchants.

## Demo loop

1. Accept a quest from the elder.
2. Fight in the Road or the Wilds and earn XP, coins and loot.
3. Return to the village and turn the quest in (XP, coins and items).
4. Talk to the Shopkeeper or the Blacksmith (G, then "Let's trade").
5. In the shop, Left/Right switches Buy/Sell/Inspect, Up/Down selects, Enter
   buys or sells one, and Esc leaves.
6. Equip what you bought from the inventory (I).
