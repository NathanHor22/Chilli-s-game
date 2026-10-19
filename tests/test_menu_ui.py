"""Title menu text, selection feedback and projected click targets."""

import os
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest
from unittest.mock import patch

import pygame

from chilli.menu_ui import MENU_ACTIONS, MENU_BUTTON_RECTS, MenuScreen
from chilli.render import CREAM, RED, Renderer
from chilli.setup_ui import canvas_position


class MenuScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((1280, 720))
        cls.renderer = Renderer()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.menu = MenuScreen(self.renderer)

    def test_menu_has_exact_title_and_only_three_large_buttons(self):
        with patch.object(self.renderer, "text", wraps=self.renderer.text) as text:
            canvas = self.menu.draw()
        self.assertEqual([call.args[0] for call in text.call_args_list],
                         ["How HOT are you", "Start", "Settings", "Quit"])
        self.assertEqual(MENU_ACTIONS, ("start", "settings", "quit"))
        self.assertEqual(len(self.menu.actions), 3)
        self.assertEqual(canvas.get_size(), (1280, 720))
        self.assertEqual(canvas.get_at((20, 20))[:3], CREAM)
        for rect, _ in self.menu.actions:
            self.assertGreaterEqual(rect.width, 400)
            self.assertGreaterEqual(rect.height, 64)
            self.assertTrue(canvas.get_rect().contains(rect))

    def test_clicks_select_each_action_and_ignore_empty_space(self):
        self.menu.draw()
        for rect, action in self.menu.actions:
            with self.subTest(action=action):
                self.assertEqual(self.menu.click(rect.center), action)
                self.assertIsNone(self.menu.click((rect.right, rect.centery)))
        for point in (None, (640, 176), (640, 407), (640, 505), (30, 30)):
            self.assertIsNone(self.menu.click(point))

    def test_selected_button_is_red_and_keyboard_selection_moves(self):
        boxes = [pygame.Rect(rect) for rect in MENU_BUTTON_RECTS]
        for selected in range(3):
            canvas = self.menu.draw(selected=selected)
            for index, box in enumerate(boxes):
                color = canvas.get_at((box.left + 30, box.top + 30))[:3]
                if index == selected:
                    self.assertEqual(color, RED)
                else:
                    self.assertNotEqual(color, RED)

    def test_hover_feedback_keeps_keyboard_choice_visible(self):
        start, settings, _ = [pygame.Rect(rect) for rect in MENU_BUTTON_RECTS]
        canvas = self.menu.draw(selected=0, mouse_pos=settings.center)
        self.assertEqual(canvas.get_at((start.left + 30, start.top + 30))[:3], RED)
        hovered = canvas.get_at((settings.left + 30, settings.top + 30))[:3]
        canvas = self.menu.draw(selected=0, mouse_pos=None)
        self.assertNotEqual(canvas.get_at((settings.left + 30, settings.top + 30))[:3], hovered)

    def test_letterboxed_mouse_positions_keep_correct_menu_actions(self):
        self.menu.draw()
        for size in ((640, 360), (1600, 1000), (1920, 720)):
            width, height = size
            factor = min(width / 1280, height / 720)
            ox, oy = (width - 1280 * factor) / 2, (height - 720 * factor) / 2
            for rect, action in self.menu.actions:
                with self.subTest(size=size, action=action):
                    point = (ox + rect.centerx * factor, oy + rect.centery * factor)
                    self.assertEqual(self.menu.click(canvas_position(point, size)), action)


if __name__ == "__main__":
    unittest.main()
