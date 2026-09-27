# Zones, exploration and world navigation (MC-006)

This is the **PROTOTYPE / NON-CANON world**: three placeholder zones. It is
not the Royal Kingdom or any canonical geography. Nothing here depends on
Pygame.

```
Prototype Village (SAFE)  <->  Prototype Road (WILD)  <->  Prototype Wilds (WILD)
  Village Elder                  Scout                        Raider camp (respawns)
  Village Square (POI)           Road ambush (respawns)       Brute's den (never respawns)
                                 Old Milestone (POI, +15 XP)  Old Watchtower (POI, +25 XP)
```

## Model (`game/world/zones.py`, `zone_catalog.py`)

- `ZoneDefinition` holds:
  - an ID, name and `ZoneKind` (SAFE or WILD)
  - a size (800×600, one screen per zone)
  - named spawn points, which must include `default`
  - exits
  - encounter placements
  - points of interest
- `ZoneExit` is a rectangle. Walking into it travels to `target_zone` at
  `target_spawn`.
- `EncounterPlacement` places an MC-003 encounter with a `RespawnRule`:
  **ON_REENTRY** rebuilds it at full strength every time you enter the zone;
  **NEVER** means it stays gone once cleared, and that is saved.
- `PointOfInterest` is a named spot with a discovery radius and an optional
  one-time XP reward.
- `WorldGraph` validates the whole world when it loads:
  - every exit leads to an existing zone and spawn
  - no arrival spawn sits inside an exit (which would travel you in a loop)
  - SAFE zones host no encounters
  - IDs are unique
  - every encounter and NPC reference exists
- NPCs belong to zones through `NpcDefinition.location_id`; `npcs_in(zone)`
  lists them.

## Runtime (`game/world/zone_instance.py`, `game/world_session.py`)

- `ZoneInstance` holds the live encounters and ground loot of the zone
  you're in. It is **rebuilt on every entry and discarded when you leave**,
  so leaving mid-fight resets that fight. Loot left on the ground is lost
  (a prototype rule).
- `WorldSession` extends the shared `PlaySession` (see ARCHITECTURE):
  - **Travel:** walk into an exit, or call `travel(exit_id)`. It returns
    `TravelStatus` (OK, UNKNOWN_EXIT, DEAD, IN_CONVERSATION). It publishes
    `ZoneLeft`, `ZoneEntered` and `LocationReached(zone_id)`, so REACH
    objectives can target a whole zone.
  - **Discovery:** entering a POI's radius records it, publishes
    `LocationReached(poi_id)`, and grants its XP once through the reward
    ledger (`discovery:<poi>`).
  - **Safe zones:** attacks, spells, block and parry input are ignored in
    SAFE zones. Movement, dodge, talking and items still work. The final
    Magical Conquest PvP safe-zone rules are **not** defined here.
  - **Death and respawn:** R revives you in the village at full health.
    There are **no penalties**; XP or stat loss rules are deferred.
    `fail_on_death` quests fail, and other quests keep their progress.
- **World time** is the single MC-001 `WorldState` clock. It keeps ticking
  across travel; zones don't have clocks of their own.

## Persistence (save schema v5)

- `campaign.exploration` records `visited_zones`, `discovered` (POI IDs)
  and `cleared` (`zone/placement` for NEVER encounters).
- `campaign.location` is `{zone, x, y}`, or `null` for the start of the
  world.
- Loading rejects: unknown zones or POIs, coordinates outside the zone or
  not finite, a "cleared" entry that isn't a NEVER placement, and a
  discovery reward claimed for a place never discovered.
- Version-4 saves migrate with nothing explored, starting in the village.
- Encounter state inside a zone is transient and never saved.

## Demo

`python main.py` now opens the world. `python main.py --arena` opens the
MC-002 to MC-005 encounter sandbox (N cycles scenarios there).
