"""Player-facing rendering contract, using SDL's headless display."""

import os
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from types import SimpleNamespace
import math
import unittest
from unittest.mock import patch

import pygame

from chilli.balloon import PLAY_BOUNDS
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
        for heat, expected in ((0., "Bring the heat!"), (.25, "Keep going!"),
                               (.5, "Scorching moves!"), (.8, "Almost there!"), (1., "Almost there!")):
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
                self.assertIn("Sway or wave your hands", texts)
                self.assertIn("Grow it to full size in 10 seconds.", texts)
                self.assertIn("Arrows / A D: sway" if demo else "SWAY OR WAVE", texts)
                if demo:
                    self.assertIn("Up Down / W S: wave", texts)
                self.assertIn("Your turn in a moment", texts)
                self.assertFalse(any("Enter" in value or "Space" in value for value in texts))

    def test_idle_uses_requested_game_title(self):
        texts = self.drawn_text(scene("idle"))
        self.assertIn("How HOT are you", texts)
        self.assertFalse(any("CHILLI SHIMMY" in value for value in texts))

    def test_tutorial_shows_engine_readiness_message_without_extra_copy(self):
        for message in ("Step into the play area", "Camera warming up..."):
            with self.subTest(message=message):
                game = scene("instructions")
                game.message = message
                texts = self.drawn_text(game)
                self.assertEqual(texts[-1], message)
                self.assertNotIn("Your turn in a moment", texts)
        game.message = ""
        self.assertEqual(self.drawn_text(game)[-1], "Your turn in a moment")

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
        with patch.object(self.renderer, "text", wraps=self.renderer.text) as draw_text:
            self.renderer._start_prompt("Press Enter or Space to start")
        self.assertEqual(draw_text.call_args.args[1], box.center)
        prompt_size = self.renderer.font(25, True).size("Press Enter or Space to start")
        self.assertTrue(box.contains(pygame.Rect((0, 0), prompt_size).move(
            box.centerx-prompt_size[0]//2, box.centery-prompt_size[1]//2)))
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

    def test_motion_moves_chilli_without_altering_score_and_keeps_full_footprint_clear(self):
        game = scene(heat=1.)
        game.round_number = 1
        left, top, right, bottom = PLAY_BOUNDS
        positions = []
        for frame in range(180):
            now = frame/30
            game.motion_timestamp = now
            game.motion_x = math.cos(now*.8)
            game.motion_y = math.sin(now*.8)
            game.motion_energy = 1.
            self.renderer.draw(game, now)
            rect = self.renderer.balloon_rect
            self.assertGreaterEqual(rect.left, left)
            self.assertGreaterEqual(rect.top, top)
            self.assertLessEqual(rect.right, right)
            self.assertLessEqual(rect.bottom, bottom)
            self.assertLessEqual(rect.width, 390)
            self.assertLessEqual(rect.height, 330)
            self.assertEqual(game.heat, 1.)
            positions.append(rect.center)
        self.assertGreater(max(x for x, _ in positions)-min(x for x, _ in positions), 250)
        self.assertGreater(max(y for _, y in positions)-min(y for _, y in positions), 60)
        self.assertLessEqual(len(self.renderer.balloon_cache), 24)
        self.assertLessEqual(len(self.renderer.sprite_cache), 32)

    def test_new_round_and_leaving_play_reset_balloon_without_replaying_audio_serial(self):
        game = scene()
        game.round_number = 1
        game.motion_x, game.motion_y, game.motion_energy = 1., .2, 1.
        game.motion_timestamp = 0.
        self.renderer.draw(game, 0.)
        self.renderer.draw(game, .1)
        self.assertNotEqual(self.renderer.balloon_rect.center, (640, 365))
        serial = self.renderer.impact_serial
        game.state = "instructions"
        self.renderer.draw(game, .2)
        self.assertIsNone(self.renderer.balloon_rect)
        self.assertEqual(self.renderer.movement_energy, 0.)
        self.assertEqual(self.renderer.impact_serial, serial)
        game.state, game.round_number = "playing", 2
        game.motion_timestamp = None
        self.renderer.draw(game, .3)
        self.assertEqual(self.renderer.balloon_rect.center, (640, 365))
        self.assertEqual(self.renderer.balloon.vx, 0.)
        self.assertEqual(self.renderer.balloon.vy, 0.)

    def test_completed_round_has_heat_rating_and_one_time_line(self):
        game = scene("won", heat=1.)
        game.result_elapsed, game.best_time, game.new_record = 5.42, 5.42, True
        texts = self.drawn_text(game, demo=True)
        self.assertIn("You're on fire!", texts)
        self.assertIn("VOLCANIC", texts)
        self.assertEqual([line for line in texts if "Best:" in line], ["New record! 5.4s   |   Best: 5.4s"])
        self.assertIn("Press Enter or Space to play again", texts)
        for heat, expected in ((.2, "WARM"), (.4, "SPICY"), (.8, "SCORCHING")):
            with self.subTest(heat=heat):
                game.state, game.heat = "timeout", heat
                texts = self.drawn_text(game)
                self.assertIn(expected, texts)
                self.assertIn("Best: 5.4s", texts)
                self.assertFalse(any("New record!" in line for line in texts))

    def test_records_never_clutter_preparation_clear_or_playing(self):
        for state in ("idle", "instructions", "countdown", "clear", "playing"):
            with self.subTest(state=state):
                game = scene(state)
                game.result_elapsed, game.best_time, game.new_record = 5.42, 5.42, True
                texts = self.drawn_text(game)
                self.assertFalse(any("Best:" in line or "record" in line for line in texts))


if __name__ == "__main__":
    unittest.main()
