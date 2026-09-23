# Magical Conquest

Magical Conquest is a fantasy RPG concept, with the long-term goal of becoming an
MMORPG. It is built around player freedom, skill-based real-time combat,
meaningful death, a persistent living world, magic, PvP and PvE, guilds,
dungeons, dynamic world events, and a player/NPC economy.

**This repository is not an MMO yet, and it is not the final game.** It holds a
small Python + Pygame systems prototype (milestone MC-001) for building and
testing the core rules before they move to a more capable 3D engine.

## Current status (MC-001)

Implemented:

- Reusable stat model: health, mana and stamina pools, plus physical strength,
  magic power, magic resistance, durability, speed and agility. All values
  are validated.
- A base `Entity` shared by players and enemies, with a unique ID, name,
  level, stats, position and alive/dead state.
- Deterministic combat with physical and magic attacks, defense and
  resistance, resource costs, cooldowns and death detection. Level is never
  part of the damage calculation, so there is no invulnerability from level.
- A player with movement state, XP and levels. XP can trigger several level-ups
  at once, and each level grants stats from a formula-based curve.
- One test enemy (a goblin) that chases the player, attacks in range with a
  cooldown, and dies through the normal combat rules.
- A `DeathRecord` created when an entity reaches 0 HP. Dead entities ignore
  further damage.
- A world clock (time, day) and a registry of active world events, all
  independent of rendering.
- JSON save/load with a schema version. Missing, malformed and
  unsupported save files are all handled without crashing.
- A lightweight Pygame demo that draws only rectangles.
- Unit tests for the core rules. They run without Pygame.

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

| Key    | Action                                       |
|--------|----------------------------------------------|
| W A S D | Move                                        |
| Space  | Melee strike (physical, costs stamina)       |
| E      | Fire bolt (magic, ranged, costs mana)        |
| F5     | Save                                         |
| F9     | Load                                         |
| R      | Restart (for example, after dying)           |
| Esc    | Quit                                         |

After a goblin dies, a new one appears a few seconds later at the player's current level.

## Running the tests

```sh
python -m unittest discover -s tests -v
python -m compileall -q .
```

The tests use only the standard library. They open no window and need no network access.

## Architecture

```
main.py                     entry point (argument parsing only)
game/
  core/        stats.py, entity.py, combat.py, vector.py   engine-independent rules
  entities/    player.py, enemy.py                         concrete entity types
  progression/ experience.py, growth.py                    XP curve and per-level stat growth
  world/       world_state.py                              world clock and active events
  persistence/ save_manager.py                             JSON save/load, schema versioning
  session.py                                               headless game loop (input -> rules)
  presentation/pygame_app.py                               the only module that imports Pygame
tests/                                                     unittest suite
data/                                                      runtime data (saves are git-ignored)
docs/ARCHITECTURE.md                                       design notes
```

For the details, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Not implemented yet

Everything beyond the MC-001 foundation is not implemented, including:

- multiplayer networking, servers, regions and sharding
- the world map, dungeons and instances
- guilds, the Holy Church, the economy and the Grand Arena
- boss and monster races (Dragon Kings, Arch Demons, werewolves, and others)
- the magic rank system, abilities, equipment and inventory
- death penalties (dungeon or PvP XP loss), respawn rules and loot
- a scheduler for world events (the event registry exists, but nothing creates events on its own yet)
- final graphics, sprites, audio and animation
