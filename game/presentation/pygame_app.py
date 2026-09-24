"""Pygame front-end: keyboard/mouse -> PlayerInput, GameSession -> shapes.

This is the only module that imports Pygame. It holds no game rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pygame

from game.core.entity import Entity
from game.core.vector import Vec2
from game.ai.states import AIState
from game.encounters.catalog import ENCOUNTERS
from game.encounters.encounter import EncounterStatus
from game.entities.enemy import Enemy
from game.magic.casting import check_spell_requirements
from game.persistence.save_manager import SaveManager
from game.session import Arena, GameSession, PlayerInput, outcome_text

WIDTH, HEIGHT = 800, 600
FPS = 60

WHITE = (235, 235, 235)
GREY = (120, 120, 120)
RED = (200, 50, 50)
ORANGE = (240, 150, 40)
GREEN = (60, 190, 90)
BLUE = (50, 100, 255)
LIGHT_BLUE = (140, 180, 255)
CYAN = (60, 190, 220)
YELLOW = (230, 200, 60)
BLACK = (20, 20, 20)
DARK_RED = (90, 25, 25)

PURPLE = (170, 90, 220)
BROWN = (150, 80, 40)
ENEMY_COLOURS = {"goblin": RED, "striker": RED, "archer": PURPLE, "brute": BROWN}
# Small debug tags drawn above enemies.
STATE_TAGS = {
    AIState.ALERT: "!",
    AIState.TELEGRAPH: "TELEGRAPH",
    AIState.RECOVER: "OPEN",
    AIState.STAGGERED: "STAGGER",
    AIState.RETREAT: "retreat",
}

DEMO_ENCOUNTER_ID = "mixed_skirmish"
ENCOUNTER_ORDER = tuple(ENCOUNTERS)


def next_encounter_id(current: str) -> str:
    index = ENCOUNTER_ORDER.index(current) if current in ENCOUNTER_ORDER else -1
    return ENCOUNTER_ORDER[(index + 1) % len(ENCOUNTER_ORDER)]


SPELL_KEYS = {getattr(pygame, f"K_{n}"): n - 1 for n in range(1, 10)}


class InputState:
    """Collects one-shot presses from events between frames."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.parry = False
        self.dodge = False
        self.cycle_weapon = False
        self.select_spell: Optional[int] = None

    def handle_keydown(self, key: int) -> None:
        if key == pygame.K_q:
            self.parry = True
        elif key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
            self.dodge = True
        elif key == pygame.K_TAB:
            self.cycle_weapon = True
        elif key in SPELL_KEYS:
            self.select_spell = SPELL_KEYS[key]

    def build(self) -> PlayerInput:
        keys = pygame.key.get_pressed()
        mouse = pygame.mouse.get_pressed()
        controls = PlayerInput(
            move=Vec2(
                float(keys[pygame.K_d]) - float(keys[pygame.K_a]),
                float(keys[pygame.K_s]) - float(keys[pygame.K_w]),
            ),
            melee=bool(keys[pygame.K_SPACE] or mouse[0]),
            magic=bool(keys[pygame.K_e]),
            block=bool(keys[pygame.K_f] or mouse[2]),
            parry=self.parry,
            dodge=self.dodge,
            cycle_weapon=self.cycle_weapon,
            select_spell=self.select_spell,
        )
        self.reset()
        return controls


def entity_rect(entity: Entity) -> pygame.Rect:
    rect = pygame.Rect(0, 0, int(entity.size), int(entity.size))
    rect.center = (int(entity.position.x), int(entity.position.y))
    return rect


def draw_bar(screen: pygame.Surface, x: int, y: int, w: int, h: int, fraction: float, colour) -> None:
    pygame.draw.rect(screen, DARK_RED, (x, y, w, h))
    pygame.draw.rect(screen, colour, (x, y, int(w * max(0.0, min(1.0, fraction))), h))


def defense_label(session: GameSession) -> str:
    d = session.player.defense
    if d.is_dodging:
        state = "DODGING"
    elif d.is_parrying:
        state = "PARRY WINDOW"
    elif d.blocking:
        state = "BLOCKING"
    else:
        state = "-"
    cooldowns = []
    if d.dodge_cooldown > 0:
        cooldowns.append(f"dodge {d.dodge_cooldown:.1f}s")
    if d.parry_cooldown > 0:
        cooldowns.append(f"parry {d.parry_cooldown:.1f}s")
    return f"Defense: {state}" + (f"  ({', '.join(cooldowns)})" if cooldowns else "")


def hud_lines(session: GameSession) -> List[Tuple[str, Tuple[int, int, int]]]:
    player = session.player
    s = player.stats
    weapon = player.weapon
    guard = player.guard_profile()
    weapon_text = (
        f"Weapon: {weapon.name} ({weapon.weapon_type.value})" if weapon else "Weapon: unarmed"
    ) + f"  block {'yes' if guard.can_block else 'no'} / parry {'yes' if guard.can_parry else 'no'}"
    lines = [
        (f"{player.name}  Lv {player.level}  XP {player.xp}/{player.xp_to_next}", WHITE),
        (f"HP {s.health:.0f}/{s.max_health:.0f}", GREEN),
        (f"MP {s.mana:.0f}/{s.max_mana:.0f}   magic power {s.magic_power:.0f}", CYAN),
        (f"ST {s.stamina:.0f}/{s.max_stamina:.0f}", YELLOW),
        (weapon_text, WHITE),
    ]
    spell = player.spellbook.selected
    if spell is not None:
        index = player.spellbook.spells.index(spell) + 1
        problem = check_spell_requirements(player, spell)
        cooldown = player.spellbook.cooldown_for(spell).remaining
        status = outcome_text(problem) if problem else (f"cooldown {cooldown:.1f}s" if cooldown else "ready")
        lines.append((f"Spell [{index}] {spell.name}  {spell.rank.value}-rank {spell.element.label}  {status}", LIGHT_BLUE))
    lines.append((defense_label(session), WHITE))
    world = session.world
    lines.append((f"Day {world.day}  time {world.time_of_day * 24:05.2f}h  kills {session.kills}", GREY))
    return lines


def encounter_lines(session: GameSession) -> List[Tuple[str, Tuple[int, int, int]]]:
    encounter = session.encounter
    status_colour = {
        EncounterStatus.ACTIVE: WHITE,
        EncounterStatus.CLEARED: GREEN,
        EncounterStatus.FAILED: RED,
    }.get(encounter.status, GREY)
    lines = [
        (encounter.spec.name, WHITE),
        (f"{encounter.status.value.upper()}  {encounter.elapsed:.1f}s", status_colour),
    ]
    for enemy in encounter.enemies:
        if not enemy.is_alive:
            lines.append((f"{enemy.name}: dead", GREY))
            continue
        hp = f"{enemy.stats.health:.0f}/{enemy.stats.max_health:.0f}"
        state = enemy.state.value
        if enemy.state is AIState.TELEGRAPH:
            state += f" {enemy.windup_remaining:.2f}s"
        elif enemy.state is AIState.RECOVER:
            state += f" {enemy.lifecycle.remaining:.1f}s"
        elif enemy.state is AIState.STAGGERED:
            state += f" {enemy.stagger_remaining:.1f}s"
        lines.append((f"{enemy.name} [{enemy.archetype}] HP {hp}  {state}", ENEMY_COLOURS.get(enemy.archetype, RED)))
    return lines


def enemy_colour(enemy: Enemy) -> Tuple[int, int, int]:
    state = enemy.state
    if state is AIState.TELEGRAPH:
        return ORANGE
    if state is AIState.STAGGERED:
        return YELLOW
    if state is AIState.RECOVER:
        return GREY
    return ENEMY_COLOURS.get(enemy.archetype, RED)


def draw_enemy(screen: pygame.Surface, small: pygame.font.Font, enemy: Enemy, player: Entity) -> None:
    if not enemy.is_alive:
        return
    rect = entity_rect(enemy)
    colour = enemy_colour(enemy)
    centre = (int(enemy.position.x), int(enemy.position.y))
    if enemy.attack_profile.is_melee:
        pygame.draw.rect(screen, colour, rect)
    else:
        pygame.draw.circle(screen, colour, centre, int(enemy.size / 2))

    if enemy.state is AIState.TELEGRAPH:
        # Where the attack will land: reach ring (melee) or aim line (ranged).
        if enemy.attack_profile.is_melee:
            origin = enemy.aim_point or enemy.position
            radius = int(enemy.attack.reach + (enemy.size / 2 if enemy.aim_point else 0))
            pygame.draw.circle(screen, ORANGE, (int(origin.x), int(origin.y)), radius, 1)
        else:
            pygame.draw.line(screen, ORANGE, centre, (int(player.position.x), int(player.position.y)), 1)
        # Wind-up bar fills up as release approaches.
        draw_bar(screen, rect.x, rect.bottom + 4, rect.width, 4, enemy.telegraph_progress, ORANGE)

    draw_bar(screen, rect.x, rect.y - 8, rect.width, 5, enemy.stats.health / enemy.stats.max_health, GREEN)
    tag = STATE_TAGS.get(enemy.state)
    if tag:
        label = small.render(tag, True, colour if enemy.state is not AIState.RECOVER else WHITE)
        screen.blit(label, label.get_rect(midbottom=(rect.centerx, rect.y - 10)))


def draw(screen: pygame.Surface, font: pygame.font.Font, session: GameSession, small: Optional[pygame.font.Font] = None) -> None:
    small = small or font
    screen.fill(BLACK)
    player = session.player

    for enemy in session.enemies:
        draw_enemy(screen, small, enemy, player)
    for projectile in session.encounter.projectiles.projectiles:
        pygame.draw.circle(screen, WHITE, (int(projectile.position.x), int(projectile.position.y)), 4)

    rect = entity_rect(player)
    defense = player.defense
    if not player.is_alive:
        colour = GREY
    elif defense.is_dodging:
        colour = LIGHT_BLUE
    else:
        colour = BLUE
    pygame.draw.rect(screen, colour, rect)
    if player.is_alive and defense.is_parrying:
        pygame.draw.rect(screen, WHITE, rect.inflate(10, 10), 3)
    elif player.is_alive and defense.blocking:
        pygame.draw.rect(screen, YELLOW, rect.inflate(8, 8), 3)

    for i, (text, colour) in enumerate(hud_lines(session)):
        screen.blit(font.render(text, True, colour), (10, 10 + i * 20))
    for i, (text, colour) in enumerate(encounter_lines(session)):
        surface = small.render(text, True, colour)
        screen.blit(surface, (WIDTH - surface.get_width() - 10, 10 + i * 17))

    for i, text in enumerate(reversed(session.messages)):
        screen.blit(font.render(text, True, GREY), (10, HEIGHT - 66 - i * 18))

    help_lines = (
        "WASD move  SPACE/LMB attack  1-9 pick spell  E cast  TAB weapon  N next encounter",
        "F/RMB hold block  Q parry  SHIFT dodge  F5 save  F9 load  R restart  ESC quit",
    )
    for i, text in enumerate(help_lines):
        screen.blit(font.render(text, True, GREY), (10, HEIGHT - 42 + i * 18))

    banner = None
    if not player.is_alive:
        banner = ("YOU DIED - encounter failed. R to restart", RED)
    elif session.encounter.status is EncounterStatus.CLEARED and not session.encounter.spec.repeat_on_clear:
        banner = ("ENCOUNTER CLEARED - R to restart, N for next", GREEN)
    if banner:
        big = font.render(banner[0], True, banner[1])
        screen.blit(big, big.get_rect(center=(WIDTH // 2, HEIGHT // 2)))


def run(save_path: Path, max_frames: Optional[int] = None) -> None:
    """Run the demo. ``max_frames`` lets smoke tests exit automatically."""
    # Only the subsystems we use; skipping audio saves memory on small machines.
    pygame.display.init()
    pygame.font.init()
    try:
        screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Magical Conquest Prototype")
        clock = pygame.time.Clock()
        font = pygame.font.SysFont(None, 22)
        small = pygame.font.SysFont(None, 18)
        arena = Arena(WIDTH, HEIGHT)
        saves = SaveManager(save_path)
        encounter_id = DEMO_ENCOUNTER_ID
        session = GameSession.new(arena=arena, encounter_id=encounter_id)
        inputs = InputState()

        frames = 0
        running = True
        while running:
            dt = min(clock.tick(FPS) / 1000.0, 0.1)  # cap dt after stalls
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        session = GameSession.new(arena=arena, encounter_id=encounter_id)
                    elif event.key == pygame.K_n:
                        encounter_id = next_encounter_id(encounter_id)
                        session = GameSession.new(arena=arena, encounter_id=encounter_id)
                        session.log(f"Encounter: {session.encounter.spec.name}")
                    elif event.key == pygame.K_F5:
                        if session.player.is_alive:
                            saves.save(session.player, session.world)
                            session.log(f"Saved to {saves.path.name}")
                        else:
                            session.log("Cannot save while dead")
                    elif event.key == pygame.K_F9:
                        result = saves.load()
                        if result.ok:
                            session = GameSession(
                                player=result.player, world=result.world, arena=arena, encounter_id=encounter_id
                            )
                            session.log("Save loaded")
                        else:
                            session.log(f"Load failed ({result.status.value})")
                    else:
                        inputs.handle_keydown(event.key)

            session.update(dt, inputs.build())
            draw(screen, font, session, small)
            pygame.display.flip()

            frames += 1
            if max_frames is not None and frames >= max_frames:
                running = False
    finally:
        pygame.quit()
