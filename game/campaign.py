"""Campaign state: everything about the player's story that is saved.

``Campaign`` holds the quest log, NPC state, story flags and the reward
ledger. ``CampaignContext`` adapts it (plus the player) to the dialogue
protocol, so dialogue content can check quest status / items / flags and
trigger quest effects without knowing how those systems work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Mapping, Optional, Set

from game.dialogue.model import Condition, ConditionKind, Effect, EffectKind
from game.economy.catalog import MERCHANTS
from game.economy.merchant import Merchant, MerchantState
from game.economy.wallet import Wallet
from game.entities.player import Player
from game.items.catalog import ITEMS, get_item
from game.npcs.catalog import NPCS
from game.npcs.definitions import NpcRegistry
from game.progression.rewards import CurrencyAccount, RewardLedger
from game.quests.catalog import QUESTS, validate_quests
from game.quests.log import QuestActionStatus, QuestLog
from game.quests.model import QuestDefinition, QuestStatus
from game.quests.service import TurnInResult, TurnInStatus, turn_in
from game.world.exploration import Exploration, Location
from game.world.zone_catalog import WORLD

validate_quests(QUESTS, lambda i: i in ITEMS, lambda n: n in NPCS)

_FLAG_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_.:")


def _valid_flag(flag: object) -> bool:
    return isinstance(flag, str) and 0 < len(flag) <= 64 and set(flag) <= _FLAG_CHARS


@dataclass
class Campaign:
    quests: QuestLog = field(default_factory=lambda: QuestLog(QUESTS))
    npcs: NpcRegistry = field(default_factory=NpcRegistry)
    flags: Set[str] = field(default_factory=set)
    ledger: RewardLedger = field(default_factory=RewardLedger)
    exploration: Exploration = field(default_factory=Exploration)
    location: Optional[Location] = None  # None: start of the world
    wallet: Wallet = field(default_factory=Wallet)
    merchants: Dict[str, MerchantState] = field(default_factory=dict)  # only merchants traded with

    def merchant(self, merchant_id: str) -> Merchant:
        definition = MERCHANTS[merchant_id]
        state = self.merchants.setdefault(merchant_id, MerchantState.fresh(definition))
        return Merchant(definition, state, get_item)

    def set_flag(self, flag: str) -> None:
        if not _valid_flag(flag):
            raise ValueError(f"bad flag {flag!r}")
        self.flags.add(flag)

    def to_dict(self) -> dict:
        return {
            "quests": self.quests.to_dict(),
            "npcs": self.npcs.to_dict(),
            "flags": sorted(self.flags),
            "ledger": self.ledger.to_list(),
            "exploration": self.exploration.to_dict(),
            "location": self.location.to_dict() if self.location else None,
            "wallet": self.wallet.balance,
            "merchants": {mid: state.to_dict() for mid, state in sorted(self.merchants.items())},
        }

    @classmethod
    def from_dict(cls, data, quests: Mapping[str, QuestDefinition] = QUESTS) -> "Campaign":
        if not isinstance(data, dict):
            raise TypeError("campaign must be an object")
        flags = data["flags"]
        if not isinstance(flags, list) or not all(_valid_flag(f) for f in flags):
            raise ValueError("flags must be a list of valid flag names")
        campaign = cls(
            QuestLog.from_dict(data["quests"], quests),
            NpcRegistry.from_dict(data["npcs"], NPCS),
            set(flags),
            RewardLedger.from_list(data["ledger"]),
            Exploration.from_dict(data["exploration"], WORLD),
            None if data["location"] is None else Location.from_dict(data["location"], WORLD),
            Wallet(data["wallet"]),
            _merchants_from_dict(data["merchants"]),
        )
        # Quest completion and the reward ledger must agree, otherwise a save
        # could re-award a quest or lock a quest out forever.
        for quest_id, definition in quests.items():
            completed = campaign.quests.stored_status(quest_id) is QuestStatus.COMPLETED
            if completed != campaign.ledger.is_claimed(definition.reward_key):
                raise ValueError(f"{quest_id}: completion and reward ledger disagree")
        for key in campaign.ledger.claimed:
            kind, _, ident = key.partition(":")
            if kind == "quest" and ident not in quests:
                raise ValueError(f"ledger references unknown quest {key}")
            if kind == "discovery" and ident not in campaign.exploration.discovered:
                raise ValueError(f"discovery reward {key} claimed but not discovered")
            if kind == "encounter" and ident not in campaign.exploration.cleared:
                raise ValueError(f"encounter reward {key} claimed but the encounter is not cleared")
            if kind not in ("quest", "discovery", "encounter"):
                raise ValueError(f"unknown reward key {key!r}")
        return campaign


def _merchants_from_dict(data) -> Dict[str, MerchantState]:
    if not isinstance(data, dict):
        raise TypeError("merchants must be an object")
    states = {}
    for merchant_id, state in data.items():
        if merchant_id not in MERCHANTS:
            raise ValueError(f"unknown merchant {merchant_id!r}")
        states[merchant_id] = MerchantState.from_dict(state, MERCHANTS[merchant_id])
    return states


class CampaignContext:
    """Implements ``game.dialogue.conversation.DialogueContext``."""

    def __init__(
        self,
        player: Player,
        campaign: Campaign,
        npc_id: Optional[str] = None,
        wallet: Optional[CurrencyAccount] = None,
        on_item: Optional[Callable[[str, int], None]] = None,
        on_open_shop: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.player = player
        self.campaign = campaign
        self.npc_id = npc_id
        self.wallet = wallet if wallet is not None else campaign.wallet
        self.on_item = on_item
        self.on_open_shop = on_open_shop
        self.last_turn_in: Optional[TurnInResult] = None

    def quest_status(self, quest_id: str) -> QuestStatus:
        return self.campaign.quests.status(quest_id, self.player.inventory.count)

    # ------------------------------------------------------------ protocol
    def check(self, condition: Condition) -> bool:
        kind = condition.kind
        if kind is ConditionKind.QUEST_STATUS:
            wanted = set((condition.value or "").split("|"))
            return self.quest_status(condition.key).value in wanted
        if kind is ConditionKind.HAS_ITEM:
            return self.player.inventory.count(condition.key) >= int(condition.value or 1)
        if kind is ConditionKind.FLAG:
            return condition.key in self.campaign.flags
        if kind is ConditionKind.NOT_FLAG:
            return condition.key not in self.campaign.flags
        if kind is ConditionKind.MIN_LEVEL:
            return self.player.level >= int(condition.value or 1)
        raise ValueError(f"unhandled condition {kind}")

    def apply(self, effect: Effect) -> str:
        if effect.kind is EffectKind.ACCEPT_QUEST:
            status = self.campaign.quests.accept(effect.key)
            title = self.campaign.quests.definitions[effect.key].title
            return f"Quest accepted: {title}" if status is QuestActionStatus.OK else f"Cannot accept: {status.value}"
        if effect.kind is EffectKind.TURN_IN_QUEST:
            result = turn_in(effect.key, self.player, self.campaign.quests, self.campaign.ledger, get_item,
                             npc_id=self.npc_id, wallet=self.wallet, on_item=self.on_item)
            self.last_turn_in = result
            if result.ok:
                title = self.campaign.quests.definitions[effect.key].title
                return f"Quest complete: {title} (+{result.reward.xp} XP)"
            if result.status is TurnInStatus.INVENTORY_FULL:
                return "Your bags are full - make room to receive the reward."
            return f"Cannot turn in: {result.status.value}"
        if effect.kind is EffectKind.SET_FLAG:
            self.campaign.set_flag(effect.key)
            return ""
        if effect.kind is EffectKind.OPEN_SHOP:
            return self.on_open_shop(effect.key) if self.on_open_shop else ""
        raise ValueError(f"unhandled effect {effect.kind}")
