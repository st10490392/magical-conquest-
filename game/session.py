"""Headless game session: ties player, enemies, combat and world together.

The Pygame layer converts keyboard state into a ``PlayerInput`` and draws the
session; everything else happens here, so the whole demo loop can be driven
by tests or a future server without a window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from game.core.combat import AttackOutcome, AttackResult
from game.core.vector import Vec2
from game.entities.enemy import Enemy, create_goblin
from game.entities.player import FIRE_BOLT, MELEE_STRIKE, Player
from game.world.world_state import WorldState

STAMINA_REGEN_PER_SECOND = 15.0
MANA_REGEN_PER_SECOND = 4.0
ENEMY_RESPAWN_SECONDS = 3.0


@dataclass(frozen=True)
class PlayerInput:
    move: Vec2 = Vec2()
    melee: bool = False
    magic: bool = False


@dataclass
class Arena:
    width: float = 800.0
    height: float = 600.0

    def clamp(self, position: Vec2, margin: float) -> Vec2:
        return position.clamped(margin, margin, self.width - margin, self.height - margin)


@dataclass
class GameSession:
    player: Player
    world: WorldState = field(default_factory=WorldState)
    arena: Arena = field(default_factory=Arena)
    enemy: Optional[Enemy] = None
    kills: int = 0
    messages: List[str] = field(default_factory=list)
    _respawn_timer: float = 0.0

    def __post_init__(self) -> None:
        if self.enemy is None:
            self.spawn_enemy()

    @classmethod
    def new(cls, player_name: str = "Hero", arena: Optional[Arena] = None) -> "GameSession":
        arena = arena or Arena()
        player = Player(player_name, position=Vec2(arena.width * 0.2, arena.height * 0.5))
        return cls(player=player, arena=arena)

    def spawn_enemy(self) -> Enemy:
        spawn = Vec2(self.arena.width * 0.75, self.arena.height * 0.5)
        if self.player.position.distance_to(spawn) < 200:
            spawn = Vec2(self.arena.width * 0.25, self.arena.height * 0.5)
        self.enemy = create_goblin(level=max(1, self.player.level), position=spawn)
        return self.enemy

    def log(self, text: str) -> None:
        self.messages.append(text)
        del self.messages[:-6]  # keep only the recent ones for the HUD

    def update(self, dt: float, controls: PlayerInput) -> None:
        self.world.tick(dt)
        player = self.player
        player.update(dt)

        if player.is_alive:
            player.move(controls.move, dt)
            player.position = self.arena.clamp(player.position, player.size / 2)
            player.stats.restore_stamina(STAMINA_REGEN_PER_SECOND * dt)
            player.stats.restore_mana(MANA_REGEN_PER_SECOND * dt)

        enemy = self.enemy
        if enemy is not None and enemy.is_alive:
            if controls.melee:
                self._player_attack(MELEE_STRIKE)
            elif controls.magic:
                self._player_attack(FIRE_BOLT)

        if enemy is not None and enemy.is_alive:
            result = enemy.update(dt, player, self.world.time)
            enemy.position = self.arena.clamp(enemy.position, enemy.size / 2)
            if result is not None and result.landed:
                self.log(f"{enemy.name} hits you for {result.damage:.1f}")
                if result.killed:
                    self.log("You died.")
        elif enemy is not None:
            enemy.update(dt, None)
            self._respawn_timer -= dt
            if self._respawn_timer <= 0 and player.is_alive:
                self.spawn_enemy()
                self.log(f"A level {self.enemy.level} {self.enemy.name} appears.")

    def _player_attack(self, attack) -> Optional[AttackResult]:
        enemy = self.enemy
        result = self.player.attack(enemy, attack, self.world.time)
        if result.landed:
            self.log(f"{attack.name} hits {enemy.name} for {result.damage:.1f}")
            if result.killed:
                self._on_enemy_killed(enemy)
        elif result.outcome in (AttackOutcome.NOT_ENOUGH_MANA, AttackOutcome.NOT_ENOUGH_STAMINA):
            self.log(result.outcome.value.replace("_", " "))
        return result

    def _on_enemy_killed(self, enemy: Enemy) -> None:
        self.kills += 1
        gained = self.player.gain_xp(enemy.xp_reward)
        self.log(f"{enemy.name} defeated! +{enemy.xp_reward} XP")
        if gained.levels_gained:
            self.log(f"Level up! You are now level {gained.new_level}")
        self._respawn_timer = ENEMY_RESPAWN_SECONDS
