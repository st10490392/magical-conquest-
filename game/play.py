"""Shared, headless play loop used by every session type.

``PlaySession`` owns what all modes have in common: player input handling
(movement, attacks, spells, block/parry/dodge, weapon cycling), talking to
NPCs, loot pickup and item use, enemy-defeat rewards, quest wiring through
the event bus, and reporting. Subclasses only say *which* encounters and NPCs
exist (``encounters`` / ``npcs``) and add their own per-tick rules:

* ``game.session.GameSession`` - the single-encounter arena sandbox.
* ``game.world_session.WorldSession`` - the zone-based world (MC-006).

The Pygame layer converts keyboard/mouse state into ``PlayerInput`` and
draws a session; nothing here imports Pygame.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from game.ai.space import Bounds
from game.ai.states import AIState
from game.campaign import Campaign, CampaignContext
from game.core.combat import AttackOutcome, AttackResult
from game.core.defense import DefenseAction
from game.core.entity import DeathRecord
from game.core.vector import Vec2
from game.dialogue.catalog import get_dialogue
from game.dialogue.conversation import ChoiceResult, Conversation
from game.economy.blacksmith import GearReport, inspect_equipment
from game.economy.catalog import MERCHANTS
from game.economy.merchant import Merchant, TransactionResult
from game.economy.wallet import CURRENCY_NAME
from game.encounters.encounter import CombatEvent, Encounter, EncounterStatus
from game.entities.enemy import Enemy
from game.entities.player import Player
from game.equipment.catalog import WEAPONS
from game.equipment.slots import EquipSlot
from game.events.bus import EventBus
from game.events.events import (
    EnemyDefeated,
    ItemObtained,
    LocationReached,
    NpcInteracted,
    QuestProgressed,
    QuestStatusChanged,
)
from game.items.actions import ItemActionResult, equip_from_inventory, give_item, unequip_to_inventory, use_item
from game.items.catalog import ITEMS, get_item
from game.items.ground import GroundLoot, PickupStatus
from game.items.loot_tables import get_loot_table
from game.magic.attributes import MagicAttribute
from game.magic.catalog import SPELLS
from game.magic.casting import check_spell_requirements
from game.npcs.catalog import get_npc
from game.npcs.definitions import NpcDefinition, can_interact
from game.progression.rewards import GrantStatus, Reward, RewardGrant, RewardSource, grant_reward, reward_key
from game.world.world_state import WorldState

# PROTOTYPE VALUES - NON-FINAL BALANCE.
STAMINA_REGEN_PER_SECOND = 15.0
MANA_REGEN_PER_SECOND = 4.0
BLOCK_MOVE_MULTIPLIER = 0.5
DODGE_SPEED_MULTIPLIER = 2.8

# Attributes the demo character starts with. Deliberately not all of them,
# so the demo also shows the "missing attribute" requirement.
DEMO_ATTRIBUTES = (MagicAttribute.FIRE, MagicAttribute.ICE, MagicAttribute.WIND, MagicAttribute.LIGHTNING, MagicAttribute.LIGHT)
STARTING_WEAPON_ID = "iron_sword"
# Training kit for the sandbox sessions: every prototype weapon (so TAB can
# cycle them, as in MC-002) plus a few consumables. PROTOTYPE / NON-FINAL.
STARTING_KIT = (
    *((weapon_id, 1) for weapon_id in WEAPONS if weapon_id != STARTING_WEAPON_ID),
    ("minor_health_potion", 2),
    ("minor_mana_potion", 1),
    ("leather_cap", 1),
)

# Order in which TAB cycles weapons; None means unarmed.
WEAPON_CYCLE = (*WEAPONS.keys(), None)


@dataclass(frozen=True)
class PlayerInput:
    """One frame of player intent.

    ``melee``, ``magic`` and ``block`` are held states; ``parry``, ``dodge``,
    ``cycle_weapon`` and ``select_spell`` are one-shot presses.
    """

    move: Vec2 = Vec2()
    melee: bool = False  # attack with the equipped weapon (or unarmed)
    magic: bool = False  # cast the selected spell
    block: bool = False
    parry: bool = False
    dodge: bool = False
    cycle_weapon: bool = False
    select_spell: Optional[int] = None  # 0-based index into the spellbook
    interact: bool = False  # talk to a nearby NPC, else pick up nearby loot


@dataclass
class Arena:
    width: float = 800.0
    height: float = 600.0

    def clamp(self, position: Vec2, margin: float) -> Vec2:
        return position.clamped(margin, margin, self.width - margin, self.height - margin)


def outcome_text(outcome) -> str:
    return outcome.value.replace("_", " ")


def make_demo_player(name: str, position: Vec2, kit=STARTING_KIT) -> Player:
    """The prototype character: demo attributes, every prototype spell known,
    an iron sword and ``kit`` in the bag. PROTOTYPE / NON-FINAL."""
    player = Player(name, position=position, magic_attributes=DEMO_ATTRIBUTES)
    player.equip(get_item(STARTING_WEAPON_ID))
    for item_id, quantity in kit:
        give_item(player, get_item(item_id), quantity)
    for spell in SPELLS.values():
        player.learn_spell(spell)
    return player


@dataclass
class PlaySession:
    player: Player
    world: WorldState = field(default_factory=WorldState)
    arena: Arena = field(default_factory=Arena)
    kills: int = 0
    messages: List[str] = field(default_factory=list)
    last_player_death: Optional[DeathRecord] = None
    ground: GroundLoot = field(default_factory=GroundLoot)
    # Loot randomness; seeded so headless runs are reproducible.
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    campaign: Campaign = field(default_factory=Campaign)
    bus: EventBus = field(default_factory=EventBus)
    conversation: Optional[Conversation] = None
    talking_to: Optional[NpcDefinition] = None
    shop: Optional[str] = None  # merchant id of the open shop, if any

    def __post_init__(self) -> None:
        # Quests react to domain events instead of being called by combat.
        for event_type in (EnemyDefeated, NpcInteracted, LocationReached):
            self.bus.subscribe(event_type, self.campaign.quests.handle)
        self.campaign.quests.attach(self.bus.publish)
        self.bus.subscribe(QuestProgressed, self._on_quest_progress)
        self.bus.subscribe(QuestStatusChanged, self._on_quest_status)

    # ------------------------------------------------------------- hooks
    @property
    def encounters(self) -> List[Encounter]:
        """Encounters currently running. Subclasses decide."""
        raise NotImplementedError

    @property
    def npcs(self) -> List[NpcDefinition]:
        return []

    @property
    def location_id(self) -> Optional[str]:
        """Zone id for events (None outside the zone world)."""
        return None

    def _after_update(self, dt: float) -> None:
        """Mode-specific per-tick rules (respawns, travel, discovery)."""

    def _on_encounter_over(self, encounter: Encounter) -> None:
        if encounter.status is EncounterStatus.CLEARED:
            self.log(f"{encounter.spec.name}: cleared in {encounter.elapsed:.1f}s")
        else:
            self.log(f"{encounter.spec.name}: failed - press R to restart")

    # ------------------------------------------------------------- queries
    @property
    def bounds(self) -> Bounds:
        return (0.0, 0.0, self.arena.width, self.arena.height)

    @property
    def enemies(self) -> List[Enemy]:
        return [enemy for encounter in self.encounters for enemy in encounter.enemies]

    def nearest_enemy(self) -> Optional[Enemy]:
        living = [e for e in self.enemies if e.is_alive]
        return min(living, key=lambda e: e.distance_to(self.player)) if living else None

    @property
    def enemy(self) -> Optional[Enemy]:
        """The nearest living enemy (the player's target), else the first one."""
        nearest = self.nearest_enemy()
        return nearest if nearest is not None else (self.enemies[0] if self.enemies else None)

    def log(self, text: str) -> None:
        self.messages.append(text)
        del self.messages[:-6]  # keep only the recent ones for the HUD

    # ------------------------------------------------------------------ loop
    def update(self, dt: float, controls: PlayerInput) -> None:
        self.world.tick(dt)
        player = self.player
        player.update(dt)

        if player.is_alive:
            self._handle_loadout_input(controls)
            self._handle_defense_input(controls)
            self._move_player(dt, controls)
            if controls.interact:
                self.interact()

        target = self.nearest_enemy()
        busy = player.defense.blocking or player.defense.is_dodging
        if target is not None and player.is_alive and not busy:
            if controls.melee:
                self._player_attack(target, player.weapon_attack(target, self.world.time))
            elif controls.magic:
                self._player_attack(target, player.cast(target, world_time=self.world.time))

        for encounter in list(self.encounters):
            was_over = encounter.is_over
            for event in encounter.update(dt, player, self.world.time):
                self._report_enemy_attack(event)
            for enemy in encounter.take_defeated():
                self._on_enemy_defeated(enemy, encounter)
            if encounter.is_over and not was_over:
                self._on_encounter_over(encounter)
        if not player.is_alive and self.last_player_death is None:
            self.last_player_death = player.death
            self.conversation = None
            for quest_id in self.campaign.quests.on_player_death():
                self.log(f"Quest failed: {self.campaign.quests.definitions[quest_id].title}")
        self._after_update(dt)

    def _handle_loadout_input(self, controls: PlayerInput) -> None:
        player = self.player
        if controls.select_spell is not None and player.spellbook.select_index(controls.select_spell):
            spell = player.spellbook.selected
            problem = check_spell_requirements(player, spell)
            note = f" ({outcome_text(problem)})" if problem else ""
            self.log(f"Selected {spell.name} [{spell.rank.value}-rank {spell.element.label}]{note}")
        if controls.cycle_weapon:
            self.cycle_weapon()

    def cycle_weapon(self) -> None:
        """Equip the next *owned* weapon in catalog order, then unarmed."""
        player = self.player
        current = player.weapon.weapon_id if player.weapon else None
        start = WEAPON_CYCLE.index(current) if current in WEAPON_CYCLE else len(WEAPON_CYCLE) - 1
        for step in range(1, len(WEAPON_CYCLE) + 1):
            candidate = WEAPON_CYCLE[(start + step) % len(WEAPON_CYCLE)]
            if candidate is None:
                if player.weapon is None or unequip_to_inventory(player, EquipSlot.MAIN_HAND).ok:
                    self.log("Unarmed")
                    return
            elif player.inventory.has(candidate) and equip_from_inventory(player, candidate).ok:
                self.log(f"Equipped {get_item(candidate).name}")
                return

    # ------------------------------------------------------- npcs/dialogue
    def nearby_npc(self) -> Optional[NpcDefinition]:
        near = [n for n in self.npcs if can_interact(n, self.player.position, self.player.is_alive)]
        return min(near, key=lambda n: n.position.distance_to(self.player.position)) if near else None

    def interact(self) -> None:
        """G: talk to a nearby NPC, otherwise pick up nearby loot."""
        npc = self.nearby_npc()
        if npc is not None:
            self.talk_to(npc.npc_id)
        else:
            self.pick_up_loot()

    def dialogue_context(self, npc_id: Optional[str] = None) -> CampaignContext:
        return CampaignContext(self.player, self.campaign, npc_id, on_item=self._reward_item,
                               on_open_shop=self.open_shop)

    def talk_to(self, npc_id: str) -> Optional[Conversation]:
        npc = get_npc(npc_id)
        if not can_interact(npc, self.player.position, self.player.is_alive):
            return None
        self.campaign.npcs.record_interaction(npc_id)
        self.bus.publish(NpcInteracted(npc_id))  # TALK objectives count this
        self.talking_to = npc
        self.conversation = Conversation(get_dialogue(npc.dialogue_id), self.dialogue_context(npc_id), npc.name)
        return self.conversation

    def choose_dialogue(self, index: int) -> ChoiceResult:
        if self.conversation is None:
            return ChoiceResult(False, ("No conversation.",))
        result = self.conversation.choose(index)
        for message in result.messages:
            self.log(message)
        return result

    def end_conversation(self) -> None:
        self.conversation = None
        self.talking_to = None

    def _reward_item(self, item_id: str, quantity: int) -> None:
        self.bus.publish(ItemObtained(item_id, quantity, "reward"))

    def _on_quest_progress(self, event: QuestProgressed) -> None:
        title = self.campaign.quests.definitions[event.quest_id].title
        self.log(f"{title}: {event.count}/{event.required}")

    def _on_quest_status(self, event: QuestStatusChanged) -> None:
        pass  # dialogue effects already report accept/complete; hook for UI/achievements

    # ---------------------------------------------------------- economy
    @property
    def coins(self) -> int:
        return self.campaign.wallet.balance

    def open_shop(self, merchant_id: str) -> str:
        """Dialogue effect: open a merchant's shop (the conversation ends)."""
        if merchant_id not in MERCHANTS:
            return f"No such shop: {merchant_id}"
        self.shop = merchant_id
        if self.conversation is not None:
            self.conversation.close()
        return f"Trading with {MERCHANTS[merchant_id].name}"

    def close_shop(self) -> None:
        self.shop = None

    def merchant(self, merchant_id: Optional[str] = None) -> Merchant:
        return self.campaign.merchant(merchant_id or self.shop)

    def buy(self, item_id: str, quantity: int = 1) -> TransactionResult:
        result = self.merchant().buy(self.player, self.campaign.wallet, item_id, quantity)
        name = get_item(item_id).name if item_id in ITEMS else item_id
        if result.ok:
            self.log(f"Bought {name} x{quantity} for {result.total} {CURRENCY_NAME}")
            self.bus.publish(ItemObtained(item_id, quantity, "purchase"))
        else:
            self.log(f"Cannot buy {name}: {outcome_text(result.status)}")
        return result

    def sell(self, item_id: str, quantity: int = 1) -> TransactionResult:
        result = self.merchant().sell(self.player, self.campaign.wallet, item_id, quantity)
        if result.ok:
            self.log(f"Sold {get_item(item_id).name} x{quantity} for {result.total} {CURRENCY_NAME}")
        else:
            self.log(f"Cannot sell: {outcome_text(result.status)}")
        return result

    def inspect_gear(self) -> tuple:
        return inspect_equipment(self.merchant(), self.player)

    def grant(self, source: RewardSource, ident: str, reward: Reward) -> RewardGrant:
        """The single hook for once-only rewards (quests use turn-in)."""
        grant = grant_reward(self.player, reward, reward_key(source, ident), self.campaign.ledger, get_item,
                             self.campaign.wallet, self._reward_item)
        if grant.ok:
            parts = [f"+{reward.xp} XP" if reward.xp else "", f"+{reward.currency} {CURRENCY_NAME}" if reward.currency else ""]
            parts += [f"{get_item(i).name} x{q}" for i, q in reward.items]
            self.log("Reward: " + ", ".join(p for p in parts if p))
        elif grant.status is GrantStatus.INVENTORY_FULL:
            self.log("Reward waiting: make room in your bags")
        return grant

    # ------------------------------------------------------------ items
    def pick_up_loot(self) -> Optional[PickupStatus]:
        drop = self.ground.nearest(self.player.position)
        if drop is None:
            return None
        result = self.ground.pickup(drop.drop_id, lambda item, qty: give_item(self.player, item, qty))
        for item_id, quantity in result.taken:
            self.log(f"Picked up {get_item(item_id).name} x{quantity}")
            self.bus.publish(ItemObtained(item_id, quantity, "loot"))
        if result.left:
            self.log("Inventory full - some loot left on the ground")
        return result.status

    def use_or_equip(self, item_id: str) -> ItemActionResult:
        item = get_item(item_id)
        if item.equip_slot is not None:
            result = equip_from_inventory(self.player, item_id)
            verb = "Equipped"
        else:
            result = use_item(self.player, item_id)
            verb = "Used"
        detail = f" ({result.detail})" if result.detail else ""
        self.log(f"{verb} {item.name}{detail}" if result.ok else f"{item.name}: {outcome_text(result.status)}")
        return result

    def unequip_slot(self, slot: EquipSlot) -> ItemActionResult:
        result = unequip_to_inventory(self.player, slot)
        self.log(f"Unequipped {get_item(result.item_id).name}" if result.ok else outcome_text(result.status))
        return result

    def _handle_defense_input(self, controls: PlayerInput) -> None:
        player = self.player
        if controls.dodge:
            action = player.dodge()
            if action is not DefenseAction.STARTED:
                self.log(f"Dodge: {action.value.replace('_', ' ')}")
        if controls.parry:
            action = player.parry()
            if action is not DefenseAction.STARTED:
                self.log(f"Parry: {action.value.replace('_', ' ')}")
        if controls.block and not player.defense.blocking and not player.defense.is_dodging:
            player.start_block()  # silently does nothing with a weapon that cannot block
        elif not controls.block and player.defense.blocking:
            player.stop_block()

    def _move_player(self, dt: float, controls: PlayerInput) -> None:
        player = self.player
        defense = player.defense
        if defense.is_dodging:
            direction = controls.move if controls.move.length() else player.facing
            player.move(direction, dt * DODGE_SPEED_MULTIPLIER)
        elif defense.blocking:
            player.move(controls.move, dt * BLOCK_MOVE_MULTIPLIER)
        else:
            player.move(controls.move, dt)
        player.position = self.arena.clamp(player.position, player.size / 2)
        if not defense.blocking and not defense.is_dodging:
            player.stats.restore_stamina(STAMINA_REGEN_PER_SECOND * dt)
        player.stats.restore_mana(MANA_REGEN_PER_SECOND * dt)

    # ------------------------------------------------------------- reporting
    def _player_attack(self, target: Enemy, result: AttackResult) -> AttackResult:
        if result.landed:
            note = " (staggered!)" if target.state is AIState.STAGGERED else ""
            self.log(f"You hit {target.name} for {result.damage:.1f}{note}")
        elif result.outcome not in (AttackOutcome.ON_COOLDOWN, AttackOutcome.OUT_OF_RANGE):
            self.log(outcome_text(result.outcome))
        return result

    def _report_enemy_attack(self, event: CombatEvent) -> None:
        name, result = event.attacker.name, event.result
        verb = "shoots" if event.ranged else "hits"
        outcome = result.outcome
        if outcome is AttackOutcome.HIT:
            self.log(f"{name} {verb} you for {result.damage:.1f}")
        elif outcome is AttackOutcome.BLOCKED:
            broken = " - guard broken!" if result.guard_broken else ""
            self.log(f"Blocked {name}: {result.absorbed:.1f} absorbed, took {result.damage:.1f}{broken}")
        elif outcome is AttackOutcome.PARRIED:
            staggered = " - it staggers!" if event.attacker.state is AIState.STAGGERED else ""
            self.log(f"Parried {name}!{staggered}")
        elif outcome is AttackOutcome.DODGED:
            self.log(f"Dodged {name}!")
        elif outcome is AttackOutcome.OUT_OF_RANGE:
            self.log(f"{name} swings and misses")
        if result.killed and event.target is self.player:
            self.log(f"You died ({result.death.context.value}).")

    def _on_enemy_defeated(self, enemy: Enemy, encounter: Encounter) -> None:
        """Single place rewards happen: XP, then a loot drop, then the
        EnemyDefeated event that quests listen to."""
        self.kills += 1
        gained = self.player.gain_xp(enemy.xp_reward)
        coins = f", +{enemy.coins} {CURRENCY_NAME}" if enemy.coins and self.campaign.wallet.earn(enemy.coins).ok else ""
        self.log(f"{enemy.name} defeated! +{enemy.xp_reward} XP{coins}")
        if gained.levels_gained:
            self.log(f"Level up! You are now level {gained.new_level}")
        if enemy.loot_table_id:
            drops = get_loot_table(enemy.loot_table_id).roll(self.rng)
            if self.ground.spawn(enemy.position, drops, get_item):
                self.log(f"{enemy.name} dropped loot (G to pick up)")
        self.bus.publish(EnemyDefeated(enemy.entity_id, enemy.archetype, encounter.spec.encounter_id, self.location_id))
