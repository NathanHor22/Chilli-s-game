"""Exercise the actual UI event loop and configuration failures without a webcam."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

from chilli.config import Config, load_config, save_camera_selection


class ConfigTests(unittest.TestCase):
    def config_from(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_config(path)

    def test_invalid_settings_fail_with_actionable_errors(self):
        for data, message in (
            ({"display": {"fullscreen": "false"}}, "display.fullscreen"),
            ({"tracking": {"zone_left": .8, "zone_right": .2}}, "zone"),
            ({"audio": {"volume": 2}}, "volume"),
            ({"display": {"fps": 0}}, "fps"),
            ({"gaem": {}}, "Unknown"),
            ({"game": {"target_motion": 0}}, "target_motion"),
            ({"game": {"instructions_seconds": -1}}, "instructions_seconds"),
        ):
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, message):
                self.config_from(data)

    def test_external_model_is_resolved_relative_to_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pose.task").write_bytes(b"model")
            (root / "custom.json").write_text(json.dumps({"tracking": {"model_path": "pose.task"}}))
            self.assertEqual(Path(load_config(root / "custom.json").tracking.model_path), root / "pose.task")

    def test_missing_explicit_configuration_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            load_config("missing-config-should-not-exist.json")

    def test_save_source_preserves_operator_settings_and_relative_model_path(self):
        config = Config()
        config.tracking.camera_index = 2
        config.tracking.camera_backend = 700
        config.tracking.camera_path = "usb-device-test"
        original = {"display": {"index": 1}, "game": {"target_motion": 4.5},
                    "tracking": {"camera_index": 0, "fps": 10,
                                 "model_path": "models/pose_landmarker_lite.task"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operator.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            save_camera_selection(config, path)
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["display"], original["display"])
        self.assertEqual(saved["game"], original["game"])
        self.assertEqual(saved["tracking"]["model_path"], original["tracking"]["model_path"])
        self.assertEqual(saved["tracking"]["fps"], 10)
        self.assertEqual(saved["tracking"]["camera_index"], 2)
        self.assertEqual(saved["tracking"]["camera_backend"], 700)
        self.assertEqual(saved["tracking"]["camera_path"], "usb-device-test")

    def test_source_save_failure_keeps_previous_config_and_cleans_temporary_file(self):
        config = Config()
        config.tracking.camera_backend = 700
        config.tracking.camera_path = "usb-device-test"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            previous = b'{"tracking": {"camera_index": 1}, "audio": {"volume": 0.2}}\n'
            path.write_bytes(previous)
            with patch("pathlib.Path.replace", side_effect=PermissionError("read-only configuration")):
                with self.assertRaisesRegex(PermissionError, "read-only"):
                    save_camera_selection(config, path)
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


class AppTests(unittest.TestCase):
    def demo_args(self):
        return SimpleNamespace(windowed=True, mute=True, demo=True, config=None,
                               camera=None, display=None, skip_setup=True, setup=False)

    def test_demo_loop_handles_controls_and_quits_cleanly(self):
        import pygame
        from main import play
        config = Config()
        config.display.fullscreen = False
        config.audio.enabled = False
        events = [[pygame.event.Event(pygame.KEYDOWN, key=key)] for key in
                  (pygame.K_RETURN, pygame.K_d, pygame.K_m, pygame.K_r, pygame.K_f, pygame.K_f, pygame.K_ESCAPE)]
        with patch("pygame.event.get", side_effect=events):
            self.assertEqual(play(config, self.demo_args()), 0)
        self.assertFalse(pygame.display.get_init())

    def run_scripted_demo(self, script):
        """Drive the real application loop with key events and a deterministic clock."""
        import pygame
        from main import play
        from chilli.render import Renderer

        class FrameClock:
            frame = 0
            now = 100.0

            def tick(self, fps):
                self.frame += 1
                self.now = 100.0 + self.frame / 30.0
                return 1000.0 / 30.0

            def get_fps(self):
                return 30.0

        clock = FrameClock()
        config = Config()
        config.display.fullscreen = False
        config.audio.enabled = False
        observations = []

        def events():
            if clock.frame > 1800:
                self.fail("Demo did not complete the scripted rounds within 60 simulated seconds")
            return script(clock, observations)

        def observe_draw(renderer, game, now, **kwargs):
            observations.append({"frame": clock.frame, "state": game.state,
                                 "heat": game.heat, "remaining": game.remaining})
            # Rendering is separately checked by --self-test; retain the actual
            # window/event/input/game loop here without drawing 1,000 test frames.
            return renderer.canvas

        with patch("pygame.time.Clock", return_value=clock), \
             patch("main.time.monotonic", side_effect=lambda: clock.now), \
             patch("pygame.event.get", side_effect=events), \
             patch.object(Renderer, "draw", autospec=True, side_effect=observe_draw), \
             patch("chilli.operator.CameraSetup", side_effect=AssertionError("Direct demo constructed camera setup")), \
             patch("chilli.tracking.CameraTracker", side_effect=AssertionError("Demo opened a webcam")):
            self.assertEqual(play(config, self.demo_args()), 0)
        self.assertFalse(pygame.display.get_init())
        return observations

    def test_arrow_key_events_win_and_space_retries_without_camera(self):
        import pygame
        held = None
        retried = False
        wins = 0
        previous_state = None

        def script(clock, observations):
            nonlocal held, retried, wins, previous_state
            events = []
            state = observations[-1]["state"] if observations else "idle"
            if state == "won" and previous_state != "won":
                wins += 1
            previous_state = state
            if wins == 2:
                return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]
            if clock.frame == 1:
                events.append(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            elif clock.frame == 2:
                events.append(pygame.event.Event(pygame.KEYUP, key=pygame.K_RETURN))
            if wins == 1 and not retried:
                events.extend([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE),
                               pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE)])
                retried = True
            if state in ("instructions", "countdown") and clock.frame % 30 == 0:
                # Repeated start attempts must neither skip nor restart either
                # preparation stage, including during the second round.
                events.extend([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN),
                               pygame.event.Event(pygame.KEYUP, key=pygame.K_RETURN)])
            direction = None
            # Practice during preparation must not bank heat or consume the
            # round's timer. Keep sending real key transitions throughout.
            if state in ("instructions", "countdown", "playing"):
                direction = pygame.K_LEFT if (clock.frame // 15) % 2 else pygame.K_RIGHT
            if direction != held:
                if held is not None:
                    events.append(pygame.event.Event(pygame.KEYUP, key=held))
                if direction is not None:
                    events.append(pygame.event.Event(pygame.KEYDOWN, key=direction))
                held = direction
            return events

        observed = self.run_scripted_demo(script)
        self.assertEqual(wins, 2)
        self.assertTrue(retried)
        transitions = [item for i, item in enumerate(observed)
                       if i == 0 or item["state"] != observed[i - 1]["state"]]
        winning = [item for item in transitions if item["state"] == "won"]
        self.assertEqual(len(winning), 2)
        self.assertTrue(all(item["heat"] >= 1 for item in winning))
        starts = [item for item in transitions if item["state"] == "playing"]
        self.assertEqual(len(starts), 2)
        self.assertTrue(all(item["heat"] < .01 for item in starts))
        self.assertEqual([item["state"] for item in transitions],
                         ["instructions", "countdown", "playing", "won"] * 2)
        for item in observed:
            if item["state"] in ("instructions", "countdown"):
                self.assertEqual(item["heat"], 0)
                self.assertEqual(item["remaining"], 10.0)
        for start in starts:
            self.assertEqual(start["remaining"], 10.0)
        for first in (0, 4):
            tutorial, countdown, playing = transitions[first:first + 3]
            tutorial_seconds = (countdown["frame"] - tutorial["frame"]) / 30.0
            countdown_seconds = (playing["frame"] - countdown["frame"]) / 30.0
            self.assertGreaterEqual(tutorial_seconds, 4.0)
            self.assertLessEqual(tutorial_seconds, 4.0 + 1.0 / 30.0 + 1e-8)
            self.assertGreaterEqual(countdown_seconds, 3.0)
            self.assertLessEqual(countdown_seconds, 3.0 + 1.0 / 30.0 + 1e-8)

    def test_demo_start_without_sway_times_out_with_zero_heat(self):
        import pygame

        def script(clock, observations):
            if clock.frame == 1:
                return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)]
            if clock.frame == 2:
                return [pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE)]
            if observations and observations[-1]["state"] == "timeout":
                return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]
            return []

        observed = self.run_scripted_demo(script)
        self.assertIn("playing", [item["state"] for item in observed])
        self.assertIn("timeout", [item["state"] for item in observed])
        self.assertEqual(max(item["heat"] for item in observed), 0)
        transitions = [item for i, item in enumerate(observed)
                       if i == 0 or item["state"] != observed[i - 1]["state"]]
        self.assertEqual([item["state"] for item in transitions],
                         ["instructions", "countdown", "playing", "timeout"])
        playing = transitions[2]
        timeout = transitions[3]
        self.assertEqual(playing["remaining"], 10.0)
        elapsed = (timeout["frame"] - playing["frame"]) / 30.0
        self.assertGreaterEqual(elapsed, 10.0)
        self.assertLessEqual(elapsed, 10.0 + 1.0 / 30.0 + 1e-8)

    def test_startup_source_selection_hotplug_and_switch_to_demo(self):
        """Run UI dispatch and the real selection policy against fake devices."""
        import pygame
        from main import play
        from chilli.cameras import CameraInfo, DiscoverySnapshot
        from chilli.game import PoseSample
        from chilli.render import Renderer
        from chilli.setup_ui import SetupScreen
        from chilli.tracking import TrackingSnapshot

        class FrameClock:
            frame = 0
            now = 100.0

            def tick(self, fps):
                self.frame += 1
                self.now = 100.0 + self.frame / 30.0
                return 1000.0 / 30.0

            def get_fps(self):
                return 30.0

        clock = FrameClock()
        camera0 = CameraInfo(0, "Built-in camera", 700, "built-in-device")
        camera1 = CameraInfo(1, "USB webcam", 700, "usb-device")
        calls = []
        seen = []

        class FakeSession:
            def __init__(self, config):
                self.running = False
                self.preview = False

            def start(self):
                calls.append("start")
                self.running = True

            def stop(self):
                calls.append("stop")
                self.running = False

            def suspend(self):
                calls.append("suspend")
                self.running = False

            def select(self, index, backend, path):
                calls.append(("select", index, backend, path))
                self.running = True

            def set_preview_enabled(self, enabled):
                self.preview = enabled

            def snapshot(self):
                return TrackingSnapshot(sample=PoseSample(clock.now, False), ready=self.running,
                                        preview=object() if self.running and self.preview else None)

        class FakeDiscovery:
            def start(self):
                calls.append("discover")

            def stop(self):
                calls.append("stop discovery")

            def refresh(self):
                calls.append("refresh")

            def snapshot(self):
                # The selected USB webcam disappears after the game is started.
                disconnected = clock.frame >= 4
                return DiscoverySnapshot(cameras=(camera0,) if disconnected else (camera0, camera1),
                                         generation=2 if disconnected else 1)

        event_keys = {2: pygame.K_DOWN, 3: pygame.K_RETURN, 5: pygame.K_k,
                      6: pygame.K_SPACE, 7: pygame.K_ESCAPE}

        def events():
            if clock.frame > 8:
                self.fail("Source selection scenario did not terminate")
            key = event_keys.get(clock.frame)
            return [] if key is None else [pygame.event.Event(pygame.KEYDOWN, key=key)]

        def draw_setup(view, snapshot, discovery, selected, **kwargs):
            seen.append((clock.frame, "setup", kwargs["can_start"]))
            return view.renderer.canvas

        def draw_game(renderer, game, now, **kwargs):
            seen.append((clock.frame, "demo" if kwargs["demo"] else "camera", game.state))
            return renderer.canvas

        config = Config()
        config.display.fullscreen = False
        config.audio.enabled = False
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            args = self.demo_args()
            args.demo = False
            args.config = path
            with patch("pygame.time.Clock", return_value=clock), \
                 patch("main.time.monotonic", side_effect=lambda: clock.now), \
                 patch("pygame.event.get", side_effect=events), \
                 patch("chilli.operator.CameraSession", FakeSession), \
                 patch("chilli.operator.CameraDiscovery", FakeDiscovery), \
                 patch.object(SetupScreen, "draw", autospec=True, side_effect=draw_setup), \
                 patch.object(Renderer, "draw", autospec=True, side_effect=draw_game):
                self.assertEqual(play(config, args), 0)
            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(saved["tracking"]["camera_index"], 1)
        self.assertEqual(saved["tracking"]["camera_path"], "usb-device")
        self.assertIn((1, "setup", True), seen)
        self.assertIn((3, "camera", "idle"), seen)
        self.assertIn((4, "setup", False), seen)
        self.assertIn((5, "demo", "idle"), seen)
        self.assertIn((6, "demo", "instructions"), seen)
        self.assertIn(("select", 1, 700, "usb-device"), calls)
        self.assertGreaterEqual(calls.count("suspend"), 2)
        self.assertEqual(calls.count("stop"), 1)
        self.assertEqual(calls.count("stop discovery"), 1)


if __name__ == "__main__":
    unittest.main()
