# Magical Conquest prototype architecture (MC-001 to MC-003)

The prototype has two goals: to show that the core rules work, and to keep
those rules portable to a future 3D engine and server. The main design
decision is to keep game rules separate from presentation.

## Layers

```
presentation (Pygame)  ->  session  ->  encounters  ->  entities  ->  ai, magic, equipment, progression  ->  core
                                    \->  world
persistence  ->  entities, magic/equipment catalogs, world, core
```

Dependencies point one way only, and there are no circular imports.

| Package | Knows about | Must not know about |
|---|---|---|
| `game.core` | the standard library | Pygame, files, players, levels, weapons, spells |
| `game.magic` | `core` | Pygame, files, equipment |
| `game.equipment` | `core` | Pygame, files, magic |
| `game.progression` | `core.stats` | Pygame, files |
| `game.ai` | `core` | Pygame, files, concrete enemy types |
| `game.entities` | `core`, `ai`, `magic`, `equipment`, `progression` | Pygame, files |
| `game.encounters` | `ai`, `entities`, `core` | Pygame, files, session |
| `game.world` | the standard library | rendering, entities, input |
| `game.persistence` | entities, world, JSON | Pygame |
| `game.session` | everything except presentation | Pygame |
| `game.presentation` | session, and Pygame | game rules |

`game.core` refers to `MagicAttribute` only in type hints (under
`TYPE_CHECKING`), so at runtime it still depends only on the standard library.

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
- MC-002 adds the `game/magic/` and `game/equipment/` packages. Combat stays
  in `game/core/combat.py`, which MC-002 extends rather than replaces. The
  defensive mechanics live in `game/core/defense.py`, because they apply to
  every entity whatever it is carrying.

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
the cause, the world time and (since MC-002) a `DeathContext`. After that,
the entity ignores all damage. Since MC-002, an entity also carries a set of
magic attributes and a `DefensiveState`, and exposes `guard_profile()`, which
reports what its loadout lets it block or parry. The base entity can do
neither; `Player` derives both from its equipped weapon.

## Combat flow

The combat code is in `game/core/combat.py`. It is pure and deterministic: no
randomness and no clock.

0. For spells only, `cast_spell` first checks the spell's requirements (see
   "Magic" below).
1. `try_attack` checks the attacker's `Cooldown`.
2. `resolve_attack` rejects the attack if the attacker is dead, the target is
   dead, the target is out of reach, or the attacker lacks stamina or mana.
   These rejections cost nothing.
3. The attacker pays the stamina and mana costs. The attack is now executed,
   even if it is then blocked, parried or dodged.
4. `raw = base_power + attribute * scaling`. The attribute is
   `physical_strength` for a physical attack and `magic_power` for a magic one.
5. `mitigated = raw * K / (K + defense)`, with `K = 100`. The defense is
   `durability` against physical attacks and `magic_resistance` against magic.
6. `final = max(mitigated, 10% of raw, 1)`.
7. `apply_defense` checks the defender's active defense, in the order dodge,
   then parry, then block (see "Block, parry and dodge").
8. Any damage left over goes to `defender.receive_damage`, together with the
   death context.
9. Once an attack is executed, the cooldown restarts, shortened by agility:
   `cooldown / (1 + agility/100)`.

Every result is an `AttackResult` with an `AttackOutcome` enum: `HIT`,
`BLOCKED`, `PARRIED`, `DODGED`, `OUT_OF_RANGE`, `NOT_ENOUGH_STAMINA`,
`NOT_ENOUGH_MANA`, `ON_COOLDOWN`, `ATTACKER_DEAD`, `TARGET_DEAD`, or one of
the spell-requirement outcomes. `landed` means damage got through (`HIT` or
`BLOCKED`). `executed` means the attack was performed, whatever the defender
did about it.

Compatibility with MC-001: the `HIT` path is numerically unchanged. The
MC-001 `FIRE_BOLT` and `MELEE_STRIKE` attacks still exist; `FIRE_BOLT` is now
the attack behind the catalog's Fire Bolt spell, and `MELEE_STRIKE` is the
unarmed attack.

**Level never creates invulnerability.** Level is not an input to any damage
function. A higher-level character is tougher only through the stats it has
gained: more health, durability and resistance. Mitigation follows a curve
with diminishing returns, and damage has a floor. So every valid hit deals
some damage, and a level-1 character can kill a level-1000 one given enough
hits (see `tests/test_combat.py` and `tests/test_pvp.py`). PvP and PvE use
exactly the same functions. Blocking cannot break this rule: a weapon's
`block_capability` is capped at 0.9, so at least 10% of every blocked hit
gets through. Parry and dodge only avoid damage inside short windows, on a
cooldown, and they cost stamina.

## Magic (MC-002)

- `MagicAttribute` (`magic/attributes.py`) has nine members: Fire, Water, Ice,
  Wind, Air, Earth, Lightning, Thunder and Light. Wind and Air are separate,
  as are Lightning and Thunder. To add an attribute, add an enum member; the
  combat code never branches on the element. Light has no special rules yet.
- `SpellRank` (`magic/ranks.py`) is an ordered enum, E < D < C < B < A < S.
  `RANK_MIN_MAGIC_POWER` sets a minimum magic power for each rank.
- `Spell` (`magic/spells.py`) is frozen data: ID, name, rank, element, base
  power, magic scaling, mana cost, cooldown, reach, minimum magic power and
  minimum level. `spell.attack` builds the matching combat `Attack`.
  `required_magic_power` is the larger of the spell's own minimum and its
  rank's minimum, so a new character can never cast an S-rank spell.
- `check_spell_requirements` / `cast_spell` (`magic/casting.py`) check, in
  order: that the caster has the element, the minimum level, and the minimum
  magic power. Then the spell goes through `try_attack`. A failed requirement
  costs nothing.
- `SpellBook` (`magic/spellbook.py`) holds the known spells in the order they
  were learned, the selected spell, and a separate `Cooldown` for each spell.
  Learning a spell never bypasses its requirements.
- `magic/catalog.py` holds nine prototype spells, one per attribute, across
  ranks E to A. There is no S-rank spell in the catalog; the tests define
  their own.

## Equipment (MC-002)

- `Weapon` (`equipment/weapons.py`) is frozen data: ID, name, `WeaponType`,
  base power, strength scaling, reach, stamina cost, cooldown,
  `block_capability` (0 means it cannot block) and `can_parry`.
  `weapon.attack` is a physical `Attack`, and `weapon.guard` is a
  `GuardProfile`.
- `Equipment` (`equipment/loadout.py`) maps an `EquipSlot` to an item. Only
  `MAIN_HAND` exists for now. Armor, trinkets and similar items can become new
  slots without changing callers.
- `Player.equip` / `unequip` / `weapon_attack` use the loadout. With no weapon,
  the player fights unarmed with `MELEE_STRIKE`, and can neither block nor
  parry.
- `equipment/catalog.py` holds five prototype weapons, one per type. Legendary
  weapons are out of scope.

## Block, parry and dodge (MC-002)

Each entity has a `DefensiveState` (`core/defense.py`) holding its timers and
flags. The tuning values live in `DefenseConfig`: they are configurable, and
they are NON-FINAL. None of these mechanics is random.

| | Needs | Cost | Effect |
|---|---|---|---|
| Block (held) | a weapon with `block_capability > 0`, and stamina > 0 | `block_stamina_per_damage` for each point absorbed | absorbs `block_capability` of the damage; if stamina runs out, absorbs only what it can afford, then the guard breaks and blocking stops |
| Parry (press) | a weapon with `can_parry`; `parry_recovery` has passed | `parry_stamina_cost` when pressed | opens a `parry_window` (0.2 s). A physical attack resolved inside it deals `parry_damage_ratio` (0) of its damage. Outside the window, attacks hit normally |
| Dodge (press) | `dodge_cooldown` has passed | `dodge_stamina_cost` when pressed | a `dodge_duration` (0.25 s) window in which every attack misses. Dodging drops a block. The session also dashes the player |

By default, weapons parry weapons but not spells (`parry_affects_magic =
False`), and blocking reduces both kinds of damage. Both settings are prototype
choices in `DefenseConfig`.

The goblin has a `windup` (0.35 s) before each claw, during which its state is
`EnemyState.WINDUP`. That wind-up is longer than the parry window, so pressing
parry the moment the wind-up starts is too early. This timing makes parrying a
matter of skill, and it would carry over to multiplayer: the server would
decide whether a strike landed inside the defender's window.

## PvP and death contexts (MC-002)

Combat never checks what kind of entity the target is, so `Player` vs
`Player` works through the same `resolve_attack` (see `tests/test_pvp.py`).

`DeathRecord.context` is a `DeathContext`: `OPEN_WORLD`, `PVP`, `DUNGEON` or
`WORLD_EVENT`, plus an optional `context_id`. `resolve_attack` accepts an
explicit context. Without one, it records `PVP` when both sides have
`is_player_character`, and `OPEN_WORLD` otherwise. Dungeon and world-event
systems will pass their context explicitly.

Penalties (XP loss, loot loss, event elimination, respawn) are deliberately
not implemented. They belong in a later system that reads `DeathRecord`s, for
example from `GameSession.last_player_death`, and never inside the damage
formula.

## Enemy AI (MC-003)

The goal is readable, deterministic game AI: no machine learning, no
behaviour-tree framework, no randomness. Everything is headless. Pygame
only draws what the AI decided.

### The pieces

| Module | Role |
|---|---|
| `ai/states.py` | `AIState`: IDLE, ALERT, APPROACH, POSITION, TELEGRAPH, ATTACK, RECOVER, RETREAT, STAGGERED, DEAD. The old `EnemyState` names (`CHASING`, `WINDUP`, `ATTACKING`) are enum aliases, so they still work. |
| `ai/perception.py` | `PerceptionConfig(detection_range, disengage_range)` and `perceive()`. An enemy notices a target inside the detection range and gives up only beyond the larger disengage range (hysteresis), so it doesn't flicker between states. Dead or missing targets are invalid. |
| `ai/attacks.py` | `EnemyAttack` wraps a combat `Attack` with `telegraph`, `recovery`, `projectile_speed` (None for melee) and `trigger_range`. `AttackLifecycle` holds the phase timers. |
| `ai/behaviors.py` | A `Behavior` returns a `Decision` (state, direction, speed scale, maximum step, and whether it wants to attack). There are hooks for the start of the telegraph, movement during the telegraph, and the moment before the strike. The behaviours are `MeleeBehavior`, `HeavyBehavior` and `RangedBehavior`. |
| `ai/projectiles.py` | Straight-line projectiles. Hits are checked against a line segment, so fast projectiles can't pass through a target between ticks, and they are resolved through `resolve_attack` at impact. |
| `ai/coordination.py` | `AttackCoordinator`: melee attack tokens. |
| `ai/space.py` | `CombatSpace`: the arena bounds, the projectile system, the coordinator, and the death context and ID that an enemy uses while acting. |
| `entities/enemy.py` | `Enemy.update`: the shared driver (see below). |
| `entities/archetypes.py` | `EnemyArchetype` data and the `STRIKER`, `ARCHER` and `BRUTE` archetypes. `create_enemy(id, level, position)` builds one; `goblin` is still available. |

### The shared update

`Enemy.update(dt, target, world_time, space)` handles only what every enemy
has in common, in this order:

1. Tick the cooldown and defense timers.
2. **DEAD:** drop any attack and release the token.
3. **STAGGERED:** count down, and do nothing else.
4. Run perception.
5. If the enemy is mid-attack, run the lifecycle:
   - **TELEGRAPH:** optionally move (the behaviour's hook). When the timer
     runs out, strike: melee attacks go through `resolve_attack` with a range
     check, and ranged attacks launch a projectile. Start the cooldown and
     recovery, and release the token.
   - **RECOVER:** the enemy is committed and does nothing.
6. Not engaged: **IDLE**. Just engaged: **ALERT** for `alert_time`.
7. Otherwise, ask the behaviour for a `Decision`: **APPROACH**, **POSITION**,
   **RETREAT**, or start an attack if the cooldown is ready and, for melee,
   a token is free.

New enemy types (knights, werewolves, bosses...) add a `Behavior` and an
archetype. They don't touch this driver.

### Telegraph -> active -> recovery

- **TELEGRAPH:** lasts `telegraph` seconds. No damage is possible; this is the
  player's window to dodge, parry, block or step away.
- **ATTACK:** a single tick. A melee attack is resolved immediately and checks
  range at that moment, so moving out of reach makes it miss
  (`OUT_OF_RANGE`). A ranged attack launches a projectile aimed where the
  target stands at release, and the projectile resolves on impact.
- **RECOVER:** lasts `recovery` seconds. The enemy doesn't move or attack:
  the punish window.
- The cooldown starts at release. The token is released at the start of
  recovery, so another melee enemy can begin its wind-up while this one
  recovers. That makes the group alternate.

### Archetypes

These are prototype mechanics, not lore species. All values are NON-FINAL.

| | Striker (melee) | Archer (ranged) | Brute (heavy) |
|---|---|---|---|
| Question it asks | read and answer close pressure | close the gap or avoid ranged pressure | spot a committed attack and punish its recovery |
| HP / durability / speed | 70 / 3 / 150 | 45 / 1 / 140 | 260 / 20 / 85 |
| Telegraph / recovery / cooldown | 0.45 / 0.5 / 1.1 s | 0.7 / 0.35 / 1.8 s | 1.1 / 1.3 / 2.2 s |
| Behaviour | approaches; tracks at 35% speed during the telegraph | keeps 170–320 units away; retreats and wall-slides when you are closer; aims when it releases | approaches; locks an aim point, stays rooted, lunges 45 units, big hit |
| Parry stagger | 1.2 s | none (arrows can be parried, but the archer isn't staggered) | 1.8 s |

### Defensive interplay

Enemy hits use the same `resolve_attack` as the player's, so MC-002 dodge,
parry and block apply unchanged at the moment an attack resolves. If a melee
attack is **PARRIED** and the enemy has a `parry_stagger`,
`Enemy.stagger()` cancels its attack, releases its token, and holds it in
STAGGERED. Every telegraph is longer than the parry window (0.2 s), so
parrying the moment a wind-up starts is always too early.

## Encounters (MC-003)

- `EncounterSpec` is frozen data: an ID, a name, a list of `SpawnSpec`s
  (archetype, position, and an optional level that otherwise follows the
  player's), an optional `trigger_range`, `max_melee_attackers`,
  `group_alert`, `repeat_on_clear` and a `DeathContext`.
- `Encounter` builds the enemies, one `ProjectileSystem`, one
  `AttackCoordinator` and a `CombatSpace`, then tracks the status (PENDING,
  ACTIVE, CLEARED or FAILED), the elapsed time and the failure reason.
  `update()` returns `CombatEvent`s for the session to report.
- It starts immediately, or when the player comes within `trigger_range`.
  It is **CLEARED** when every enemy is dead, and **FAILED**
  (`player_died`) when the player dies. `fail(reason)` covers other
  interruptions. No penalties are applied.
- With `group_alert`, once one enemy engages, the rest are alerted too, after
  their own reaction delay. A tiny O(n²) separation step keeps enemies from
  overlapping (n is 3 at most).
- The encounter's `DeathContext` and ID are written into death records, so
  later dungeon, event or arena rules can tell deaths apart.
- `GameSession` owns one encounter, targets the nearest living enemy, awards
  XP on kills, and rebuilds `repeat_on_clear` encounters (goblin training).
  `GameSession.new()` still defaults to goblin training; the Pygame demo
  starts on `mixed_skirmish`.

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
are offline. Nothing creates events automatically yet. Only the
registry and the clock exist.

## Persistence

`SaveManager` writes one JSON document:

```json
{
  "schema_version": 2,
  "player": {"id": "...", "name": "...", "level": 1, "xp": 0,
             "position": {"x": 0, "y": 0}, "stats": {"health": 120, "...": "..."},
             "magic_attributes": ["fire", "ice"], "equipped_weapon": "iron_sword",
             "known_spells": ["fire_bolt", "ice_shard"], "selected_spell": "fire_bolt"},
  "world": {"time": 0.0, "day_length": 600.0, "events": []}
}
```

- Weapons and spells are stored by catalog ID. An unknown ID, an unknown
  attribute, or a selected spell the character doesn't know makes the save
  `MALFORMED`.
- Migrations: `_MIGRATIONS` maps each old version to a function that
  upgrades it by one step, and loading applies them in a chain. v1 (MC-001)
  becomes v2 with the Fire attribute, Fire Bolt known and selected, and no
  weapon, which is exactly what an MC-001 character could do. Any other
  version is rejected as `UNSUPPORTED_VERSION`.
- Cooldowns and defensive timers are not saved; they reset on load.
- MC-003 doesn't change the save format (it is still v2). Encounters and AI
  state (telegraphs, recovery, stagger) are transient and never saved.
  Loading a save restarts the current encounter with the loaded player.

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
  rectangles and outlines.
- Spell and weapon attacks and guard profiles are built once per definition
  (`cached_property`), not every frame.
- Enemy AI is a finite-state machine that uses plain distance checks. There is
  no pathfinding, no physics and no per-frame allocation beyond a few small
  value objects. Encounters use 1–3 enemies.
- The frame rate is capped at 60 FPS, and `dt` is clamped after stalls.

## Future migration considerations

- `core`, `progression`, `world` and `persistence` are plain Python with
  data-only definitions (`Attack`, `Spell`, `Weapon`, `DefenseConfig`,
  `StatGrowth`, `ProgressionCurve`). They can
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
- The spell and weapon catalogs are Python tuples today. They could move to
  data files (JSON) under `data/` without changing the `Spell` or `Weapon`
  types.
