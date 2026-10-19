import math
import unittest

from chilli.game import Game, GameConfig, PoseSample


def pose(t, x=0.5, scale=0.2, lean=0.0, present=True, left_hand=None, right_hand=None):
    return PoseSample(t, present, x, scale, lean, left_hand, right_hand)


class GameTests(unittest.TestCase):
    def start(self, **kwargs):
        settings = {"settle_seconds": 0, "instructions_seconds": 0, "countdown_seconds": 0}
        settings.update(kwargs)
        game = Game(GameConfig(**settings))
        game.update(0.0, pose(0.0))
        self.assertEqual(game.state, "playing")
        return game

    def test_default_preparation_is_separate_from_ten_second_round(self):
        game = Game(GameConfig())
        for i in range(81):
            t = i / 10
            game.update(t, pose(t))
            expected = "idle" if t < 1 else "instructions" if t < 5 else "countdown" if t < 8 else "playing"
            self.assertEqual(game.state, expected)
            self.assertEqual(game.heat, 0)
            self.assertEqual(game.remaining, 10)
        self.assertEqual(game.state, "playing")
        self.assertEqual(game.round_number, 1)
        self.assertEqual(game.remaining, 10.0)
        for i in range(81, 181):
            t = i / 10
            game.update(t, pose(t))
        self.assertEqual(game.state, "timeout")
        self.assertEqual(game.remaining, 0)

    def test_explicit_begin_shows_instructions_without_faking_a_player(self):
        game = Game(GameConfig())
        game.begin(100)
        self.assertEqual(game.state, "instructions")
        self.assertFalse(game.player_visible)
        self.assertEqual(game.message, "Step into the play area")
        self.assertEqual(game.heat, 0)
        self.assertEqual(game.remaining, 10)
        self.assertEqual(game.countdown, 0)
        self.assertEqual(game.round_number, 0)

    def test_explicit_begin_waits_for_late_camera_and_player_without_using_timer(self):
        game = Game(GameConfig())
        game.begin(100)
        for t in (100, 101, 110):
            game.update(t, None, camera_ready=False)
            self.assertEqual(game.state, "instructions")
            self.assertEqual(game.message, "Connect a camera in Settings")
            self.assertEqual(game.remaining, 10)
            self.assertEqual(game.heat, 0)
        game.update(111, pose(111, present=False))
        self.assertEqual(game.state, "instructions")
        self.assertEqual(game.message, "Step into the play area")
        for i in range(10):
            t = 120 + i / 10
            game.update(t, pose(t))
            self.assertEqual(game.state, "instructions")
            self.assertEqual(game.remaining, 10)
        game.update(121, pose(121))
        self.assertEqual(game.state, "countdown")
        self.assertEqual(game.countdown, 3)
        for i in range(1, 31):
            t = 121 + i / 10
            game.update(t, pose(t))
        self.assertEqual(game.state, "playing")
        self.assertEqual(game.remaining, 10)
        self.assertEqual(game.heat, 0)

    def test_explicit_begin_keeps_full_tutorial_even_when_player_is_ready(self):
        game = Game(GameConfig(target_motion=0.001))
        game.begin(0)
        for i in range(40):
            t = i / 10
            game.update(t, pose(t, 0.5 + 0.1 * math.sin(t * math.tau)))
            self.assertEqual(game.state, "instructions")
            self.assertEqual(game.message, "Your turn in a moment")
            self.assertEqual(game.remaining, 10)
            self.assertEqual(game.heat, 0)
        game.update(4, pose(4))
        self.assertEqual(game.state, "countdown")
        self.assertEqual(game.countdown, 3)
        for i in range(41, 71):
            t = i / 10
            game.update(t, pose(t))
        self.assertEqual(game.state, "playing")
        self.assertEqual(game.remaining, 10)
        self.assertEqual(game.heat, 0)

    def test_explicit_tutorial_waits_after_departure_and_rechecks_presence(self):
        game = Game(GameConfig())
        game.begin(0)
        game.update(0, pose(0))
        game.update(0.2, pose(0.2, present=False))
        game.update(4, pose(4, present=False))
        self.assertEqual(game.state, "instructions")
        self.assertEqual(game.message, "Step into the play area")
        for i in range(50, 60):
            t = i / 10
            game.update(t, pose(t))
            self.assertEqual(game.state, "instructions")
        game.update(6, pose(6))
        self.assertEqual(game.state, "countdown")
        self.assertEqual(game.countdown, 3)
        self.assertEqual(game.remaining, 10)

    def test_explicit_begin_cannot_count_a_pose_gap_as_settled_presence(self):
        game = Game(GameConfig(instructions_seconds=0))
        game.begin(0)
        game.update(0, pose(0))
        game.update(5, pose(5))
        self.assertEqual(game.state, "instructions")
        for i in range(51, 60):
            t = i / 10
            game.update(t, pose(t))
            self.assertEqual(game.state, "instructions")
        game.update(6, pose(6))
        self.assertEqual(game.state, "countdown")
        self.assertEqual(game.countdown, 3)

    def test_explicit_countdown_loss_returns_to_waiting_tutorial(self):
        for loss in ("absent", "camera", "gap"):
            with self.subTest(loss=loss):
                game = Game(GameConfig())
                game.begin(0)
                for i in range(41):
                    t = i / 10
                    game.update(t, pose(t))
                self.assertEqual(game.state, "countdown")
                if loss == "absent":
                    game.update(4.1, pose(4.1, present=False))
                elif loss == "camera":
                    game.update(4.1, None, camera_ready=False)
                else:
                    game.update(4.7, pose(4.7))
                self.assertEqual(game.state, "instructions")
                self.assertEqual(game.remaining, 10)
                self.assertEqual(game.heat, 0)
                self.assertEqual(game.round_number, 0)
                game.update(10, None, camera_ready=False)
                self.assertEqual(game.state, "instructions")
                self.assertEqual(game.message, "Connect a camera in Settings")

    def test_explicit_begin_resets_progress_from_a_previous_round(self):
        game = self.start(target_motion=100)
        game.update(0.1, pose(0.1, 0.53))
        self.assertGreater(game.heat, 0)
        game.begin(0.2)
        self.assertEqual(game.state, "instructions")
        self.assertEqual(game.heat, 0)
        self.assertEqual(game.remaining, 10)
        self.assertFalse(game.player_visible)
        self.assertEqual(game.round_number, 1)

    def test_stationary_and_small_tracking_jitter_do_not_score(self):
        for jitter in (0.0, 0.002):
            with self.subTest(jitter=jitter):
                game = self.start()
                for i in range(1, 150):
                    t = i / 15
                    game.update(t, pose(t, 0.5 + jitter * (-1) ** i, lean=0.01 * (-1) ** i))
                self.assertEqual(game.heat, 0.0)
                self.assertEqual(game.state, "playing")

    def test_comfortable_sway_wins_early(self):
        game = self.start()
        for i in range(1, 150):
            t = i / 15
            game.update(t, pose(t, 0.5 + 0.085 * math.sin(t * 2 * math.pi * 0.9)))
            if game.state == "won":
                break
        self.assertEqual(game.state, "won")
        self.assertEqual(game.heat, 1.0)
        self.assertGreater(game.remaining, 0)
        self.assertLessEqual(abs(game.sway), 1.0)

    def hand_game(self, *, left_hand=(0.8, 0.8), right_hand=None, **kwargs):
        game = Game(GameConfig(settle_seconds=0, instructions_seconds=0, countdown_seconds=0, **kwargs))
        game.update(0, pose(0, left_hand=left_hand, right_hand=right_hand))
        self.assertEqual(game.state, "playing")
        return game

    def test_one_hand_can_win_with_horizontal_vertical_or_diagonal_waves(self):
        for direction in ((1, 0), (0, 1), (math.sqrt(0.5), math.sqrt(0.5))):
            with self.subTest(direction=direction):
                game = self.hand_game()
                for i in range(1, 300):
                    t = i / 30
                    offset = 1.4 * math.sin(t * math.tau * 0.7)
                    hand = (0.8 + direction[0] * offset, 0.8 + direction[1] * offset)
                    game.update(t, pose(t, left_hand=hand))
                    if game.state == "won":
                        break
                self.assertEqual(game.state, "won")
                self.assertEqual(game.heat, 1)
                self.assertGreater(game.remaining, 0)

    def test_stationary_hands_and_small_wrist_jitter_do_not_score(self):
        for amplitude in (0, 0.012):
            with self.subTest(amplitude=amplitude):
                game = self.hand_game(left_hand=(-0.8, 0.8), right_hand=(0.8, 0.8))
                for i in range(1, 300):
                    t = i / 30
                    jitter = amplitude * (-1) ** i
                    game.update(t, pose(t, left_hand=(-0.8 + jitter, 0.8 - jitter),
                                        right_hand=(0.8 - jitter, 0.8 + jitter)))
                self.assertEqual(game.heat, 0)
                self.assertEqual(game.motion_energy, 0)

    def test_opposing_hands_retain_energy_and_dominant_direction(self):
        game = self.hand_game(left_hand=(-0.8, 0.8), right_hand=(0.8, 0.8))
        game.update(0.1, pose(0.1, left_hand=(-0.8, 1.2), right_hand=(0.8, 0.4)))
        self.assertGreater(game.heat, 0)
        self.assertGreater(game.motion_energy, 0.5)
        self.assertGreater(abs(game.motion_y), 0.5)
        self.assertAlmostEqual(game.motion_x, 0)
        self.assertEqual(game.motion_timestamp, 0.1)

    def test_hand_occlusion_and_reappearance_never_award_missing_travel(self):
        game = self.hand_game(target_motion=100)
        game.update(0.1, pose(0.1, left_hand=(0.8, 1.2)))
        earned = game.heat
        self.assertGreater(earned, 0)
        game.update(0.2, pose(0.2))
        self.assertEqual(game.heat, earned)
        self.assertEqual(game.motion_energy, 0)
        game.update(0.3, pose(0.3, left_hand=(-2, -1)))
        game.update(0.4, pose(0.4, left_hand=(-2, -1)))
        self.assertEqual(game.heat, earned)
        self.assertEqual(game.motion_energy, 0)

    def test_visible_hand_keeps_scoring_when_other_hand_is_occluded(self):
        game = self.hand_game(left_hand=(-0.8, 0.8), right_hand=(0.8, 0.8), target_motion=100)
        game.update(0.1, pose(0.1, left_hand=(-0.8, 1.1), right_hand=(0.8, 0.5)))
        earned = game.heat
        game.update(0.2, pose(0.2, left_hand=None, right_hand=(0.8, 0.2)))
        self.assertGreater(game.heat, earned)
        self.assertGreater(game.motion_energy, 0)

    def test_hand_teleports_and_invalid_coordinates_do_not_score(self):
        game = self.hand_game(left_hand=(0, 0))
        game.update(0.1, pose(0.1, left_hand=(5, 5)))
        game.update(0.2, pose(0.2, left_hand=(5, 5)))
        self.assertEqual(game.heat, 0)
        invalid = (None, (float("nan"), 0), (0, float("inf")), (7, 0), ("x", 1), (1,), "bad")
        for i, point in enumerate(invalid, 3):
            t = i / 10
            game.update(t, pose(t, left_hand=point))
            self.assertEqual(game.heat, 0)
            self.assertEqual(game.motion_energy, 0)
        game.update(1, pose(1, left_hand=(-1, -1)))
        self.assertEqual(game.heat, 0)

    def test_person_or_scale_jump_resets_both_hand_baselines(self):
        for x, scale in ((0.95, 0.2), (0.5, 0.4)):
            with self.subTest(x=x, scale=scale):
                game = self.hand_game(left_hand=(-0.8, 0.8), right_hand=(0.8, 0.8))
                for t in (0.1, 0.2):
                    game.update(t, pose(t, x=x, scale=scale, left_hand=(1, -1), right_hand=(-1, 2)))
                self.assertEqual(game.heat, 0)
                self.assertEqual(game.motion_energy, 0)

    def test_broad_waves_at_three_tracking_fps_are_not_rejected_as_teleports(self):
        game = self.hand_game(left_hand=(-1, 1))
        game.update(1 / 3, pose(1 / 3, left_hand=(1, -1)))
        self.assertGreater(game.heat, 0)
        self.assertGreater(game.motion_energy, 0)

    def test_hand_scoring_is_comparable_at_three_ten_fifteen_and_thirty_fps(self):
        scores = []
        for fps in (3, 10, 15, 30):
            game = self.hand_game(left_hand=(0.8, -1.2), target_motion=100)
            for i in range(1, fps * 9 + 1):
                t = i / fps
                phase = t % 3
                y = -1.2 + 1.6 * phase if phase < 1.5 else 1.2 - 1.6 * (phase - 1.5)
                game.update(t, pose(t, left_hand=(0.8, y)))
            scores.append(game.heat)
        self.assertGreater(min(scores), 0)
        self.assertLess(max(scores) / min(scores), 1.25)

    def test_combined_body_and_two_hands_have_one_shared_scoring_cap(self):
        game = self.hand_game(left_hand=(-0.8, 0.8), right_hand=(0.8, 0.8))
        for i in range(1, 61):
            t = i / 30
            wave = 1.4 * math.sin(t * math.tau)
            game.update(t, pose(t, x=0.5 + 0.1 * math.sin(t * math.tau),
                                left_hand=(-0.8, 0.8 + wave), right_hand=(0.8, 0.8 - wave)))
            self.assertLessEqual(game.motion_energy, 1)
            self.assertLessEqual(math.hypot(game.motion_x, game.motion_y), 1.00000001)
        self.assertEqual(game.state, "playing")
        self.assertLessEqual(game.heat, 2 * game.config.max_combined_speed / game.config.target_motion + 1e-8)

    def test_feedback_is_once_per_observation_and_clears_on_loss_or_preparation(self):
        for explicit_absence in (True, False):
            with self.subTest(explicit_absence=explicit_absence):
                game = self.hand_game()
                sample = pose(0.1, left_hand=(0.8, 1.2))
                game.update(0.1, sample)
                feedback = game.motion_x, game.motion_y, game.motion_energy, game.motion_timestamp
                game.update(0.15, sample)
                self.assertEqual((game.motion_x, game.motion_y, game.motion_energy, game.motion_timestamp), feedback)
                game.update(0.6, pose(0.6, present=False) if explicit_absence else None)
                self.assertEqual((game.motion_x, game.motion_y, game.motion_energy), (0, 0, 0))
                self.assertIsNone(game.motion_timestamp)
                game.begin(0.7)
                game.update(0.8, pose(0.8, left_hand=(-1, -1)))
                self.assertEqual((game.motion_x, game.motion_y, game.motion_energy), (0, 0, 0))
                self.assertIsNone(game.motion_timestamp)

    def test_body_sway_produces_horizontal_feedback_without_hands(self):
        game = self.start()
        game.update(0.1, pose(0.1, x=0.54))
        self.assertGreater(game.motion_x, 0)
        self.assertEqual(game.motion_y, 0)
        self.assertGreater(game.motion_energy, 0)

    def test_render_frame_rate_cannot_multiply_points(self):
        def run(render_fps):
            game = self.start(target_motion=100)
            last_capture = -1
            sample = pose(0)
            for frame in range(1, render_fps * 5 + 1):
                now = frame / render_fps
                capture = math.floor(now * 10 + 1e-8)
                if capture != last_capture:
                    t = capture / 10
                    sample = pose(t, 0.5 + 0.08 * math.sin(2 * math.pi * t))
                    last_capture = capture
                game.update(now, sample)
            return game.heat, game.remaining
        slow = run(20)
        fast = run(120)
        self.assertAlmostEqual(slow[0], fast[0], places=12)
        self.assertAlmostEqual(slow[1], fast[1], places=12)

    def test_tracking_rate_keeps_comparable_difficulty(self):
        scores = []
        for fps in (10, 15, 30):
            game = self.start(target_motion=100)
            for i in range(1, fps * 5 + 1):
                t = i / fps
                game.update(t, pose(t, 0.5 + 0.08 * math.sin(2 * math.pi * 0.8 * t)))
            scores.append(game.heat)
        self.assertGreater(min(scores), 0)
        self.assertLess(max(scores) / min(scores), 1.15)

    def test_body_size_normalization(self):
        scores = []
        for size in (0.1, 0.2, 0.35):
            game = Game(GameConfig(settle_seconds=0, instructions_seconds=0, countdown_seconds=0, target_motion=100))
            game.update(0, pose(0, scale=size))
            for i in range(1, 75):
                t = i / 15
                game.update(t, pose(t, 0.5 + size * 0.4 * math.sin(2 * math.pi * t), scale=size))
            scores.append(game.heat)
        for score in scores[1:]:
            self.assertAlmostEqual(score, scores[0], places=12)

    def test_short_loss_keeps_heat_and_timer_but_reacquisition_gets_no_points(self):
        game = self.start(target_motion=100)
        game.update(0.1, pose(0.1, 0.53))
        earned = game.heat
        self.assertGreater(earned, 0)
        game.update(0.2, pose(0.2, present=False))
        game.update(0.7, pose(0.7, 0.75))
        self.assertEqual(game.state, "playing")
        self.assertEqual(game.heat, earned)
        self.assertAlmostEqual(game.remaining, 9.3)
        game.update(0.8, pose(0.8, 0.75))
        self.assertEqual(game.heat, earned)

    def test_stale_frames_and_duplicate_samples_cannot_score(self):
        game = self.start(target_motion=100)
        sample = pose(0.1, 0.53)
        game.update(0.1, sample)
        earned = game.heat
        for now in (0.2, 0.3, 0.6, 1.0):
            game.update(now, sample)
        self.assertFalse(game.player_visible)
        self.assertEqual(game.heat, earned)
        game.update(1.1, pose(0.5, 0.8))
        self.assertEqual(game.heat, earned)
        game.update(1.2, pose(1.2, 0.8))
        self.assertEqual(game.heat, earned)

    def test_camera_sample_gap_never_scores_the_missing_movement(self):
        game = self.start()
        game.update(0.6, pose(0.6, 0.7))
        self.assertEqual(game.heat, 0)

    def test_sustained_loss_cancels_round(self):
        game = self.start()
        game.update(0.2, pose(0.2, present=False))
        game.update(2.21, None)
        self.assertEqual(game.state, "clear")

    def test_reappearance_cannot_rescue_an_already_abandoned_round(self):
        for explicit_absence in (True, False):
            with self.subTest(explicit_absence=explicit_absence):
                game = self.start()
                if explicit_absence:
                    game.update(0.2, pose(0.2, present=False))
                game.update(2.5, pose(2.5, 0.6))
                self.assertEqual(game.state, "clear")
                self.assertEqual(game.heat, 0)

    def test_reacquisition_uses_current_body_size(self):
        game = self.start(target_motion=100)
        game.update(0.1, pose(0.1, present=False))
        game.update(0.2, pose(0.2, scale=0.4))
        baseline = Game(GameConfig(settle_seconds=0, instructions_seconds=0, countdown_seconds=0, target_motion=100))
        baseline.update(0.2, pose(0.2, scale=0.4))
        for i in range(3, 10):
            t = i / 10
            sample = pose(t, 0.5 + 0.08 * math.sin(t * 2 * math.pi), scale=0.4)
            game.update(t, sample)
            baseline.update(t, sample)
        self.assertAlmostEqual(game.heat, baseline.heat, places=12)

    def test_tracking_jump_is_rebaselined_without_awarding_points(self):
        for x, scale in ((0.9, 0.2), (0.55, 0.4)):
            with self.subTest(x=x, scale=scale):
                game = self.start()
                game.update(0.1, pose(0.1, x, scale))
                game.update(0.2, pose(0.2, x, scale))
                self.assertEqual(game.heat, 0)

    def test_no_points_at_or_after_deadline(self):
        for sample_time, now in ((10, 10), (9.99, 10.01), (10.01, 10.01)):
            with self.subTest(sample_time=sample_time, now=now):
                game = self.start(target_motion=0.001)
                for i in range(1, 100):
                    t = i / 10
                    game.update(t, pose(t))
                game.update(now, pose(sample_time, 0.53))
                self.assertEqual(game.state, "timeout")
                self.assertEqual(game.heat, 0)

    def test_future_out_of_order_and_invalid_samples_are_ignored(self):
        game = self.start()
        game.update(0.1, pose(0.5, 0.8))
        game.update(0.2, pose(-1, 0.8))
        self.assertEqual(game.heat, 0)
        game.update(0.3, pose(0.3, float("nan")))
        self.assertFalse(game.player_visible)
        self.assertEqual(game.heat, 0)

    def test_result_waits_for_player_to_leave_before_rearming(self):
        game = self.start(round_seconds=1, result_seconds=0.5, clear_seconds=0.5)
        game.update(1, pose(1))
        self.assertEqual(game.state, "timeout")
        game.update(1.5, pose(1.5))
        self.assertEqual(game.state, "clear")
        game.update(2, pose(2))
        self.assertEqual(game.state, "clear")
        game.update(2.1, pose(2.1, present=False))
        game.update(2.4, pose(2.4))
        self.assertEqual(game.state, "clear")
        game.update(2.5, pose(2.5, present=False))
        game.update(3, pose(3, present=False))
        self.assertEqual(game.state, "idle")
        game.update(3.1, pose(3.1))
        self.assertEqual(game.state, "playing")
        self.assertEqual(game.round_number, 2)
        self.assertEqual(game.heat, 0)

    def test_countdown_aborts_when_player_leaves(self):
        game = Game(GameConfig(settle_seconds=0, instructions_seconds=0))
        game.update(0, pose(0))
        self.assertEqual(game.state, "countdown")
        self.assertEqual(game.countdown, 3)
        game.update(0.1, pose(0.1, present=False))
        self.assertEqual(game.state, "idle")
        self.assertEqual(game.round_number, 0)

    def test_practice_during_instructions_and_countdown_cannot_score_or_use_play_time(self):
        game = Game(GameConfig(settle_seconds=0, target_motion=0.001))
        for i in range(71):
            t = i / 10
            game.update(t, pose(t, 0.5 + 0.15 * math.sin(t * math.tau)))
            self.assertEqual(game.heat, 0)
            self.assertEqual(game.remaining, 10)
            self.assertEqual(game.round_number, int(t >= 7))
            if t < 4:
                self.assertEqual(game.state, "instructions")
            elif t < 7:
                self.assertEqual(game.state, "countdown")
        self.assertEqual(game.state, "playing")
        game.update(7.1, pose(7.1))
        self.assertEqual(game.heat, 0)
        self.assertAlmostEqual(game.remaining, 9.9)

    def test_instructions_abort_on_departure_or_stale_pose_and_restart_in_full(self):
        for explicit_absence in (True, False):
            with self.subTest(explicit_absence=explicit_absence):
                game = Game(GameConfig(settle_seconds=0))
                game.update(0, pose(0))
                self.assertEqual(game.state, "instructions")
                game.update(0.5, pose(0.5, present=False) if explicit_absence else None)
                self.assertEqual(game.state, "idle")
                self.assertEqual(game.heat, 0)
                self.assertEqual(game.remaining, 10)
                self.assertEqual(game.round_number, 0)
                game.update(1, pose(1))
                for i in range(11, 50):
                    t = i / 10
                    game.update(t, pose(t))
                    self.assertEqual(game.state, "instructions")
                game.update(5, pose(5))
                self.assertEqual(game.state, "countdown")
                self.assertEqual(game.countdown, 3)

    def test_instruction_duration_is_clock_based_at_different_frame_rates(self):
        for fps in (10, 30, 60):
            with self.subTest(fps=fps):
                game = Game(GameConfig(settle_seconds=0.5, instructions_seconds=1.2, countdown_seconds=0.3))
                for frame in range(2 * fps + 1):
                    t = frame / fps
                    game.update(t, pose(t))
                self.assertEqual(game.state, "playing")
                self.assertEqual(game.remaining, 10)
                self.assertEqual(game.heat, 0)

    def test_zero_instruction_duration_skips_directly_to_countdown(self):
        game = Game(GameConfig(settle_seconds=0, instructions_seconds=0))
        game.update(0, pose(0))
        self.assertEqual(game.state, "countdown")
        self.assertEqual(game.countdown, 3)
        self.assertEqual(game.remaining, 10)

    def test_camera_rearm_repeats_instructions_before_the_next_round(self):
        game = Game(GameConfig(
            settle_seconds=0, instructions_seconds=0.2, countdown_seconds=0,
            round_seconds=0.2, result_seconds=0.1, clear_seconds=0.1,
        ))
        for t in (0, 0.1, 0.2, 0.3, 0.4):
            game.update(t, pose(t))
        self.assertEqual(game.state, "timeout")
        game.update(0.51, pose(0.51))
        self.assertEqual(game.state, "clear")
        game.update(0.6, pose(0.6, present=False))
        game.update(0.8, pose(0.8, present=False))
        self.assertEqual(game.state, "idle")
        game.update(0.9, pose(0.9))
        self.assertEqual(game.state, "instructions")
        self.assertEqual(game.round_number, 1)
        game.update(1.0, pose(1.0))
        self.assertEqual(game.state, "instructions")
        game.update(1.1, pose(1.1))
        self.assertEqual(game.state, "playing")
        self.assertEqual(game.round_number, 2)
        self.assertAlmostEqual(game.remaining, 0.2)

    def test_camera_failure_recovers_through_clear_gate(self):
        game = self.start()
        game.update(0.1, pose(0.1), camera_ready=False)
        self.assertEqual(game.state, "error")
        self.assertFalse(game.player_visible)
        game.update(0.2, pose(0.2), camera_ready=True)
        self.assertEqual(game.state, "clear")
        game.update(0.3, pose(0.3, present=False))
        game.update(1.31, pose(1.31, present=False))
        self.assertEqual(game.state, "idle")

    def test_operator_reset_keeps_round_number(self):
        game = self.start()
        game.update(0.1, pose(0.1, 0.53))
        game.reset(0.2)
        self.assertEqual(game.state, "idle")
        self.assertEqual(game.heat, 0)
        self.assertEqual(game.remaining, 10)
        self.assertEqual(game.round_number, 1)

    def test_unattended_rounds_and_camera_reconnections_do_not_leak_state(self):
        game = Game(GameConfig(
            settle_seconds=0, instructions_seconds=0, countdown_seconds=0, round_seconds=1,
            result_seconds=0.1, clear_seconds=0.1, target_motion=0.03,
        ))
        now = 100_000.0  # A boot-relative monotonic clock need not begin at zero.

        def tick(delta, x=0.5, present=True, ready=True):
            nonlocal now
            now += delta
            game.update(now, pose(now, x=x, present=present), camera_ready=ready)

        for round_index in range(30):
            self.assertEqual(game.state, "idle")
            tick(0.01)
            self.assertEqual(game.state, "playing")
            if round_index % 2:
                tick(1.001)
                self.assertEqual(game.state, "timeout")
            else:
                tick(0.1, x=0.55)
                self.assertEqual(game.state, "won")
            tick(0.11)
            self.assertEqual(game.state, "clear")
            tick(0.2)
            self.assertEqual(game.state, "clear")
            tick(0.01, present=False)
            tick(0.11, present=False)
            self.assertEqual(game.state, "idle")
            self.assertEqual(game.heat, 0)
            if round_index % 10 == 0:
                tick(0.01, ready=False)
                self.assertEqual(game.state, "error")
                tick(0.01, present=False)
                self.assertEqual(game.state, "clear")
                tick(0.11, present=False)
                self.assertEqual(game.state, "idle")
        self.assertEqual(game.round_number, 30)

    def test_invalid_configuration_and_clock_fail_fast(self):
        for kwargs in (
            {"target_motion": 0}, {"round_seconds": -1}, {"smoothing_seconds": float("nan")},
            {"instructions_seconds": -1}, {"instructions_seconds": float("inf")},
        ):
            with self.assertRaises(ValueError):
                GameConfig(**kwargs)
        game = self.start()
        with self.assertRaises(ValueError):
            game.update(-1, None)


if __name__ == "__main__":
    unittest.main()
