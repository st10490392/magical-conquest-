"""Merchant / blacksmith overlay for the Pygame prototype (presentation only).

Tabs: Buy, Sell and (for blacksmiths) Inspect. Left/Right switch tabs,
Up/Down select, Enter buys or sells one, Esc closes. All rules live in
``game.economy`` via the session.
"""

from __future__ import annotations

from typing import List, Tuple

import pygame

from game.economy.merchant import ServiceType
from game.economy.wallet import CURRENCY_NAME
from game.play import PlaySession

PANEL_BG = (34, 30, 26)
WHITE = (235, 235, 235)
GREY = (140, 140, 140)
GOLD = (230, 200, 90)
HIGHLIGHT = (90, 70, 40)


class ShopPanel:
    def __init__(self) -> None:
        self.tab = 0
        self.cursor = 0

    @staticmethod
    def tabs(session: PlaySession) -> List[str]:
        merchant = session.merchant()
        return ["Buy", "Sell"] + (["Inspect"] if merchant.has_service(ServiceType.INSPECT) else [])

    def rows(self, session: PlaySession) -> List[Tuple[str, str, str]]:
        """(item_id, label, right column) for the current tab."""
        merchant = session.merchant()
        tab = self.tabs(session)[self.tab]
        if tab == "Buy":
            return [(o.item.item_id, o.item.name + ("" if o.available is None else f" ({o.available} left)"),
                     f"{o.price} {CURRENCY_NAME}") for o in merchant.offers()]
        if tab == "Sell":
            rows = []
            for item, qty in session.player.inventory.stacks:
                price = merchant.sell_price(item)
                rows.append((item.item_id, f"{item.name} x{qty}", f"{price} {CURRENCY_NAME}" if price else "won't buy"))
            return rows
        rows = []
        for report in session.inspect_gear():
            rows.append(("", f"[{report.slot}] {report.name} ({report.rarity})", f"worth {report.sell_price}"))
            rows.append(("", "    " + report.details[:68], ""))
        return rows

    def handle_key(self, key: int, session: PlaySession) -> None:
        tabs = self.tabs(session)
        if key == pygame.K_ESCAPE:
            session.close_shop()
            self.tab = self.cursor = 0
            return
        if key == pygame.K_LEFT:
            self.tab, self.cursor = (self.tab - 1) % len(tabs), 0
        elif key == pygame.K_RIGHT:
            self.tab, self.cursor = (self.tab + 1) % len(tabs), 0
        elif key == pygame.K_UP:
            self.cursor = max(0, self.cursor - 1)
        elif key == pygame.K_DOWN:
            self.cursor += 1
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            rows = self.rows(session)
            if rows and rows[min(self.cursor, len(rows) - 1)][0]:
                item_id = rows[min(self.cursor, len(rows) - 1)][0]
                if tabs[self.tab] == "Buy":
                    session.buy(item_id)
                elif tabs[self.tab] == "Sell":
                    session.sell(item_id)
        self.cursor = max(0, min(self.cursor, len(self.rows(session)) - 1))

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, small: pygame.font.Font, session: PlaySession) -> None:
        width, height = 500, 400
        rect = pygame.Rect((screen.get_width() - width) // 2, 80, width, height)
        pygame.draw.rect(screen, PANEL_BG, rect)
        pygame.draw.rect(screen, GOLD, rect, 1)
        merchant = session.merchant()
        header = f"{merchant.definition.name}   You have {session.coins} {CURRENCY_NAME}   (game paused)"
        screen.blit(font.render(header, True, GOLD), (rect.x + 10, rect.y + 8))
        tabs = self.tabs(session)
        x = rect.x + 10
        for index, name in enumerate(tabs):
            label = small.render(f"[{name}]" if index == self.tab else name, True, WHITE if index == self.tab else GREY)
            screen.blit(label, (x, rect.y + 34))
            x += label.get_width() + 16
        y = rect.y + 58
        for index, (_, left, right) in enumerate(self.rows(session)[:15]):
            if index == self.cursor:
                pygame.draw.rect(screen, HIGHLIGHT, (rect.x + 4, y - 1, width - 8, 19))
            screen.blit(small.render(left, True, WHITE), (rect.x + 10, y))
            right_surface = small.render(right, True, GOLD)
            screen.blit(right_surface, (rect.right - right_surface.get_width() - 10, y))
            y += 20
        hint = "Left/Right tab  Up/Down select  Enter buy/sell one  Esc leave"
        if tabs[self.tab] == "Inspect":
            hint = "The smith looks over your equipped gear. (Upgrades: not available yet)"
        screen.blit(small.render(hint, True, GREY), (rect.x + 10, rect.bottom - 22))
