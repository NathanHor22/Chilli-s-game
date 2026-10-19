"""Player-facing rendering contract, using SDL's headless display."""

import os
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pygame

from chilli.render import CREAM, DEMO_START_RECT, Renderer


def scene(state="playing", *, heat=.4, player_visible=True):
    return SimpleNamespace(state=state, heat=heat, remaining=5.3, countdown=3,
                           sway=.4, player_visible=player_visible,
                           config=SimpleNamespace(round_seconds=10.0))


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((1280, 720))
        cls.renderer = Renderer()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def drawn_text(self, game, **kwargs):
        with patch.object(self.renderer, "text", wraps=self.renderer.text) as text:
            self.renderer.draw(game, 2.0, **kwargs)
        return [str(call.args[0]) for call in text.call_args_list]

    def test_playing_shows_only_timer_and_one_encouragement_even_in_demo(self):
        for demo in (False, True):
            with self.subTest(demo=demo):
                self.assertEqual(self.drawn_text(scene(), demo=demo), ["06s", "Keep going!"])

    def test_encouragement_progresses_with_growth(self):
        for heat, expected in ((0., "Sway left and right"), (.25, "Keep going!"),
                               (.5, "Getting hotter!"), (.8, "Almost there!"), (1., "Almost there!")):
            with self.subTest(heat=heat):
                self.assertEqual(self.drawn_text(scene(heat=heat))[-1], expected)

    def test_missing_player_overrides_growth_encouragement(self):
        for heat in (0., .4, .9):
            with self.subTest(heat=heat):
                self.assertEqual(self.drawn_text(scene(heat=heat, player_visible=False))[-1], "Step back into view")

    def test_how_to_screen_teaches_camera_and_keyboard_paths_without_skip_prompt(self):
        for demo in (False, True):
            with self.subTest(demo=demo):
                texts = self.drawn_text(scene("instructions"), demo=demo)
                self.assertIn("Sway left. Sway right.", texts)
                self.assertIn("Grow it to full size in 10 seconds.", texts)
                self.assertIn("ALTERNATE LEFT / RIGHT" if demo else "SWAY SIDE TO SIDE", texts)
                self.assertIn("Your turn in a moment", texts)
                self.assertFalse(any("Enter" in value or "Space" in value for value in texts))

    def test_demonstrator_visibly_animates_between_lean_poses(self):
        self.renderer.draw(scene("instructions"), 0.)
        neutral = pygame.image.tobytes(self.renderer.canvas.subsurface((228, 168, 320, 320)), "RGB")
        self.renderer.draw(scene("instructions"), .85)
        leaning = pygame.image.tobytes(self.renderer.canvas.subsurface((228, 168, 320, 320)), "RGB")
        self.assertNotEqual(neutral, leaning)

    def test_tutorial_chilli_keeps_growing_when_demonstrator_changes_direction(self):
        with patch.object(self.renderer, "_hero", wraps=self.renderer._hero) as hero:
            self.renderer.draw(scene("instructions"), .3)
            first_size = hero.call_args.args[0]
            self.renderer.draw(scene("instructions"), 1.9)
            later_size = hero.call_args.args[0]
        self.assertGreater(later_size, first_size)

    def test_demo_click_target_matches_rendered_prompt_and_never_skips_instructions(self):
        box = pygame.Rect(DEMO_START_RECT)
        with patch("chilli.render.pygame.draw.rect", wraps=pygame.draw.rect) as draw_rect:
            self.renderer._start_prompt("Press Enter or Space to start")
        actual_box = pygame.Rect(draw_rect.call_args.args[2])
        self.assertEqual(actual_box, box)
        for state in ("idle", "won", "timeout", "clear"):
            self.assertTrue(self.renderer.demo_start_hit(box.center, state))
        for state in ("instructions", "countdown", "playing", "error"):
            self.assertFalse(self.renderer.demo_start_hit(box.center, state))
        self.assertFalse(self.renderer.demo_start_hit(None, "idle"))
        self.assertFalse(self.renderer.demo_start_hit((box.right+1, box.centery), "idle"))

    def test_maximum_chilli_stays_above_encouragement_and_on_canvas(self):
        self.renderer.canvas.fill(CREAM)
        for angle in (-7.2, 0., 7.2):
            rect = self.renderer._hero(500, angle)
            self.assertGreaterEqual(rect.top, 0)
            self.assertLess(rect.bottom, 621)
            self.assertGreaterEqual(rect.left, 0)
            self.assertLessEqual(rect.right, 1280)


if __name__ == "__main__":
    unittest.main()
