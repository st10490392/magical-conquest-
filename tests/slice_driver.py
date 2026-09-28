"""A scripted 'player' for headless end-to-end tests.

It only uses what a human has: ``PlayerInput`` (move, attack, parry, G),
dialogue choices, shop buy/sell and inventory actions through the session.
It never edits game state directly.
"""

from __future__ import annotations

from game.ai.states import AIState
from game.core.vector import Vec2
from game.npcs.catalog import get_npc
from game.session import PlayerInput

DT = 1 / 60


class StuckError(AssertionError):
    pass


class SliceDriver:
    def __init__(self, session, max_seconds: float = 600.0) -> None:
        self.session = session
        self.budget = round(max_seconds / DT)

    # ---------------------------------------------------------------- basics
    def tick(self, controls: PlayerInput = PlayerInput()) -> None:
        self.budget -= 1
        if self.budget <= 0:
            raise StuckError("scripted player ran out of time")
        self.session.update(DT, controls)

    def threats(self):
        return [e for e in self.session.enemies if e.is_alive and e.engaged]

    def combat_input(self) -> PlayerInput:
        """Fight the nearest engaged enemy: parry melee strikes just before
        they land, otherwise close in and attack."""
        session, player = self.session, self.session.player
        target = min(self.threats(), key=lambda e: e.distance_to(player))
        danger = next((e for e in self.threats() if e.state is AIState.TELEGRAPH
                       and e.attack_profile.is_melee and e.windup_remaining < 0.1), None)
        if danger is not None and player.defense.parry_cooldown <= 0:
            return PlayerInput(parry=True)
        if player.stats.health < player.stats.max_health * 0.35 and player.inventory.has("minor_health_potion"):
            session.use_or_equip("minor_health_potion")
        distance = player.distance_to(target)
        return PlayerInput(move=(target.position - player.position) if distance > 60 else Vec2(),
                           melee=distance <= 75)

    def walk_to(self, point: Vec2, radius: float = 30.0) -> None:
        """Walk to ``point`` in the current zone, fighting anything that engages."""
        while self.session.player.position.distance_to(point) > radius:
            if self.threats():
                self.tick(self.combat_input())
            else:
                self.tick(PlayerInput(move=point - self.session.player.position))

    def clear_threats(self) -> None:
        while self.threats():
            self.tick(self.combat_input())

    def travel_via(self, exit_id: str) -> None:
        """Walk into an exit (fighting on the way) until the zone changes."""
        start = self.session.zone.zone_id
        area = self.session.zone_definition.exit(exit_id).area
        while self.session.zone.zone_id == start:
            if self.threats():
                self.tick(self.combat_input())
            else:
                self.tick(PlayerInput(move=area.centre - self.session.player.position))

    # ------------------------------------------------------------ interaction
    def talk(self, npc_id: str) -> None:
        npc = get_npc(npc_id)
        self.walk_to(npc.position + Vec2(35, 0), radius=15)
        self.tick(PlayerInput(interact=True))
        if self.session.conversation is None or self.session.talking_to.npc_id != npc_id:
            raise StuckError(f"could not start talking to {npc_id}")

    def choose(self, text_start: str):
        """Pick the visible reply whose text starts with ``text_start``."""
        options = self.session.conversation.options()
        for index, option in enumerate(options):
            if option.text.startswith(text_start):
                return self.session.choose_dialogue(index)
        raise StuckError(f"no reply starting with {text_start!r} in {[o.text for o in options]}")

    def leave_conversation(self) -> None:
        self.session.end_conversation()

    def loot_everything(self) -> None:
        while self.session.ground.drops:
            drop = self.session.ground.drops[0]
            self.walk_to(drop.position, radius=20)
            before = len(self.session.ground.drops)
            self.tick(PlayerInput(interact=True))
            if len(self.session.ground.drops) == before and self.session.ground.drops[0] is drop:
                raise StuckError("could not pick up loot (inventory full?)")
