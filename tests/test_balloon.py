"""Visual physics stay bounded and independent of scoring/render frequency."""
import math
import unittest

from chilli.balloon import Balloon, PLAY_BOUNDS


class BalloonTests(unittest.TestCase):
    def test_one_tracking_sample_cannot_become_repeated_impulses(self):
        balloon = Balloon()
        balloon.update(0., motion_timestamp=0., motion_x=.7, motion_y=.4, energy=.8)
        initial_speed = math.hypot(balloon.vx, balloon.vy)
        serial = balloon.impact_serial
        for frame in range(1, 13):
            balloon.update(frame/60, motion_timestamp=0., motion_x=.7, motion_y=.4, energy=.8)
        self.assertAlmostEqual(math.hypot(balloon.vx, balloon.vy), initial_speed*math.exp(-Balloon.DRAG*.2), places=7)
        self.assertEqual(balloon.impact_serial, serial)
        self.assertGreater(balloon.x, 640.)
        self.assertGreater(balloon.y, 365.)

    def test_hand_direction_kicks_both_axes(self):
        for dx, dy in ((1., 0.), (-1., 0.), (0., 1.), (0., -1.)):
            with self.subTest(direction=(dx, dy)):
                balloon = Balloon()
                balloon.update(0., motion_timestamp=0., motion_x=dx, motion_y=dy, energy=1.)
                if dx:
                    self.assertGreater(balloon.vx*dx, 0.)
                if dy:
                    self.assertGreater(balloon.vy*dy, 0.)

    def test_stale_and_missing_input_cannot_add_impulses(self):
        balloon = Balloon()
        for now, stamp in ((1., 0.), (1.1, None), (1.2, 2.), (1.3, float("nan"))):
            balloon.update(now, motion_timestamp=stamp, motion_x=1., motion_y=1., energy=1.)
        self.assertEqual((balloon.x, balloon.y), (640., 365.))
        self.assertEqual((balloon.vx, balloon.vy), (0., 0.))
        self.assertEqual(balloon.impact_serial, 0)

    def test_wall_bounces_squash_and_signal_a_single_meaningful_impact(self):
        balloon = Balloon()
        balloon.x, balloon.vx = 1065., 600.
        balloon.update(0., half_width=140.)
        balloon.update(.05, half_width=140.)
        self.assertLess(balloon.vx, 0.)
        self.assertLess(balloon.deformation, 0.)
        self.assertGreater(balloon.impact_serial, 0)
        self.assertLessEqual(balloon.x+140., PLAY_BOUNDS[2])
        serial = balloon.impact_serial
        balloon.update(.1, half_width=140.)
        self.assertEqual(balloon.impact_serial, serial)
        self.assertLess(balloon.x+140., PLAY_BOUNDS[2])

    def test_growth_keeps_entire_sprite_inside_both_axes(self):
        balloon = Balloon()
        balloon.x, balloon.y = 1170., 560.
        balloon.update(0., half_width=195., half_height=165.)
        self.assertLessEqual(balloon.x+195., PLAY_BOUNDS[2])
        self.assertLessEqual(balloon.y+165., PLAY_BOUNDS[3])
        balloon.x, balloon.y = 80., 150.
        balloon.constrain(195., 165., .1)
        self.assertGreaterEqual(balloon.x-195., PLAY_BOUNDS[0])
        self.assertGreaterEqual(balloon.y-165., PLAY_BOUNDS[1])

    def test_long_pause_is_clamped_and_reset_clears_motion_but_preserves_serial(self):
        balloon = Balloon()
        balloon.update(0., motion_timestamp=0., motion_x=1., motion_y=.2, energy=1.)
        serial = balloon.impact_serial
        balloon.update(100.)
        self.assertLess(balloon.x-640., Balloon.MAX_SPEED*Balloon.MAX_FRAME_SECONDS)
        balloon.reset(100.)
        self.assertEqual((balloon.x, balloon.y, balloon.vx, balloon.vy), (640., 365., 0., 0.))
        self.assertEqual((balloon.pop, balloon.movement_energy), (0., 0.))
        self.assertEqual(balloon.stretch, (1., 1.))
        self.assertEqual(balloon.impact_serial, serial)

    def test_new_stationary_samples_stop_energy_without_new_pop(self):
        balloon = Balloon()
        balloon.update(0., motion_timestamp=0., motion_x=.6, motion_y=.2, energy=.8)
        balloon.update(.1, motion_timestamp=.1, energy=0.)
        serial = balloon.impact_serial
        for frame in range(2, 10):
            balloon.update(frame/10, motion_timestamp=frame/10, energy=0.)
        self.assertEqual(balloon.impact_serial, serial)
        self.assertLess(balloon.movement_energy, .01)

    def test_input_frequency_uses_sample_intervals_and_speed_has_a_cap(self):
        def velocity(fps):
            balloon = Balloon(bounds=(0., 0., 100000., 100000.))
            for frame in range(fps+1):
                now = frame/fps
                stamp = math.floor((now+1e-7)*15)/15
                balloon.update(now, motion_timestamp=stamp, motion_x=.2, motion_y=.1, energy=.3)
            return balloon
        low, high = velocity(30), velocity(60)
        self.assertAlmostEqual(low.vx, high.vx, delta=5.)
        self.assertAlmostEqual(low.x, high.x, delta=10.)
        balloon = Balloon()
        for frame in range(60):
            now = frame/60
            balloon.update(now, motion_timestamp=now, motion_x=100., motion_y=100., energy=100.)
            self.assertLessEqual(math.hypot(balloon.vx, balloon.vy), Balloon.MAX_SPEED+.0001)
            self.assertTrue(all(math.isfinite(value) for value in balloon.stretch))

    def test_invalid_bounds_and_nonfinite_time_fail_clearly(self):
        for bounds in ((0, 0, 0, 1), (0, 0, 1, math.inf)):
            with self.assertRaises(ValueError):
                Balloon(bounds)
        with self.assertRaises(ValueError):
            Balloon().update(math.nan)


if __name__ == "__main__":
    unittest.main()
