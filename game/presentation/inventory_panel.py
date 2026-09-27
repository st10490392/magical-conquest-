"""Inventory/equipment overlay for the Pygame prototype (presentation only).

Lists equipped slots first, then inventory stacks. Up/Down select, Enter
equips/uses (or unequips an equipped entry). All rules live in the session
and ``game.items``; this file only draws and forwards choices.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game.equipment.slots import EquipSlot, describe
from game.items.catalog import item_for
from game.items.definitions import ItemDefinition
from game.session import GameSession

PANEL_BG = (30, 30, 40)
WHITE = (235, 235, 235)
GREY = (140, 140, 140)
HIGHLIGHT = (60, 80, 140)
RARITY_COLOURS = {
    "common": (220, 220, 220),
    "uncommon": (90, 200, 110),
    "rare": (90, 150, 240),
    "epic": (190, 110, 230),
    "unique": (240, 190, 70),
}

Entry = Tuple[Optional[EquipSlot], ItemDefinition, int]  # (slot if equipped, item, qty)


class InventoryPanel:
    def __init__(self) -> None:
        self.open = False
        self.cursor = 0

    def toggle(self) -> None:
        self.open = not self.open
        self.cursor = 0

    @staticmethod
    def entries(session: GameSession) -> List[Entry]:
        player = session.player
        equipped = [(slot, item_for(item), 1) for slot, item in player.equipment.items().items()]
        carried = [(None, item, qty) for item, qty in player.inventory.stacks]
        return equipped + carried

    def handle_key(self, key: int, session: GameSession) -> None:
        entries = self.entries(session)
        if key == pygame.K_UP:
            self.cursor = max(0, self.cursor - 1)
        elif key == pygame.K_DOWN:
            self.cursor = min(len(entries) - 1, self.cursor + 1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER) and entries:
            slot, item, _ = entries[min(self.cursor, len(entries) - 1)]
            if slot is not None:
                session.unequip_slot(slot)
            else:
                session.use_or_equip(item.item_id)
        self.cursor = max(0, min(self.cursor, len(self.entries(session)) - 1))

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, small: pygame.font.Font, session: GameSession) -> None:
        width, height = 460, 440
        rect = pygame.Rect((screen.get_width() - width) // 2, 70, width, height)
        pygame.draw.rect(screen, PANEL_BG, rect)
        pygame.draw.rect(screen, GREY, rect, 1)
        player = session.player
        inventory = player.inventory
        title = f"Inventory {inventory.used_slots}/{inventory.capacity}   (game paused)"
        screen.blit(font.render(title, True, WHITE), (rect.x + 10, rect.y + 8))
        bonus = describe(player.equipment_bonuses)
        screen.blit(small.render(f"Gear bonuses: {bonus}", True, GREY), (rect.x + 10, rect.y + 30))
        entries = self.entries(session)
        y = rect.y + 52
        for index, (slot, item, qty) in enumerate(entries[:18]):
            if index == self.cursor:
                pygame.draw.rect(screen, HIGHLIGHT, (rect.x + 4, y - 1, width - 8, 19))
            prefix = f"[{slot.value}] " if slot is not None else ""
            amount = f" x{qty}" if qty > 1 else ""
            colour = RARITY_COLOURS.get(item.rarity.value, WHITE)
            screen.blit(small.render(f"{prefix}{item.name}{amount}", True, colour), (rect.x + 10, y))
            screen.blit(small.render(f"{item.category.value} / {item.rarity.value}", True, GREY), (rect.x + 290, y))
            y += 20
        if entries:
            _, item, _ = entries[min(self.cursor, len(entries) - 1)]
            details = item.description
            if item.armor is not None:
                details += "  " + describe(item.modifiers.as_dict())
            if item.weapon is not None:
                weapon = item.weapon
                details += f"  power {weapon.base_power:g}, reach {weapon.reach:g}"
            screen.blit(small.render(details[:70], True, WHITE), (rect.x + 10, rect.bottom - 44))
        hint = "Up/Down select  Enter equip/use/unequip  I close"
        screen.blit(small.render(hint, True, GREY), (rect.x + 10, rect.bottom - 22))
