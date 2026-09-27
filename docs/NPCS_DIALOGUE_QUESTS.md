# NPCs, dialogue and quests (MC-005)

The NPCs, dialogue lines and quests are **PROTOTYPE / NON-CANON** content;
the "raiders", the elder and the scout are placeholders, not Magical
Conquest characters. All reward numbers are **NON-FINAL**. Nothing in this
document depends on Pygame.

## Domain events (`game/events/`)

`EventBus` is synchronous and deterministic:

- Handlers run in the order they subscribed.
- A handler can subscribe to a base class; for example, a `GameEvent`
  handler sees every event.
- An event published *during* dispatch is queued and delivered afterwards,
  first in, first out. Handlers never re-enter each other.

The events are `EnemyDefeated`, `ItemObtained`, `NpcInteracted`,
`LocationReached`, `QuestProgressed` and `QuestStatusChanged`. Quests listen
to events rather than being called by combat, so future guild missions,
village defences, hunts or world events only have to publish the same
events.

## NPCs (`game/npcs/`)

- `NpcDefinition` holds `npc_id`, `name`, `role` (villager, quest giver,
  merchant, blacksmith, scout), `dialogue_id`, `location_id`, `position` and
  `gives_quests`.
- `can_interact()` checks the distance (70 units) and that the player is
  alive.
- `NpcRegistry` stores per-NPC runtime state (how many times you've talked)
  and is saved.

## Dialogue (`game/dialogue/`)

- A `Dialogue` is data. It has **entries** tried in order, where the first
  whose conditions pass is the start node, and the last entry must be an
  unconditional fallback. It also has **nodes**, each with text and
  `DialogueResponse`s.
- A response can have **conditions**, which hide it (and a hidden response
  can't be chosen by index). It can have **effects**, and it leads to
  `next_node`, or to `None` to end the conversation.
- The conditions are quest status (one status or `"a|b"`), has item, flag,
  not flag and minimum level. The effects are accept quest, turn in quest,
  set flag and open shop (a hook for MC-007).
- `Conversation` only talks to a `DialogueContext` protocol (`check` and
  `apply`). `CampaignContext` implements it on top of the quest log,
  inventory and flags, so dialogue never imports quest or item internals.
- Dialogues are validated when they load: unknown nodes, duplicate IDs or a
  missing fallback raise an error.

## Quests (`game/quests/`)

- `QuestDefinition` holds an ID, title, description, objectives, a `Reward`
  (XP, currency and items), the giver and turn-in NPC, prerequisites,
  `consume_collected` and `fail_on_death`.
- **Objective types:**
  - **DEFEAT:** counts `EnemyDefeated` events by archetype.
  - **TALK:** counts `NpcInteracted` events.
  - **REACH:** counts `LocationReached` events.
  - **COLLECT:** counts the items you *hold* right now, so selling or using
    the items un-readies the quest. "Deliver" is COLLECT plus
    `consume_collected`, handed over at the turn-in NPC.
- **Statuses:** only ACTIVE, COMPLETED and FAILED are stored. UNAVAILABLE
  (prerequisites unmet), AVAILABLE and READY_TO_TURN_IN are **derived**, so
  they can't go stale.
- Events only count toward quests that are already active. Counts are
  capped at the required amount.
- **Chains** are `prerequisites`. Quest B stays UNAVAILABLE until quest A is
  COMPLETED.
- **Failure:** `fail_on_death` quests fail when the player dies; the rest
  keep their progress. A FAILED quest can be accepted again, and its progress
  restarts.

## Rewards and duplicate prevention (`game/progression/rewards.py`, `quests/service.py`)

- `RewardLedger` records claimed keys such as `quest:<id>` and is saved.
  `grant_reward` is **all-or-nothing and at most once**. If the items don't
  fit, nothing is granted (no XP, no items) and nothing is recorded.
- `turn_in` checks, in order: the quest is known, it isn't already completed
  or claimed, it's the right NPC, and it's ready. It then simulates handing
  over the collected items and receiving the reward on a *copy* of the
  inventory. Only if that works does it hand over, grant the reward and mark
  the quest completed. A second turn-in returns ALREADY_COMPLETED.

## Save schema v4

A `campaign` section holds `quests`, `npcs`, `flags` and `ledger`. Loading
validates it all against the definitions. A save is rejected as malformed
if it has:

- unknown quests, NPCs or flags
- impossible counts
- a stored derived status
- an active or completed quest whose prerequisite isn't completed
- a quest marked completed that the ledger doesn't show as claimed, or the
  reverse

Version-3 saves migrate with an empty campaign.

## Demo

The Pygame demo opens in the **quest camp** scenario:

1. Talk to the Village Elder (G) and accept "Clear the Raider Camp".
2. Walk east to wake the camp and defeat the two Strikers, then pick up
   their loot.
3. Return to the elder and turn the quest in.
4. Talk to the elder again to get "Strange Bones", talk to the Scout, and
   collect three bone shards (the camp comes back after being cleared).
5. Hand the shards in. The quest tracker in the top right shows your
   progress throughout.
