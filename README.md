# Magical Conquest

Magical Conquest is a fantasy RPG concept, with the long-term goal of becoming an
MMORPG. It is built around player freedom, skill-based real-time combat,
meaningful death, a persistent living world, magic, PvP and PvE, guilds,
dungeons, dynamic world events, and a player/NPC economy.

**This repository is not an MMO yet, and it is not the final game.** It holds a
small Python + Pygame systems prototype for building and testing the core
rules before they move to a more capable 3D engine.

> **All balance numbers in this prototype (stats, spells, weapons, block,
> parry and dodge timings) are NON-FINAL prototype values.**

## Current status

### MC-001: core foundation

- A reusable, validated stat model (health, mana and stamina pools, plus physical
  strength, magic power, magic resistance, durability, speed and agility).
- A base `Entity` shared by players and enemies.
- Deterministic physical and magic combat. Level is never part of the damage
  calculation.
- XP and levels from a formula, with multiple level-ups per award.
- A goblin test enemy, and a `DeathRecord` when an entity dies.
- A world clock and a registry of active world events.
- JSON save/load with a schema version.
- A Pygame demo drawn with rectangles only.

### MC-002: combat and magic foundation

- **Magic attributes:** Fire, Water, Ice, Wind, Air, Earth, Lightning, Thunder
  and Light. Wind and Air are separate attributes, as are Lightning and
  Thunder. An entity can hold any number of them.
- **Spell ranks** E < D < C < B < A < S, as an ordered enum. Each rank sets
  a minimum magic power for its spells.
- **Data-driven spells**, with requirements enforced when casting: the caster
  needs the spell's attribute, the minimum level, and the minimum magic power
  for the spell and its rank. A new character cannot cast an S-rank spell.
  There are 9 prototype spells (one per attribute), across ranks E to A.
- **Per-spell cooldowns**, plus a spellbook of known spells with a selected spell.
- **Data-driven weapons:** sword, greatsword, dagger, spear and staff, each
  with its own power, strength scaling, reach, stamina cost, speed, and
  block/parry ability.
- **Equipment:** equip or unequip a main-hand weapon, and attack with it.
  With no weapon, the player fights unarmed.
- **Blocking** needs a weapon that can block. It absorbs part of each hit and
  spends stamina for what it absorbs. The guard breaks when stamina runs out,
  and a block never absorbs everything.
- **Parrying** needs a weapon that can parry. It opens a short timing window
  and costs stamina. A physical attack that lands inside the window is
  negated; outside the window it hits normally.
- **Dodging** costs stamina and gives a short window in which attacks miss. It
  has a cooldown, so it can't be spammed.
- **Structured outcomes:** hit, blocked, parried, dodged, out of range, not
  enough stamina/mana, on cooldown, and each failed spell requirement.
- **PvP-compatible:** player vs enemy, player vs player and enemy vs player
  all use the same `resolve_attack`.
- **Death contexts:** open world, PvP, dungeon and world event, stored on each
  death record. PvP is detected automatically; no penalties are applied yet.
- The **goblin telegraphs** each attack with a short wind-up (it turns
  orange), so parries and dodges can be timed.
- **Save schema v2.** MC-001 (v1) saves are migrated automatically.

## Requirements

- Python 3.10 or newer
- Pygame 2.x, needed only for the playable demo; the tests don't use it

```sh
pip install -r requirements.txt     # or: sudo pacman -S python-pygame
```

## Running the demo

```sh
python main.py
```

Options:

- `--save PATH` sets the save file. The default is `data/saves/savegame.json`, relative to the repo.
- `--frames N` quits automatically after N frames, for smoke tests.

### Controls

| Input | Action |
|---|---|
| W A S D | Move |
| Space / left mouse (hold) | Attack with the equipped weapon (or unarmed) |
| 1–9 | Select a known spell |
| E (hold) | Cast the selected spell |
| Tab | Cycle weapons: sword, greatsword, dagger, spear, staff, unarmed |
| F / right mouse (hold) | Block (only with a weapon that can block) |
| Q | Parry (only with a weapon that can parry) |
| Shift | Dodge (dashes in your movement direction) |
| F5 / F9 | Save / load |
| R | Restart |
| Esc | Quit |

You can't attack while blocking or dodging. Blocking halves your movement
speed, and stamina doesn't regenerate while you block or dodge.

The demo character starts at level 1 with an Iron Sword. They have the Fire,
Ice, Wind, Lightning and Light attributes and know all 9 prototype spells.
Only Fire Bolt can be cast at first: some spells need an attribute the
character lacks (Water, Air, Earth, Thunder), and others need more magic power.
The HUD shows why a spell can't be cast. Magic power grows with level, so
Ice Shard and Wind Cutter unlock at level 4.

Visual cues:

- An **orange** goblin is winding up an attack. Parry just before it strikes.
- A **yellow** outline means you are blocking.
- A **white** outline means your parry window is open.
- A **light blue** player is dodging.

## Running the tests

```sh
python -m unittest discover -s tests -v
python -m compileall -q .
```

The tests use only the standard library, and they open no window and need no
network access.

## Architecture

```
main.py                     entry point (argument parsing only)
game/
  core/        stats, entity (+ DeathContext), combat, defense, vector
  magic/       attributes, ranks, spells, catalog, casting, spellbook
  equipment/   weapons, catalog, loadout (equipment slots)
  entities/    player, enemy
  progression/ experience curve, per-level stat growth
  world/       world clock and active events
  persistence/ JSON save/load, schema v2 + v1 migration
  session.py   headless game loop (input -> rules)
  presentation/pygame_app.py   the only module that imports Pygame
tests/         unittest suite (no Pygame needed)
docs/ARCHITECTURE.md
```

For the details, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Save files

Save files are JSON with a `schema_version` field:

- **v1 (MC-001):** player ID, name, level, XP, position and stats, plus the world state.
- **v2 (MC-002):** adds `magic_attributes`, `equipped_weapon`, `known_spells`
  and `selected_spell`.

When a v1 save loads, it is migrated to v2. The migrated character has the
Fire attribute, knows Fire Bolt (selected) and has no weapon, which is exactly
what an MC-001 character could do. Unknown weapons, spells or attributes make
the save count as malformed. Versions newer than 2 are rejected as
unsupported.

## Not implemented yet

- Multiplayer networking, servers, regions, sharding and matchmaking.
- The world map, dungeons and instances, guilds, the Holy Church, the economy,
  crafting, quests and the Grand Arena.
- Boss and monster races, legendary weapons (Dragon Slayer, the Heaven's
  Blessings weapons) and Dragon King abilities.
- Light magic's special reflection/repelling rules.
- Elemental strengths and weaknesses (elements are tracked, but they don't
  change damage yet).
- How characters acquire attributes (the demo assigns them directly).
- Armor, the full inventory, weapon durability and upgrades.
- Death penalties: XP or stat loss, loot loss, event elimination and respawn
  rules. The death context is recorded, but nothing acts on it yet.
- Enemy blocking, parrying and dodging (the goblin only telegraphs).
- A scheduler that starts world events automatically.
- Final graphics, sprites, audio and animation.
