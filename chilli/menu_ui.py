"""A small title menu drawn on the game's existing 1280 x 720 canvas."""
from __future__ import annotations

import pygame

from .render import CREAM, INK, RED


MENU_ACTIONS = ("start", "settings", "quit")
MENU_LABELS = ("Start", "Settings", "Quit")
MENU_BUTTON_RECTS = ((390, 320, 500, 76), (390, 418, 500, 76), (390, 516, 500, 76))


class MenuScreen:
    def __init__(self, renderer):
        self.renderer = renderer
        self.actions = tuple((pygame.Rect(rect), action)
                             for rect, action in zip(MENU_BUTTON_RECTS, MENU_ACTIONS))

    def click(self, point):
        if point is not None:
            for rect, action in self.actions:
                if rect.collidepoint(point):
                    return action
        return None

    def draw(self, selected=0, mouse_pos=None):
        r, surface = self.renderer, self.renderer.canvas
        surface.fill(CREAM)
        r.text("How HOT are you", (640, 176), 76, RED, True, "center")
        pygame.draw.line(surface, (230, 188, 154), (600, 246), (680, 246), 3)
        selected = int(selected) % len(MENU_ACTIONS)
        for index, ((rect, _), label) in enumerate(zip(self.actions, MENU_LABELS)):
            active = index == selected
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            fill = RED if active else (255, 231, 211) if hovered else (255, 251, 243)
            pygame.draw.rect(surface, fill, rect, border_radius=20)
            if not active:
                pygame.draw.rect(surface, RED if hovered else (229, 205, 177), rect, 2, border_radius=20)
            r.text(label, rect.center, 33, CREAM if active else INK, True, "center")
        return surface
