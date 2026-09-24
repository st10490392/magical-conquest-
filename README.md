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

### MC-003: enemy intelligence and encounters

- **Headless, deterministic enemy AI** with explicit states: idle, alert,
  approach, position, telegraph, attack, recover, retreat, staggered and
  dead. There is no randomness.
- **Perception:** a detection range, plus a larger disengage range so enemies
  don't flicker in and out of combat. A short "alert" reaction delay when an
  enemy notices you.
- **Attack lifecycle:** every enemy attack goes telegraph (wind-up) → active
  (resolved through the normal MC-002 combat rules) → recovery. The telegraph
  and recovery times are set per attack.
- **Three archetypes that behave differently:**
  - **Striker (melee):** closes in, tracks you slightly during its wind-up,
    then has a short recovery.
  - **Archer (ranged):** holds a distance band, backs off (sliding along walls)
    when you get close, and shoots projectiles you can sidestep.
  - **Brute (heavy):** slow and tough. It locks onto where you stood, winds up
    for a long time, then lunges and slams hard. Its long recovery is your
    punish window.
- **Parry consequence:** a successful parry of a melee attack staggers the
  enemy (1.2 s for the striker, 1.8 s for the brute).
- **Encounters** track their enemies, whether they have started, whether they
  are active, cleared or failed (the player died), and how long they have run.
  They are reusable for dungeons, events and other content later.
- **Multiple enemies:** one group alert, one melee attack token (melee enemies
  take turns winding up), and enemies keep apart from each other.
- **Pygame demo:** starts with a 3-enemy mixed skirmish. You can also cycle to
  single-archetype drills and the MC-002 goblin training loop.

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
| N | Next encounter: mixed skirmish, striker drill, archer drill, brute drill, goblin training |
| R | Restart the current encounter |
| Esc | Quit |

You can't attack while blocking or dodging. Blocking halves your movement
speed, and stamina doesn't regenerate while you block or dodge.

The demo character starts at level 1 with an Iron Sword. They have the Fire,
Ice, Wind, Lightning and Light attributes and know all 9 prototype spells.
Only Fire Bolt can be cast at first: some spells need an attribute the
character lacks (Water, Air, Earth, Thunder), and others need more magic power.
The HUD shows why a spell can't be cast. Magic power grows with level, so
Ice Shard and Wind Cutter unlock at level 4.

Your attacks and spells target the **nearest living enemy**.

Visual cues (debug-quality on purpose; a later engine replaces them):

- **Enemy shapes:** squares are melee enemies (red for the striker and goblin,
  brown and larger for the brute). A purple circle is the archer.
- **Orange enemy + "TELEGRAPH":** an attack is winding up. The bar under the
  enemy fills until it releases.
  - An **orange ring** shows where a melee attack will reach. For the brute,
    the ring is centred on its locked aim point, so step out of it.
  - An **orange line** from the archer is its aim. Sidestep the arrow (the
    small white dot) or dodge it.
- **Grey + "OPEN":** the enemy is recovering after an attack. Punish it.
- **Yellow + "STAGGER":** you parried it. Punish it.
- **"!"** means the enemy just noticed you; **"retreat"** means the archer is
  backing off.
- **Top right:** the encounter name, its status and time, and each enemy's
  archetype, HP, state and timer.
- **Your own defense:** a yellow outline means you are blocking, a white
  outline means your parry window is open, and a light blue player is dodging.

#### Suggested playtest checklist (MC-003)

1. **Striker drill:** parry just before the strike lands and confirm the
   stagger. Then try a dodge and a block.
2. **Archer drill:** close the distance while it retreats, and sidestep
   arrows.
3. **Brute drill:** watch the long wind-up, step out of the ring, then punish
   the "OPEN" recovery.
4. **Mixed skirmish:** check that the melee enemies take turns and that the
   fight is readable.

## Running the tests

```sh
python -m unittest discover -s tests -v
python -m compileall -q .
```

The tests use only the standard library, and they open no window and need no
network access. They include headless simulations: a scripted player fights
full encounters tick by tick, and the same simulation run twice must produce
identical results.

**What the tests do and don't show:** they prove the rules are correct and
deterministic. They don't tell you whether combat feels good. That needs a
human playtest.

## Architecture

```
main.py                     entry point (argument parsing only)
game/
  core/        stats, entity (+ DeathContext), combat, defense, vector
  ai/          states, perception, attack lifecycle, behaviours, projectiles,
               attack tokens, combat space (all headless)
  encounters/  encounter lifecycle + prototype encounter catalog
  magic/       attributes, ranks, spells, catalog, casting, spellbook
  equipment/   weapons, catalog, loadout (equipment slots)
  entities/    player, enemy (shared AI driver), archetypes (striker/archer/brute)
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
- Enemy blocking, parrying and dodging. Enemies telegraph, but never defend
  themselves.
- Stealth, line of sight, aggro/threat tables, pathfinding and obstacles.
  Enemies move in straight lines, and only the archer slides along walls.
- A posture/break system (a parry only causes a fixed stagger), enemy
  combos, and more than one attack per enemy.
- Dungeon rooms, loot, quests, and werewolf, vampire, dragon or boss AI.
- Saving encounters. Encounters and AI states are not saved; loading
  restarts the current encounter.
- A scheduler that starts world events automatically.
- Final graphics, sprites, audio and animation.
