"""Pygame front-end: keyboard -> PlayerInput, GameSession -> rectangles.

This is the only module that imports Pygame. It holds no game rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pygame

from game.core.entity import Entity
from game.core.vector import Vec2
from game.persistence.save_manager import SaveManager
from game.session import Arena, GameSession, PlayerInput

WIDTH, HEIGHT = 800, 600
FPS = 60

WHITE = (235, 235, 235)
GREY = (120, 120, 120)
RED = (200, 50, 50)
GREEN = (60, 190, 90)
BLUE = (50, 100, 255)
CYAN = (60, 190, 220)
YELLOW = (230, 200, 60)
BLACK = (20, 20, 20)
DARK_RED = (90, 25, 25)


def read_input() -> PlayerInput:
    keys = pygame.key.get_pressed()
    move = Vec2(
        float(keys[pygame.K_d]) - float(keys[pygame.K_a]),
        float(keys[pygame.K_s]) - float(keys[pygame.K_w]),
    )
    return PlayerInput(move=move, melee=bool(keys[pygame.K_SPACE]), magic=bool(keys[pygame.K_e]))


def entity_rect(entity: Entity) -> pygame.Rect:
    rect = pygame.Rect(0, 0, int(entity.size), int(entity.size))
    rect.center = (int(entity.position.x), int(entity.position.y))
    return rect


def draw_bar(screen: pygame.Surface, x: int, y: int, w: int, h: int, fraction: float, colour) -> None:
    pygame.draw.rect(screen, DARK_RED, (x, y, w, h))
    pygame.draw.rect(screen, colour, (x, y, int(w * max(0.0, min(1.0, fraction))), h))


def draw(screen: pygame.Surface, font: pygame.font.Font, session: GameSession) -> None:
    screen.fill(BLACK)
    player, enemy = session.player, session.enemy

    if enemy is not None and enemy.is_alive:
        rect = entity_rect(enemy)
        pygame.draw.rect(screen, RED, rect)
        draw_bar(screen, rect.x, rect.y - 8, rect.width, 5, enemy.stats.health / enemy.stats.max_health, GREEN)

    rect = entity_rect(player)
    pygame.draw.rect(screen, BLUE if player.is_alive else GREY, rect)

    s = player.stats
    lines = [
        (f"{player.name}  Lv {player.level}  XP {player.xp}/{player.xp_to_next}", WHITE),
        (f"HP {s.health:.0f}/{s.max_health:.0f}", GREEN),
        (f"MP {s.mana:.0f}/{s.max_mana:.0f}", CYAN),
        (f"ST {s.stamina:.0f}/{s.max_stamina:.0f}", YELLOW),
    ]
    if enemy is not None:
        es = enemy.stats
        lines.append((f"{enemy.name} Lv {enemy.level}  HP {es.health:.0f}/{es.max_health:.0f}", RED))
    world = session.world
    lines.append((f"Day {world.day}  time {world.time_of_day * 24:05.2f}h  kills {session.kills}", GREY))
    for i, (text, colour) in enumerate(lines):
        screen.blit(font.render(text, True, colour), (10, 10 + i * 20))

    for i, text in enumerate(reversed(session.messages)):
        screen.blit(font.render(text, True, GREY), (10, HEIGHT - 48 - i * 18))

    help_text = "WASD move  SPACE strike  E fire bolt  F5 save  F9 load  R restart  ESC quit"
    screen.blit(font.render(help_text, True, GREY), (WIDTH - font.size(help_text)[0] - 10, HEIGHT - 24))

    if not player.is_alive:
        big = font.render("YOU DIED - press R to restart", True, RED)
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
        arena = Arena(WIDTH, HEIGHT)
        saves = SaveManager(save_path)
        session = GameSession.new(arena=arena)

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
                        session = GameSession.new(arena=arena)
                    elif event.key == pygame.K_F5:
                        if session.player.is_alive:
                            saves.save(session.player, session.world)
                            session.log(f"Saved to {saves.path.name}")
                        else:
                            session.log("Cannot save while dead")
                    elif event.key == pygame.K_F9:
                        result = saves.load()
                        if result.ok:
                            session = GameSession(player=result.player, world=result.world, arena=arena)
                            session.log("Save loaded")
                        else:
                            session.log(f"Load failed ({result.status.value})")

            session.update(dt, read_input())
            draw(screen, font, session)
            pygame.display.flip()

            frames += 1
            if max_frames is not None and frames >= max_frames:
                running = False
    finally:
        pygame.quit()
