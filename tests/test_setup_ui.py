"""Exercise the real setup canvas and click geometry with synthetic RGB frames."""

import os
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import numpy as np
import pygame

from chilli.cameras import CameraInfo, DiscoverySnapshot
from chilli.game import PoseSample
from chilli.render import RED, Renderer
from chilli.setup_ui import SetupScreen, canvas_position
from chilli.tracking import TrackingSnapshot


class SetupScreenTests(unittest.TestCase):
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
        self.screen = SetupScreen(self.renderer)
        self.cameras = tuple(
            CameraInfo(i, f"USB camera {i}", 700, f"test-device-{i}")
            for i in range(7)
        )
        self.discovery = DiscoverySnapshot(
            cameras=self.cameras, generation=1, status="Seven webcams found"
        )
        self.frame = np.zeros((240, 320, 3), dtype=np.uint8)
        self.frame[:120, :160] = (12, 34, 56)
        self.frame[:120, 160:] = (45, 67, 89)
        self.frame[120:, :160] = (111, 22, 33)
        self.frame[120:, 160:] = (22, 111, 88)
        self.frame.setflags(write=False)
        self.snapshot = TrackingSnapshot(
            sample=PoseSample(100, True), ready=True, status="Player detected",
            fps=15.0, preview=self.frame,
        )

    def draw(self, **kwargs):
        return self.screen.draw(
            self.snapshot, self.discovery, kwargs.pop("selected", self.cameras[1]),
            can_start=kwargs.pop("can_start", True), now=100, **kwargs,
        )

    def test_live_preview_preserves_rgb_orientation_aspect_and_read_only_input(self):
        before = self.frame.tobytes()
        surface = self.draw()
        # A 320x240 picture fits as 520x390, centered at x=164 inside the
        # 720x390 viewport. Sample all four quadrants away from UI overlays.
        for point, expected in (
            ((200, 260), (12, 34, 56)),
            ((650, 260), (45, 67, 89)),
            ((200, 500), (111, 22, 33)),
            ((650, 500), (22, 111, 88)),
        ):
            with self.subTest(point=point):
                self.assertEqual(surface.get_at(point)[:3], expected)
        self.assertEqual(surface.get_at((100, 300))[:3], (46, 43, 36))
        self.assertEqual(surface.get_at((750, 300))[:3], (46, 43, 36))
        self.assertEqual(self.frame.tobytes(), before)
        self.assertFalse(self.frame.flags.writeable)

    def test_landmarks_use_the_preview_box_coordinates(self):
        points = [(-1.0, -1.0)] * 33
        points[11], points[12] = (0.35, 0.35), (0.65, 0.35)
        points[23], points[24] = (0.4, 0.7), (0.6, 0.7)
        self.snapshot = TrackingSnapshot(
            sample=PoseSample(100, True), ready=True, preview=self.frame,
            landmarks=tuple(points),
        )
        surface = self.draw()
        # Horizontal shoulder connection crosses the exact fitted image center.
        self.assertEqual(surface.get_at((424, 323))[:3], (103, 255, 166))
        # Invalid/unseen joints stay outside the render path.
        self.assertEqual(surface.get_at((200, 260))[:3], (12, 34, 56))

    def test_selected_source_is_highlighted_and_rows_return_the_right_device(self):
        surface = self.draw()
        self.assertEqual(surface.get_at((1000, 212))[:3], RED)
        self.assertNotEqual(surface.get_at((1000, 159))[:3], RED)
        for row, camera in enumerate(self.cameras[:4]):
            with self.subTest(row=row):
                self.assertEqual(self.screen.click((1014, 183 + row * 53)), ("camera", camera))
        self.assertIsNone(self.screen.click((1014, 209)))  # Gap between rows.
        self.assertIsNone(self.screen.click((424, 400)))  # Preview, not a source.
        self.assertIsNone(self.screen.click(None))

    def test_start_requires_ready_frame_and_stale_preview_is_not_shown(self):
        surface = self.draw(can_start=False)
        self.assertIsNone(self.screen.click((1014, 625)))
        self.assertEqual(surface.get_at((200, 260))[:3], (46, 43, 36))
        self.assertEqual(self.screen.click((1014, 183)), ("camera", self.cameras[0]))
        self.assertEqual(self.screen.click((188, 671)), ("demo", None))
        self.draw(can_start=True)
        self.assertEqual(self.screen.click((1014, 625)), ("start", None))
        # Redrawing the disabled state must remove the old enabled hit target.
        self.draw(can_start=False)
        self.assertIsNone(self.screen.click((1014, 625)))

    def test_scrolling_clamps_and_replaces_visible_source_hit_targets(self):
        self.draw()
        self.screen.scroll = 999
        surface = self.draw(selected=self.cameras[-1])
        self.assertEqual(self.screen.scroll, 3)
        visible = [action[1] for _, action, _ in self.screen.actions if action[0] == "camera"]
        self.assertEqual(visible, list(self.cameras[3:]))
        self.assertEqual(self.screen.click((1014, 183)), ("camera", self.cameras[3]))
        self.assertEqual(self.screen.click((1014, 342)), ("camera", self.cameras[6]))
        self.assertEqual(surface.get_at((1000, 318))[:3], RED)
        self.screen.scroll = -10
        self.draw()
        self.assertEqual(self.screen.scroll, 0)
        self.assertEqual(self.screen.click((1014, 183)), ("camera", self.cameras[0]))

    def test_inventory_shrinking_clears_disconnected_rows_and_scroll(self):
        self.screen.scroll = 3
        self.draw()
        self.discovery = DiscoverySnapshot(cameras=(self.cameras[0],), generation=2)
        self.draw(selected=None)
        self.assertEqual(self.screen.scroll, 0)
        self.assertEqual(self.screen.click((1014, 183)), ("camera", self.cameras[0]))
        self.assertIsNone(self.screen.click((1014, 236)))
        self.discovery = DiscoverySnapshot(cameras=(), generation=3)
        self.draw(selected=None)
        self.assertIsNone(self.screen.click((1014, 183)))
        self.assertEqual(self.screen.click((1014, 425)), ("refresh", None))

    def test_manual_index_buttons_obey_source_limits(self):
        self.draw(camera_index=0)
        self.assertIsNone(self.screen.click((854, 510)))
        self.assertEqual(self.screen.click((978, 510)), ("index", 1))
        self.draw(camera_index=63)
        self.assertEqual(self.screen.click((854, 510)), ("index", -1))
        self.assertIsNone(self.screen.click((978, 510)))

    def test_letterboxed_window_clicks_select_same_row_and_start_action(self):
        self.draw()
        for size in ((640, 360), (1600, 1000), (1920, 720), (1000, 1000)):
            width, height = size
            factor = min(width / 1280, height / 720)
            ox, oy = (width - 1280 * factor) / 2, (height - 720 * factor) / 2
            for point, expected in (
                ((1014, 236), ("camera", self.cameras[1])),
                ((1014, 625), ("start", None)),
            ):
                with self.subTest(size=size, action=expected[0]):
                    window_point = (ox + point[0] * factor, oy + point[1] * factor)
                    self.assertEqual(self.screen.click(canvas_position(window_point, size)), expected)


class CanvasPositionTests(unittest.TestCase):
    def test_letterbox_bars_and_canvas_edges_are_not_clickable(self):
        self.assertIsNone(canvas_position((100, 360), (1920, 720)))
        self.assertIsNone(canvas_position((1850, 360), (1920, 720)))
        self.assertIsNone(canvas_position((500, 100), (1000, 1000)))
        self.assertIsNone(canvas_position((500, 950), (1000, 1000)))
        self.assertEqual(canvas_position((320, 0), (1920, 720)), (0, 0))
        self.assertEqual(canvas_position((1280, 720), (2560, 1440)), (640, 360))
        self.assertIsNone(canvas_position((1280, 200), (1280, 720)))
        self.assertIsNone(canvas_position((200, 720), (1280, 720)))

    def test_minimized_or_invalid_window_dimensions_do_not_divide_by_zero(self):
        for size in ((0, 0), (0, 720), (1280, 0), (-1, 720)):
            with self.subTest(size=size):
                self.assertIsNone(canvas_position((0, 0), size))


if __name__ == "__main__":
    unittest.main()
