"""Exercise the actual UI event loop and configuration failures without a webcam."""
import json
import os
from contextlib import ExitStack
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
    def app_args(self, demo=True, config=None):
        return SimpleNamespace(windowed=True, mute=True, demo=demo, config=config,
                               camera=None, display=None)

    @staticmethod
    def keys(key):
        import pygame
        return [pygame.event.Event(pygame.KEYDOWN, key=key),
                pygame.event.Event(pygame.KEYUP, key=key)]

    @staticmethod
    def mouse(point):
        """Click a canvas point using the actual scaled window coordinates."""
        import pygame
        width, height = pygame.display.get_surface().get_size()
        factor = min(width / 1280, height / 720)
        position = ((width - 1280 * factor) / 2 + point[0] * factor,
                    (height - 720 * factor) / 2 + point[1] * factor)
        return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)]

    def fake_hardware(self, *, cameras=(), ready=False, present=False):
        """Fake only hardware I/O; use the real CameraSetup policy and widgets."""
        import numpy as np
        from chilli.cameras import DiscoverySnapshot
        from chilli.game import PoseSample
        from chilli.tracking import TrackingSnapshot

        device = SimpleNamespace(
            clock=None, cameras=tuple(cameras), ready=ready, present=present,
            generation=1, revision=1, scanning=False, error=False,
            status=f"{len(cameras)} cameras found", pending=None, fail_refresh=False,
            calls=[], sessions=[], frame=np.zeros((24, 32, 3), dtype=np.uint8),
        )

        def call(name, *values):
            device.calls.append((device.clock.frame, name, *values))

        class FakeSession:
            def __init__(self, config):
                self.running = False
                self.preview = False
                device.sessions.append(self)
                call("session_created")

            def start(self):
                self.running = True
                call("start")

            def stop(self):
                self.running = False
                call("stop")

            def suspend(self):
                self.running = False
                call("suspend")

            def select(self, index, backend, path):
                self.running = True
                call("select", index, backend, path)

            def set_preview_enabled(self, enabled):
                self.preview = enabled

            def snapshot(self):
                ready = self.running and device.ready
                return TrackingSnapshot(
                    sample=PoseSample(device.clock.now, device.present) if ready else None,
                    ready=ready, status="Player detected" if ready else "Camera unavailable",
                    preview=device.frame if ready and self.preview else None,
                )

        class FakeDiscovery:
            def __init__(self):
                call("discovery_created")

            def start(self):
                call("discover")

            def stop(self):
                call("stop discovery")

            def refresh(self):
                call("refresh")
                device.scanning = True
                device.pending = device.clock.frame + 1

            def snapshot(self):
                if device.pending is not None and device.clock.frame >= device.pending:
                    device.pending = None
                    device.scanning = False
                    device.revision += 1
                    device.error = device.fail_refresh
                    if device.error:
                        device.status = "Camera scan failed: test failure"
                    else:
                        device.generation += 1
                        device.status = f"{len(device.cameras)} cameras found"
                return DiscoverySnapshot(
                    cameras=device.cameras, scanning=device.scanning, status=device.status,
                    generation=device.generation, revision=device.revision, error=device.error,
                )

        device.Session = FakeSession
        device.Discovery = FakeDiscovery
        return device

    def test_demo_loop_handles_controls_and_quits_cleanly(self):
        import pygame
        controls = {2: pygame.K_RETURN, 3: pygame.K_d, 4: pygame.K_m,
                    5: pygame.K_r, 6: pygame.K_f, 7: pygame.K_f,
                    8: pygame.K_ESCAPE, 10: pygame.K_ESCAPE}

        def script(clock, observed):
            key = controls.get(clock.frame)
            return self.keys(key) if key is not None else []

        observed = self.run_scripted_app(script)
        self.assertEqual(observed[0]["page"], "menu")
        self.assertEqual(observed[1]["state"], "instructions")
        self.assertEqual([item["page"] for item in observed if item["frame"] >= 8], ["menu", "menu"])

    def run_scripted_app(self, script, *, args=None, hardware=None, max_frames=1800,
                         result_capture=None):
        """Drive the real application loop with key events and a deterministic clock."""
        import pygame
        from main import play
        from chilli.render import Renderer
        from chilli.menu_ui import MenuScreen
        from chilli.setup_ui import SetupScreen
        from chilli.records import ResultStore

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
        if hardware is not None:
            hardware.clock = clock
        config = Config()
        config.display.fullscreen = False
        config.audio.enabled = False
        observations = []

        def events():
            if clock.frame > max_frames:
                self.fail("Application did not complete the scripted interaction")
            return script(clock, observations)

        def observe_draw(renderer, game, now, **kwargs):
            observations.append({"frame": clock.frame, "page": "game", "state": game.state,
                                 "heat": game.heat, "remaining": game.remaining,
                                 "message": game.message, "demo": kwargs["demo"],
                                 "best_time": game.best_time, "new_record": game.new_record,
                                 "result_elapsed": game.result_elapsed})
            # Rendering is separately checked by --self-test; retain the actual
            # window/event/input/game loop here without drawing 1,000 test frames.
            return renderer.canvas

        original_setup_draw = SetupScreen.draw

        def observe_menu(view, selected=0, **kwargs):
            observations.append({"frame": clock.frame, "page": "menu", "state": "menu", "selected": selected})
            return view.renderer.canvas

        def observe_setup(view, snapshot, discovery, selected, **kwargs):
            observations.append({"frame": clock.frame, "page": "settings", "state": "settings",
                                 "can_start": kwargs["can_start"], "selected": selected,
                                 "cameras": discovery.cameras, "scanning": discovery.scanning,
                                 "status": discovery.status, "notice": kwargs["notice"]})
            # Keep real setup drawing to exercise its actual source/save targets.
            return original_setup_draw(view, snapshot, discovery, selected, **kwargs)

        with ExitStack() as stack:
            # Exercise the actual persistence code, but never read or write the
            # operator's workspace results, even when the app uses its default
            # record path. One isolated store is created per scripted app run.
            result_directory = stack.enter_context(tempfile.TemporaryDirectory())
            result_path = Path(result_directory) / "results.json"
            result_stores = []

            def create_results(requested_path):
                store = ResultStore(result_path)
                record_win = stack.enter_context(patch.object(store, "record_win", wraps=store.record_win))
                result_stores.append((Path(requested_path), store, record_win))
                return store

            stack.enter_context(patch("chilli.records.ResultStore", side_effect=create_results))
            stack.enter_context(patch("pygame.time.Clock", return_value=clock))
            stack.enter_context(patch("main.time.monotonic", side_effect=lambda: clock.now))
            stack.enter_context(patch("pygame.event.get", side_effect=events))
            stack.enter_context(patch.object(Renderer, "draw", autospec=True, side_effect=observe_draw))
            stack.enter_context(patch.object(MenuScreen, "draw", autospec=True, side_effect=observe_menu))
            stack.enter_context(patch.object(SetupScreen, "draw", autospec=True, side_effect=observe_setup))
            stack.enter_context(patch("chilli.tracking.CameraTracker", side_effect=AssertionError("Test opened a real webcam")))
            if hardware is None:
                stack.enter_context(patch("chilli.operator.CameraSetup", side_effect=AssertionError("Menu/demo constructed camera setup")))
            else:
                stack.enter_context(patch("chilli.operator.CameraSession", hardware.Session))
                stack.enter_context(patch("chilli.operator.CameraDiscovery", hardware.Discovery))
            self.assertEqual(play(config, args or self.app_args()), 0)
            self.assertEqual(len(result_stores), 1)
            if result_capture is not None:
                requested_path, store, record_win = result_stores[0]
                result_capture.update(
                    requested_path=requested_path, entries=dict(store.entries),
                    calls=list(record_win.call_args_list),
                    saved=json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None,
                )
        self.assertFalse(pygame.display.get_init())
        return observations

    def test_idle_menu_never_creates_camera_in_either_mode(self):
        import pygame
        for demo in (False, True):
            with self.subTest(demo=demo):
                def script(clock, observed):
                    return [pygame.event.Event(pygame.QUIT)] if clock.frame == 5 else []
                observed = self.run_scripted_app(script, args=self.app_args(demo=demo))
                self.assertEqual([item["page"] for item in observed], ["menu"] * 4)

    def test_mouse_start_and_quit_route_through_menu(self):
        import pygame
        def script(clock, observed):
            if clock.frame == 2:
                return self.mouse((640, 358))
            if clock.frame == 4:
                return self.keys(pygame.K_ESCAPE)
            if clock.frame == 6:
                return self.mouse((640, 554))
            return []
        observed = self.run_scripted_app(script)
        by_frame = {item["frame"]: item for item in observed}
        self.assertEqual(by_frame[1]["page"], "menu")
        self.assertEqual(by_frame[2]["state"], "instructions")
        self.assertTrue(by_frame[2]["demo"])
        self.assertEqual(by_frame[4]["page"], "menu")

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
                return [pygame.event.Event(pygame.QUIT)]
            if clock.frame == 2:
                events.append(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            elif clock.frame == 3:
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

        observed = self.run_scripted_app(script)
        self.assertEqual(observed[0]["page"], "menu")
        observed = [item for item in observed if item["page"] == "game"]
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
        results = {}

        def script(clock, observations):
            if clock.frame == 2:
                return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)]
            if clock.frame == 3:
                return [pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE)]
            if observations and observations[-1]["state"] == "timeout":
                return [pygame.event.Event(pygame.QUIT)]
            return []

        observed = self.run_scripted_app(script, result_capture=results)
        self.assertEqual(observed[0]["page"], "menu")
        observed = [item for item in observed if item["page"] == "game"]
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
        self.assertEqual(results["calls"], [])
        self.assertEqual(results["entries"], {})
        self.assertIsNone(results["saved"])

    def test_hand_only_keyboard_wave_wins_and_records_best_once(self):
        import pygame
        from chilli.demo import DemoController

        for up, down in ((pygame.K_UP, pygame.K_DOWN), (pygame.K_w, pygame.K_s)):
            with self.subTest(keys=(up, down)):
                held = None
                first_win_frame = None
                samples = []
                results = {}
                original_update = DemoController.update

                def observe_demo(controller, now, dt):
                    sample = original_update(controller, now, dt)
                    samples.append(sample)
                    return sample

                def script(clock, observations):
                    nonlocal held, first_win_frame
                    state = observations[-1]["state"] if observations else "menu"
                    if clock.frame == 2:
                        return self.keys(pygame.K_RETURN)
                    if state == "won":
                        if first_win_frame is None:
                            first_win_frame = clock.frame
                        # Keep displaying the result for several frames: the
                        # app must save only on the transition into won.
                        if clock.frame - first_win_frame >= 15:
                            return [pygame.event.Event(pygame.QUIT)]
                    direction = (up if (clock.frame // 12) % 2 else down) if state == "playing" else None
                    events = []
                    if direction != held:
                        if held is not None:
                            events.append(pygame.event.Event(pygame.KEYUP, key=held))
                        if direction is not None:
                            events.append(pygame.event.Event(pygame.KEYDOWN, key=direction))
                        held = direction
                    return events

                with patch.object(DemoController, "update", autospec=True, side_effect=observe_demo):
                    observed = self.run_scripted_app(script, max_frames=650, result_capture=results)
                playing = [item for item in observed if item["state"] == "playing"]
                winning = [item for item in observed if item["state"] == "won"]
                self.assertTrue(playing)
                self.assertGreater(len(winning), 10)
                self.assertEqual(playing[0]["remaining"], 10.0)
                self.assertTrue(all(sample.x == 0.5 and sample.lean == 0.0 for sample in samples))
                hand_heights = [sample.right_hand[1] for sample in samples]
                self.assertGreater(max(hand_heights) - min(hand_heights), 2.0)
                self.assertEqual(winning[0]["heat"], 1.0)
                self.assertGreater(winning[0]["result_elapsed"], 0)
                self.assertLess(winning[0]["result_elapsed"], 10)
                self.assertTrue(winning[0]["new_record"])
                self.assertEqual(winning[0]["best_time"], winning[0]["result_elapsed"])
                self.assertEqual(len(results["calls"]), 1)
                record_call = results["calls"][0]
                self.assertEqual(record_call.args[0], "demo")
                self.assertAlmostEqual(record_call.args[2], winning[0]["result_elapsed"])
                self.assertEqual(len(results["entries"]), 1)
                self.assertTrue(next(iter(results["entries"])).startswith("hands-v1:demo:"))
                self.assertEqual(results["saved"]["best_times"], results["entries"])

    def test_settings_usb_save_returns_to_menu_then_start_shows_tutorial(self):
        """Click real source/save targets and keep camera policy unmocked."""
        import pygame
        from chilli.cameras import CameraInfo
        camera0 = CameraInfo(0, "Built-in camera", 700, "built-in-device")
        camera1 = CameraInfo(1, "USB webcam", 700, "usb-device")
        device = self.fake_hardware(cameras=(camera0, camera1), ready=True)

        def script(clock, observed):
            actions = {
                2: lambda: self.mouse((640, 456)),   # Menu Settings.
                3: lambda: self.mouse((1014, 236)),  # Second source row.
                4: lambda: self.mouse((1014, 625)),  # Save & Back.
                6: lambda: self.mouse((640, 358)),   # Menu Start.
                9: lambda: self.keys(pygame.K_ESCAPE),
                11: lambda: self.mouse((640, 456)),
                12: lambda: self.mouse((374, 671)),  # Keyboard option in Settings.
                14: lambda: self.keys(pygame.K_RETURN),
                17: lambda: [pygame.event.Event(pygame.QUIT)],
            }
            return actions[clock.frame]() if clock.frame in actions else []

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            results = {}
            observed = self.run_scripted_app(
                script, args=self.app_args(demo=False, config=path), hardware=device, max_frames=20,
                result_capture=results,
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(results["requested_path"], path.parent / "results.json")
        by_frame = {item["frame"]: item for item in observed}
        self.assertEqual(saved["tracking"]["camera_index"], 1)
        self.assertEqual(saved["tracking"]["camera_path"], "usb-device")
        self.assertEqual(by_frame[1]["page"], "menu")
        self.assertEqual(by_frame[2]["page"], "settings")
        self.assertEqual(by_frame[3]["selected"], camera1)
        self.assertEqual(by_frame[4]["page"], "menu")
        self.assertEqual(by_frame[6]["state"], "instructions")
        self.assertFalse(by_frame[6]["demo"])
        self.assertEqual(by_frame[9]["page"], "menu")
        self.assertEqual(by_frame[12]["page"], "menu")
        self.assertEqual(by_frame[14]["state"], "instructions")
        self.assertTrue(by_frame[14]["demo"])
        self.assertIn((3, "select", 1, 700, "usb-device"), device.calls)
        self.assertTrue(all(frame >= 2 for frame, *_ in device.calls))
        self.assertGreaterEqual(sum(call[1] == "suspend" for call in device.calls), 3)
        self.assertEqual(sum(call[1] == "stop" for call in device.calls), 1)
        self.assertEqual(sum(call[1] == "stop discovery" for call in device.calls), 1)

    def test_start_without_camera_waits_on_tutorial_and_keeps_navigation_available(self):
        import pygame
        device = self.fake_hardware()

        def script(clock, observed):
            if clock.frame == 2:
                return self.keys(pygame.K_RETURN)
            if clock.frame == 155:
                return self.keys(pygame.K_c)
            if clock.frame == 157:
                return self.keys(pygame.K_ESCAPE)
            if clock.frame == 159:
                return self.keys(pygame.K_RETURN)
            if clock.frame == 161:
                return self.keys(pygame.K_ESCAPE)
            if clock.frame == 163:
                return self.keys(pygame.K_ESCAPE)
            return []

        observed = self.run_scripted_app(script, args=self.app_args(demo=False), hardware=device, max_frames=165)
        by_frame = {item["frame"]: item for item in observed}
        for item in observed:
            if item["page"] == "game":
                self.assertEqual(item["state"], "instructions")
                self.assertEqual(item["remaining"], 10)
                self.assertEqual(item["heat"], 0)
                self.assertEqual(item["message"], "Connect a camera in Settings")
        self.assertEqual(by_frame[154]["state"], "instructions")
        self.assertEqual(by_frame[155]["page"], "settings")
        self.assertFalse(by_frame[155]["can_start"])
        self.assertEqual(by_frame[157]["page"], "menu")
        self.assertEqual(by_frame[159]["state"], "instructions")
        self.assertEqual(by_frame[161]["page"], "menu")

    def test_settings_refresh_completes_and_hotplug_updates_real_source_rows(self):
        import pygame
        from chilli.cameras import CameraInfo
        camera = CameraInfo(3, "New USB webcam", 700, "new-usb")
        device = self.fake_hardware()

        def script(clock, observed):
            if clock.frame == 2:
                return self.mouse((640, 456))
            if clock.frame == 4:
                device.cameras = (camera,)
                device.ready = True
                return self.keys(pygame.K_F5)
            if clock.frame == 7:
                device.fail_refresh = True
                return self.mouse((1014, 425))
            if clock.frame == 10:
                return [pygame.event.Event(pygame.QUIT)]
            return []

        observed = self.run_scripted_app(script, args=self.app_args(demo=False), hardware=device, max_frames=12)
        by_frame = {item["frame"]: item for item in observed}
        self.assertTrue(by_frame[4]["scanning"])
        self.assertEqual(by_frame[4]["notice"], "Refreshing connected webcams...")
        self.assertFalse(by_frame[5]["scanning"])
        self.assertEqual(by_frame[5]["cameras"], (camera,))
        self.assertNotEqual(by_frame[5]["notice"], "Refreshing connected webcams...")
        self.assertTrue(by_frame[7]["scanning"])
        self.assertFalse(by_frame[8]["scanning"])
        self.assertIn("failed", by_frame[8]["notice"].lower())
        self.assertEqual(by_frame[8]["cameras"], (camera,))

    def test_selected_camera_disconnect_during_countdown_returns_to_settings(self):
        import pygame
        from chilli.cameras import CameraInfo
        camera = CameraInfo(1, "USB webcam", 700, "usb-device")
        device = self.fake_hardware(cameras=(camera,), ready=True, present=True)
        disconnected = False

        def script(clock, observed):
            nonlocal disconnected
            if clock.frame == 2:
                return self.mouse((640, 456))
            if clock.frame == 3:
                return self.mouse((1014, 183))
            if clock.frame == 4:
                return self.keys(pygame.K_RETURN)
            if clock.frame == 6:
                return self.keys(pygame.K_RETURN)
            if observed and observed[-1]["state"] == "countdown" and not disconnected:
                disconnected = True
                device.cameras = ()
                device.ready = False
                device.generation += 1
                device.revision += 1
            elif disconnected and observed and observed[-1]["page"] == "settings":
                return [pygame.event.Event(pygame.QUIT)]
            return []

        with tempfile.TemporaryDirectory() as directory:
            observed = self.run_scripted_app(
                script, args=self.app_args(demo=False, config=Path(directory) / "config.json"),
                hardware=device, max_frames=150,
            )
        self.assertTrue(disconnected)
        self.assertEqual(observed[-1]["page"], "settings")
        self.assertFalse(observed[-1]["can_start"])
        self.assertIn("disconnected", observed[-1]["notice"].lower())
        self.assertIn("instructions", [item["state"] for item in observed])
        self.assertIn("countdown", [item["state"] for item in observed])


if __name__ == "__main__":
    unittest.main()
