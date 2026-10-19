"""Replay real pygame key events through the controller and gameplay engine."""

import os
import unittest

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import pygame
except ImportError:
    pygame = None

from chilli.game import Game, GameConfig

if pygame is not None:
    from chilli.demo import DemoController


@unittest.skipIf(pygame is None, "pygame is required for keyboard event tests")
class DemoTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(GameConfig())
        self.demo = DemoController(self.game)
        self.now = 100_000.0

    def event(self, kind, key, **kwargs):
        self.demo.handle_event(pygame.event.Event(kind, key=key, **kwargs), self.now)

    def tap(self, key):
        self.event(pygame.KEYDOWN, key)
        self.event(pygame.KEYUP, key)

    def frame(self, dt=1 / 30):
        self.now += dt
        sample = self.demo.update(self.now, dt)
        self.game.update(self.now, sample)
        return sample

    def start_playing(self):
        self.tap(pygame.K_RETURN)
        self.assertEqual(self.game.state, "instructions")
        self.assertEqual(self.game.countdown, 0)
        visited = set()
        for _ in range(215):
            self.frame()
            visited.add(self.game.state)
            if self.game.state == "playing":
                break
        self.assertIn("countdown", visited)
        self.assertEqual(self.game.state, "playing")

    def test_initially_idle_and_start_keys_confirm_presence(self):
        self.frame()
        self.assertFalse(self.demo.active)
        self.assertEqual(self.game.state, "idle")
        self.tap(pygame.K_SPACE)
        self.assertTrue(self.demo.active)
        self.assertTrue(self.game.player_visible)
        self.assertEqual(self.game.state, "instructions")
        self.assertEqual(self.game.countdown, 0)

    def test_start_keys_cannot_restart_or_skip_the_how_to_play_screen(self):
        self.tap(pygame.K_SPACE)
        for frame in range(16):
            self.assertEqual(self.game.state, "instructions")
            if frame in (4, 8, 12):
                self.tap(pygame.K_RETURN if frame == 8 else pygame.K_SPACE)
            self.frame(0.25)
            self.assertEqual(self.game.heat, 0)
            self.assertEqual(self.game.remaining, 10)
        self.assertEqual(self.game.state, "countdown")
        self.assertEqual(self.game.countdown, 3)

    def test_keyboard_practice_during_instructions_does_not_earn_heat(self):
        self.tap(pygame.K_RETURN)
        for frame in range(90):
            if frame % 6 == 0:
                self.tap(pygame.K_LEFT if (frame // 6) % 2 else pygame.K_RIGHT)
            self.frame()
            self.assertEqual(self.game.state, "instructions")
            self.assertEqual(self.game.heat, 0)
            self.assertEqual(self.game.remaining, 10)
            self.assertEqual(self.game.round_number, 0)

    def test_zero_instruction_setting_keeps_the_full_countdown(self):
        self.game = Game(GameConfig(instructions_seconds=0))
        self.demo = DemoController(self.game)
        self.tap(pygame.K_RETURN)
        self.assertEqual(self.game.state, "countdown")
        self.assertEqual(self.game.countdown, 3)

    def test_enter_and_space_do_not_toggle_player_out_during_active_round(self):
        self.start_playing()
        remaining = self.game.remaining
        for key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
            self.tap(key)
            self.frame()
        self.assertTrue(self.demo.active)
        self.assertTrue(self.game.player_visible)
        self.assertEqual(self.game.state, "playing")
        self.assertLess(self.game.remaining, remaining)
        self.assertEqual(self.game.round_number, 1)

    def test_quick_tap_received_between_frames_still_moves_and_scores(self):
        self.start_playing()
        self.tap(pygame.K_LEFT)
        # get_pressed() sees no held key here; the event controller keeps a pulse.
        positions = [self.frame().x for _ in range(8)]
        self.assertLess(min(positions), 0.46)
        self.assertGreater(self.game.heat, 0)
        self.assertGreater(positions[-1], min(positions))

    def test_held_key_moves_toward_a_bounded_stance_and_release_recenters(self):
        self.start_playing()
        self.event(pygame.KEYDOWN, pygame.K_RIGHT)
        positions = [self.frame().x for _ in range(60)]
        self.assertGreater(positions[-1], 0.65)
        self.assertLessEqual(max(positions), DemoController.MAX_X)
        self.assertNotEqual(self.game.state, "won")
        self.event(pygame.KEYUP, pygame.K_RIGHT)
        for _ in range(30):
            self.frame()
        self.assertAlmostEqual(self.demo.x, 0.5, places=4)

    def test_alternating_held_arrows_wins_full_default_round_at_30_fps(self):
        self.start_playing()
        previous = None
        for frame in range(300):
            key = pygame.K_LEFT if (frame // 12) % 2 == 0 else pygame.K_RIGHT
            if key != previous:
                if previous is not None:
                    self.event(pygame.KEYUP, previous)
                self.event(pygame.KEYDOWN, key)
                previous = key
            self.frame()
            if self.game.state == "won":
                break
        self.assertEqual(self.game.state, "won")
        self.assertEqual(self.game.heat, 1)
        self.assertGreater(self.game.remaining, 0)

    def test_alternating_short_taps_win_without_any_held_key_polling(self):
        self.start_playing()
        for frame in range(300):
            if frame % 6 == 0:
                self.tap(pygame.K_a if (frame // 6) % 2 == 0 else pygame.K_d)
            self.frame()
            if self.game.state == "won":
                break
        self.assertEqual(self.game.state, "won")
        self.assertGreater(self.game.remaining, 0)

    def test_no_input_times_out_with_zero_heat_then_enter_retries(self):
        self.start_playing()
        for _ in range(305):
            self.frame()
            if self.game.state == "timeout":
                break
        self.assertEqual(self.game.state, "timeout")
        self.assertEqual(self.game.heat, 0)
        self.tap(pygame.K_RETURN)
        self.assertEqual(self.game.state, "instructions")
        self.assertEqual(self.game.countdown, 0)
        self.assertTrue(self.demo.active)
        self.assertEqual(self.game.remaining, 10)

    def test_retry_works_from_result_and_clear_without_simulated_exit(self):
        for state in ("won", "timeout", "clear"):
            with self.subTest(state=state):
                self.game.state = state
                self.demo.active = True
                self.tap(pygame.K_SPACE)
                self.assertEqual(self.game.state, "instructions")
                self.assertEqual(self.demo.x, 0.5)
                self.assertTrue(self.demo.active)
                self.assertEqual(self.game.heat, 0)

    def test_start_autorepeat_cannot_chain_restarts(self):
        self.event(pygame.KEYDOWN, pygame.K_RETURN)
        self.frame()
        self.game.state = "timeout"
        self.event(pygame.KEYDOWN, pygame.K_RETURN, repeat=True)
        self.assertEqual(self.game.state, "timeout")
        self.event(pygame.KEYUP, pygame.K_RETURN)
        self.tap(pygame.K_RETURN)
        self.assertEqual(self.game.state, "instructions")

    def test_opposite_keys_are_neutral_and_focus_loss_clears_stuck_keys(self):
        self.start_playing()
        self.event(pygame.KEYDOWN, pygame.K_LEFT)
        self.event(pygame.KEYDOWN, pygame.K_RIGHT)
        for _ in range(15):
            self.frame()
        self.assertEqual(self.demo.direction, 0)
        self.assertEqual(self.demo.x, 0.5)
        self.assertEqual(self.game.heat, 0)
        self.event(pygame.KEYUP, pygame.K_LEFT)
        for _ in range(10):
            self.frame()
        self.assertGreater(self.demo.x, 0.5)
        self.demo.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST), self.now)
        for _ in range(30):
            self.frame()
        self.assertEqual(self.demo.direction, 0)
        self.assertAlmostEqual(self.demo.x, 0.5, places=4)
        self.assertTrue(self.demo.active)

    def test_operator_restart_clears_motion_and_starts_instructions(self):
        self.start_playing()
        self.event(pygame.KEYDOWN, pygame.K_RIGHT)
        for _ in range(10):
            self.frame()
        self.demo.reset(self.now)
        self.assertEqual(self.game.state, "instructions")
        self.assertEqual(self.game.countdown, 0)
        self.assertEqual(self.demo.x, 0.5)
        self.assertEqual(self.demo.direction, 0)
        self.assertEqual(self.game.heat, 0)

    def test_hints_match_start_play_and_retry_controls(self):
        self.assertIn("start", self.demo.hint())
        self.demo.active = True
        self.assertIn("LEFT", self.demo.hint("instructions"))
        self.start_playing()
        self.assertIn("LEFT", self.demo.hint())
        self.assertIn("again", self.demo.hint("clear"))


if __name__ == "__main__":
    unittest.main()
