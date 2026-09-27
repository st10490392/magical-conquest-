"""Dialogue overlay and quest tracker for the Pygame prototype.

Presentation only: the conversation, its options and all effects come from
``game.dialogue`` via the session.
"""

from __future__ import annotations

import textwrap
from typing import List, Tuple

import pygame

from game.quests.model import QuestStatus
from game.session import GameSession

PANEL_BG = (28, 32, 30)
WHITE = (235, 235, 235)
GREY = (140, 140, 140)
GOLD = (230, 200, 90)
GREEN = (90, 200, 110)

NUMBER_KEYS = {getattr(pygame, f"K_{n}"): n - 1 for n in range(1, 10)}


def handle_dialogue_key(key: int, session: GameSession) -> None:
    conversation = session.conversation
    if conversation is None:
        return
    if key in (pygame.K_ESCAPE, pygame.K_g) or conversation.ended:
        session.end_conversation()
    elif key in NUMBER_KEYS:
        session.choose_dialogue(NUMBER_KEYS[key])


def draw_dialogue(screen: pygame.Surface, font: pygame.font.Font, small: pygame.font.Font, session: GameSession) -> None:
    conversation = session.conversation
    if conversation is None:
        return
    rect = pygame.Rect(60, screen.get_height() - 250, screen.get_width() - 120, 170)
    pygame.draw.rect(screen, PANEL_BG, rect)
    pygame.draw.rect(screen, GOLD, rect, 1)
    screen.blit(font.render(conversation.speaker, True, GOLD), (rect.x + 10, rect.y + 8))
    y = rect.y + 32
    for line in textwrap.wrap(conversation.node.text, 80)[:3]:
        screen.blit(small.render(line, True, WHITE), (rect.x + 10, y))
        y += 18
    y += 6
    if conversation.ended:
        screen.blit(small.render("(press any key to close)", True, GREY), (rect.x + 10, y))
        return
    for index, option in enumerate(conversation.options()[:5]):
        screen.blit(small.render(f"{index + 1}. {option.text}", True, GREEN), (rect.x + 16, y))
        y += 18
    screen.blit(small.render("1-9 choose   Esc/G leave   (game paused)", True, GREY), (rect.x + 10, rect.bottom - 20))


def tracker_lines(session: GameSession) -> List[Tuple[str, Tuple[int, int, int]]]:
    """Active quests with objective progress (the objective tracker)."""
    quests = session.campaign.quests
    count = session.player.inventory.count
    lines = []
    for quest_id in quests.active():
        definition = quests.definitions[quest_id]
        ready = quests.status(quest_id, count) is QuestStatus.READY_TO_TURN_IN
        lines.append((f"{definition.title}{' - return to turn in' if ready else ''}", GOLD))
        for objective in definition.objectives:
            done, required = quests.objective_progress(quest_id, objective.objective_id, count)
            colour = GREEN if done >= required else WHITE
            lines.append((f"  {objective.description or objective.target}: {done}/{required}", colour))
    return lines
