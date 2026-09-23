# Magical Conquest prototype architecture (MC-001)

The prototype has two goals: to show that the core rules work, and to keep
those rules portable to a future 3D engine and server. The main design
decision is to keep game rules separate from presentation.

## Layers

```
presentation (Pygame)  ->  session  ->  entities / progression  ->  core
                                    \->  world
persistence  ->  entities, world, core
```

Dependencies point one way only, and there are no circular imports.

| Package | Knows about | Must not know about |
|---|---|---|
| `game.core` | the standard library | Pygame, files, players, levels |
| `game.progression` | `core.stats` | Pygame, files |
| `game.entities` | `core`, `progression` | Pygame, files |
| `game.world` | the standard library | rendering, entities, input |
| `game.persistence` | entities, world, JSON | Pygame |
| `game.session` | everything except presentation | Pygame |
| `game.presentation` | session, and Pygame | game rules |

`game.presentation.pygame_app` is the only module that imports `pygame`. The
tests import everything else, and they check that the full demo loop runs
headlessly through `GameSession`.

### Deviations from the suggested layout

- `game/core/vector.py` is a small, immutable `Vec2`. It lets positions and
  movement work without `pygame.math`.
- `game/progression/growth.py` holds the per-level stat increases. These are
  kept separate from the XP curve, so that players and monsters can share
  one curve with different growth profiles.
- `game/session.py` is the loop behind the demo: input intent, then
  movement, attacks, enemy AI, regeneration, XP and respawning. It lives
  outside `presentation`, so the tests and a future server can run the same
  loop without a window. Pygame only converts key presses into a
  `PlayerInput` and draws rectangles.

## Entities and stats

`Stats` holds three resource pools (`health`, `mana`, `stamina`), each with a
maximum, plus six attributes: `physical_strength`, `magic_power`,
`magic_resistance`, `durability`, `speed` and `agility`. It has no concept of
players or levels.

- Every value must be a finite, non-negative number, and a pool can never
  exceed its maximum. Invalid values raise `TypeError` or `ValueError`.
- `consume_*` is all-or-nothing and returns a success flag. `restore_*` and
  `heal` clamp to the maximum. Dead entities cannot be healed.
- `max_health` must be greater than 0. The other maximums may be 0; the
  goblin, for example, has no mana.

`Entity` adds an ID (a UUID hex string), a name, a level (an integer of 1 or
more), a position and a size. `Player` and `Enemy` subclass `Entity`.
`Entity.receive_damage` is the only path that can kill an entity. When health
first reaches 0, it creates a frozen `DeathRecord` with the entity, the killer,
the cause and the world time. After that, the entity ignores all damage.

## Combat flow

The combat code is in `game/core/combat.py`. It is pure and deterministic: no
randomness and no clock.

1. `try_attack` checks the attacker's `Cooldown`.
2. `resolve_attack` rejects the attack if the attacker is dead, the target is
   dead, the target is out of reach, or the attacker lacks stamina or mana.
   Resources are spent only when the attack lands.
3. `raw = base_power + attribute * scaling`. The attribute is
   `physical_strength` for a physical attack and `magic_power` for a magic one.
4. `mitigated = raw * K / (K + defense)`, with `K = 100`. The defense is
   `durability` against physical attacks and `magic_resistance` against magic.
5. `final = max(mitigated, 10% of raw, 1)`.
6. `defender.receive_damage(final)` is called, and the result reports the
   damage and any death.
7. On a hit, the cooldown restarts, shortened by agility:
   `cooldown / (1 + agility/100)`.

**Level never creates invulnerability.** Level is not an input to any damage
function. A higher-level character is tougher only through the stats it has
gained: more health, durability and resistance. Mitigation follows a curve
with diminishing returns, and damage has a floor. So every valid hit deals
some damage, and a level-1 character can kill a level-1000 one given enough
hits (see `tests/test_combat.py`). PvP and PvE use exactly the same functions.

## Progression

`ProgressionCurve` computes the XP needed for the next level as
`xp_to_next(level) = round(base * level ** exponent)`, with an optional
`max_level`. The curve is a formula, not a table, so very high level caps
cost nothing. `Experience.add` rolls over as many thresholds as the XP covers,
so a single award can give several levels. The level itself lives on the
entity, so it isn't stored twice. `StatGrowth` applies flat increases for each
level gained. The numbers are placeholders, and nothing is balanced for high
levels yet.

## World state

`WorldState` tracks the world time in seconds, a configurable day length,
the resulting 1-based `day` and `time_of_day`, and a dictionary of active
`WorldEvent`s. Each event has an ID, a kind, a name, a start time, an
optional duration and free-form `data`. `tick(dt)` advances time and returns
the events that expired.

`WorldState` does not reference rendering, input or players. That makes it
the base for later systems (dragon attacks, periodic Arch Demon events, NPC
routines, market drift, guild events) that must run on a server while players
are offline. In MC-001, nothing creates events automatically. Only the
registry and the clock exist.

## Persistence

`SaveManager` writes one JSON document:

```json
{
  "schema_version": 1,
  "player": {"id": "...", "name": "...", "level": 1, "xp": 0,
             "position": {"x": 0, "y": 0}, "stats": {"health": 120, "...": "..."}},
  "world": {"time": 0.0, "day_length": 600.0, "events": []}
}
```

- Writes are atomic: the file goes to a temp file, then `os.replace`.
- `load()` never raises for bad input. It returns a `LoadResult` with one of
  these statuses: `OK`, `MISSING`, `MALFORMED` or `UNSUPPORTED_VERSION`.
- Loaded data goes through the normal constructors, so the stat validation
  also applies to save files.
- Serialization lives in the persistence layer, not in the entities, so the
  file format can change without touching the rules.
- The default path is resolved relative to `main.py`
  (`data/saves/savegame.json`), and Git ignores it.

## Performance notes

The prototype targets a machine with about 2 GB of RAM:

- The only dependency is Pygame.
- Only the display and font subsystems are initialized; audio is not.
- There are no images, sprites or other assets. Everything is drawn as
  rectangles.
- The frame rate is capped at 60 FPS, and `dt` is clamped after stalls.

## Future migration considerations

- `core`, `progression`, `world` and `persistence` are plain Python with
  data-only definitions (`Attack`, `StatGrowth`, `ProgressionCurve`). They can
  be ported to C#/C++/GDScript almost line by line, or they can stay as the
  authoritative server rules while a 3D client handles presentation.
- `GameSession` is a model for a server tick: it takes intents in, advances
  the simulation deterministically, and lets clients render the state.
  Networking would replace `PlayerInput` with messages from clients.
- `Vec2` would become a 3D vector. Combat already works on distances, not on
  screen coordinates.
- `schema_version` allows save migrations. A real database would replace
  `SaveManager` behind the same `LoadResult` interface.
- Entity IDs are UUIDs, so they are already globally unique for a
  multi-server setup.
