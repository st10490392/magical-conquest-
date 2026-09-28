# The connected vertical slice (MC-008)

MC-008 adds no big systems. It **connects and hardens** MC-001 to MC-007
into one small RPG loop. All content is **PROTOTYPE / NON-CANON**, and all
numbers are **NON-FINAL**.

## The loop

1. Start (`python main.py`) or resume (`python main.py --load`, or F9 in game).
2. You wake in the **Prototype Village** (a safe zone). The Village Elder
   shows **!**, meaning a quest is available.
3. Talk to the elder (G) and accept **Clear the Raider Camp** (reply 1).
4. Leave east for the **Prototype Road**. The road ambush (an archer and a
   striker) uses MC-003 AI: it notices you, telegraphs, attacks and recovers.
5. Continue east into the **Prototype Wilds** and defeat the raider camp's two
   strikers. Use your weapon, spells (E), dodge (Shift), block (F) and parry
   (Q). The objective tracker in the top right counts the kills.
6. Pick up the loot (G) and check it or equip it from the inventory (I).
7. Return west to the village. The elder now shows **?**. Turn the quest in
   for XP, coins and potions.
8. Sell unwanted loot to the Blacksmith and buy gear or consumables from the
   Shopkeeper or the Blacksmith. Equip it from the inventory (I).
9. Save (F5), quit (Esc), run `python main.py --load`, and check that
   everything is where you left it.

Optional extras: the scout on the road (the watchtower quest), the
"Strange Bones" chain quest, the brute's den (it pays out once and never
respawns) and the points of interest.

## Integration fixes found while connecting systems

These were real bugs, fixed in the domain rather than worked around in the
UI:

- **Opening a shop left the conversation open.** The session then still
  counted as in a conversation, which blocked saving and travel. Before, the
  Pygame loop hid this with a workaround. Now `open_shop` ends the
  conversation itself, and the workaround is gone.
- **Death didn't close an open shop.** Death now closes the conversation and
  the shop, and respawning does the same.
- **Trading with no shop open used to crash.** Buy and sell now return
  `NO_SHOP_OPEN`, and inspect returns nothing.
- **Travel while a shop was open.** It's now refused (`IN_SHOP`), and walking
  into an exit while busy doesn't travel.
- **Saving had no rules.** `PlaySession.save_blocker()` now refuses to save
  while dead or while a conversation or shop is open. The demo and the
  `session_io.save_session` facade both go through it.

## Decisions for the awkward cases (all tested in `tests/test_hardening.py`)

| Case | Behaviour |
|---|---|
| Death during a quest | No penalties. The quest keeps its progress, unless it's `fail_on_death`. R respawns you in the village |
| Death during an encounter | The encounter is FAILED. Coming back later builds it fresh |
| Inventory full when picking up loot | The stacks that don't fit stay on the ground; nothing is lost |
| Inventory full at a reward | Nothing is granted, the quest stays ready, and you can make room and try again |
| Leaving a zone mid-fight | The encounter and its projectiles are discarded. Re-entering rebuilds it at full strength |
| Encounter reset rules | ON_REENTRY encounters respawn; NEVER encounters stay cleared, and that is saved |
| Quest already completed / reward claimed | The reward ledger and quest log refuse it, across save and load |
| Save during an active quest | Counters are saved; the reloaded session's event bus keeps counting |
| Load after changing equipment or trading | Base stats plus equipment give identical stats; wallet and stock persist |
| Dead enemies | Only NEVER placements are remembered; the rest respawn by design |
| World time after travel | One clock; it keeps running across travel and survives save/load |
| Missing or corrupt save | Reported as MISSING or MALFORMED, and the load returns no session |
| Tampered save | Negative coins, impossible stacks, duplicated rewards, bad equipment, NaN or infinite values are all rejected |
| Older saves | v1 → v2 → v3 → v4 → v5 → v6, migrated automatically |

## Not saved (by design, for now)

- Enemy and encounter state inside a zone. Loading rebuilds the zone.
- Ground loot.
- Cooldowns and defense timers.
- Open UI (dialogue, shop, inventory).

## Tests

- `tests/test_vertical_slice.py` plays the whole loop through public APIs
  only, using the scripted player in `tests/slice_driver.py` (walking,
  fighting with parries, G to interact, dialogue choices, shop buy/sell,
  equipping). It then saves, reloads and compares the full state.
- `tests/test_hardening.py` covers the cases in the table above.

## Recommended human playtest checklist

Human playtesting **has not been done yet**; these steps are for the project
owner.

1. **Start:** `python main.py`. You're in the village, the HUD shows zone,
   HP/MP/ST, coins, weapon and spell, and F1 shows the controls.
2. **Movement and safety:** walk around the village. Attacks do nothing
   there; the exit on the east edge is labelled.
3. **Dialogue:** talk to the elder (G). Read the text, take reply 1, and see
   "Quest accepted" and the tracker entry.
4. **Travel:** walk into the east exit. The zone label changes to
   Prototype Road [HOSTILE].
5. **Road ambush:** the archer aims (an orange line) and shoots. Sidestep or
   dodge the arrow. Parry the striker's strike just before it lands and watch
   for the STAGGER tag.
6. **Wilds:** the raider camp wakes when you approach. Check the telegraphs,
   that the two strikers take turns, and that the tracker counts 1/2 and then
   2/2.
7. **Brute (optional):** watch the long wind-up, step out of its ring, and
   punish the grey "OPEN" recovery. It pays out once.
8. **Loot:** yellow diamonds appear. Pick them up with G, open I, and equip
   or use something.
9. **Return:** go back west through the road. The elder shows "?"; turn the
   quest in and check the XP, coins and potions.
10. **Trade:** sell bone shards or iron scrap to the Blacksmith (G, then
    "Show me your wares", then the Sell tab). Buy boots or a potion from the
    Shopkeeper, and use Inspect at the Blacksmith.
11. **Equip:** equip the purchase from I and check the HUD stats change.
12. **Save and load:** press F5, then quit (Esc). Run
    `python main.py --load` and check the zone, position, coins, level,
    inventory, equipment and quest state.
13. **Death:** die on purpose in the wilds, press R, and check that you wake
    in the village with your quest progress intact.
14. **Feel:** is the combat readable? Are the telegraphs long enough on your
    machine? Is the UI understandable? Note anything confusing.
