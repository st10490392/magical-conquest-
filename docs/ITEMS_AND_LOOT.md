# Items, loot, inventory and equipment (MC-004)

All item content is **PROTOTYPE / NON-CANON**, and every number here is
**NON-FINAL**. There are no legendary or canonical items. Everything in this
document works without Pygame.

## Item definitions (`game/items/definitions.py`, `catalog.py`)

`ItemDefinition` is frozen, shared data. It contains:

- a stable `item_id` (lower_snake_case, used in saves)
- `name`, `category`, `description` and `rarity`
- `max_stack`: 1 means the item doesn't stack. Equippable and unique items
  never stack.
- `base_value` (for merchants from MC-007)
- `unique`: the owner may hold at most one, counting both inventory and
  equipment. It is the hook for future one-of-a-kind items; none exist yet.
- `sellable` (quest items are never sellable)
- exactly one payload that matches the category: `weapon` (an MC-002
  `Weapon`), `armor` (an `ArmorProfile`) or `consumable` (a
  `ConsumableEffect`)

The categories are weapon, armor, consumable, material, quest and misc.
Runtime state (quantities, who holds what) lives in `Inventory` and
`Equipment`, never in definitions.

The catalog has 20 items: the 5 MC-002 weapons wrapped as items, 7 armor
pieces, 3 consumables, 3 materials, 1 misc item and 1 quest item.

## Rarity

The tiers are Common, Uncommon, Rare, Epic and Unique. The names and value
multipliers (1.0, 1.5, 2.5, 4.0 and 6.0) are **non-final**. Rarity scales
**value only**; an item's power always comes from its own stats, so a
common item can beat an uncommon one.

## Inventory (`game/items/inventory.py`)

- It has a fixed number of slots (20 by default). Stacks fill the existing
  stacks of that item first, in slot order, then new slots.
- `add` and `remove` are all-or-nothing and return an `InventoryResult`
  with one of these statuses: OK, INVENTORY_FULL, INVALID_QUANTITY,
  NOT_ENOUGH, UNIQUE_OWNED or INVALID_SLOT. A failed call changes nothing, so
  items are never duplicated or silently lost.
- It also has `count`, `has`, `space_for`, `can_add_all` (to check that a
  whole reward fits before granting it), `split` and `copy`.
- `from_list` treats save data as untrusted. It rejects unknown items,
  quantities that aren't integers or fall outside 1..max_stack, too many
  stacks, unexpected keys and duplicated unique items.

## Equipment and stat modifiers (`game/equipment/slots.py`, `loadout.py`)

- The slots are `main_hand` (the weapon), `head`, `chest`, `hands`, `legs`
  and `feet`.
- `Equipment` accepts anything *equippable*: a bare MC-002 `Weapon` (so the
  old API still works) or an `ItemDefinition`.
- `StatModifiers` are flat, non-negative bonuses to the attributes
  durability, magic resistance, physical strength, magic power, speed and
  agility. They never touch pool maximums (health, mana, stamina), so
  equipping can't leave current HP above its maximum. Modifiers for pools are
  deferred.
- **Reversibility:** `Player` records the total bonus it has applied. On
  every equip or unequip it applies only the difference, rounded, so 500
  equip/unequip cycles leave the stats exactly unchanged (this is tested).
  `player.base_stats()` returns the stats without equipment bonuses; that is
  what gets saved.
- Armor raises durability and magic resistance, and so lowers damage
  through the existing formula. The minimum-damage floor still applies, so
  armor never grants immunity.

## Item actions (`game/items/actions.py`)

These validate first and mutate second, so a failure never leaves the
player half-changed:

- `give_item`: respects unique ownership across inventory *and* equipment.
- `equip_from_inventory`: the item leaves the inventory, and whatever was
  already in that slot goes back into the freed inventory slot.
- `unequip_to_inventory`: refuses with INVENTORY_FULL and keeps the item
  equipped when there's no room.
- `use_item`: consumables respect the stat caps. It refuses with NO_EFFECT
  (and keeps the item) when the potion would do nothing, and refuses when the
  player is dead or the item isn't a consumable.

## Loot (`game/items/loot.py`, `loot_tables.py`, `ground.py`)

- A `LootTable` has explicit `LootEntry` items. Each has a `chance`, where
  1.0 means guaranteed, and a min/max quantity. A table can also have an
  optional weighted `pool` with a "nothing" option, from which it picks
  `pool_picks` times.
- **Randomness is injected** as a `random.Random`. The same seed always
  gives the same drops, and guaranteed entries with a fixed quantity don't
  use the RNG at all.
- There is one table per archetype: goblin, striker, archer and brute. The
  brute always drops iron scrap and a potion, plus one weighted armor roll.
- `Encounter.take_defeated()` reports each dead enemy **exactly once**. The
  session handles each report in one place: XP, then a loot roll, then a
  `LootDrop` on the ground (`GroundLoot`).
- **Pickup** (G) takes each stack if it fits. Anything that doesn't fit
  stays on the ground (PARTIAL), and nothing is lost.

## Save schema v3

The player save now holds `stats` as **base** stats, plus
`equipment: {slot: item_id}` and `inventory: [{item, qty}]`. Version-2 saves
are migrated: `equipped_weapon` becomes `equipment.main_hand`, and the
inventory starts empty. The item's slot is validated against the slot it's
saved in, and unique items can't be duplicated.
