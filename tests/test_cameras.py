"""Discovery/hotplug and source-switch ownership tests without real devices."""

import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from chilli.cameras import CameraDiscovery, CameraInfo, CameraSession, enumerate_connected_cameras
from chilli.tracking import TrackingConfig, TrackingSnapshot


def wait_for(predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Background worker did not reach the expected state")


class EnumerationTests(unittest.TestCase):
    def test_native_enumeration_names_sources_without_opening_any_camera(self):
        cv2 = SimpleNamespace(CAP_DSHOW=700, CAP_MSMF=1400, VideoCapture=Mock())
        enumerate_fn = Mock(side_effect=lambda backend: [
            SimpleNamespace(index=0, name="USB webcam", path="USB/deviceA"),
            SimpleNamespace(index=1, name="Second webcam", path="USB/deviceB"),
        ] if backend == 700 else [
            SimpleNamespace(index=4, name="USB webcam", path="usb/devicea"),
            SimpleNamespace(index=5, name="MF-only camera", path="USB/deviceC"),
        ])
        package = SimpleNamespace(enumerate_cameras=enumerate_fn, supported_backends=(700, 1400))
        with patch.dict(sys.modules, {"cv2": cv2, "cv2_enumerate_cameras": package}), patch("chilli.cameras.sys.platform", "win32"):
            cameras = enumerate_connected_cameras()
        self.assertEqual([(c.index, c.name, c.backend) for c in cameras], [
            (0, "USB webcam", 700), (1, "Second webcam", 700), (5, "MF-only camera", 1400),
        ])
        self.assertEqual(cameras[0].identity, (700, "usb/devicea"))
        cv2.VideoCapture.assert_not_called()

    def test_backend_failure_does_not_hide_other_backend_sources(self):
        cv2 = SimpleNamespace(CAP_DSHOW=700, CAP_MSMF=1400)
        enumerate_fn = Mock(side_effect=[RuntimeError("DSHOW failed"), [SimpleNamespace(index=2, name="Camera", path="device")]])
        package = SimpleNamespace(enumerate_cameras=enumerate_fn, supported_backends=(700, 1400))
        with patch.dict(sys.modules, {"cv2": cv2, "cv2_enumerate_cameras": package}), patch("chilli.cameras.sys.platform", "win32"):
            cameras = enumerate_connected_cameras()
        self.assertEqual(cameras, (CameraInfo(2, "Camera", 1400, "device"),))


class DiscoveryTests(unittest.TestCase):
    def test_periodic_scan_detects_newly_connected_and_removed_sources(self):
        connected = []
        discovery = CameraDiscovery(0.03, enumerate_fn=lambda: tuple(connected))
        discovery.start()
        try:
            wait_for(lambda: discovery.snapshot().generation >= 1)
            self.assertEqual(discovery.snapshot().cameras, ())
            camera = CameraInfo(1, "Added USB camera", 700, "stable-path")
            connected.append(camera)
            wait_for(lambda: discovery.snapshot().cameras == (camera,))
            connected.clear()
            wait_for(lambda: not discovery.snapshot().cameras)
        finally:
            discovery.stop()

    def test_refresh_is_immediate_and_errors_preserve_last_successful_inventory(self):
        camera = CameraInfo(0, "USB camera", 700, "stable-path")
        enumerate_fn = Mock(side_effect=[(camera,), RuntimeError("temporary scan failure")])
        discovery = CameraDiscovery(60, enumerate_fn=enumerate_fn)
        discovery.start()
        try:
            wait_for(lambda: discovery.snapshot().generation == 1)
            discovery.refresh()
            wait_for(lambda: "failed" in discovery.snapshot().status)
            self.assertEqual(discovery.snapshot().cameras, (camera,))
            self.assertEqual(discovery.snapshot().generation, 1)
            self.assertFalse(discovery.snapshot().scanning)
        finally:
            discovery.stop()

    def test_blocked_enumeration_keeps_ui_nonblocking_and_stop_bounded(self):
        entered, release = threading.Event(), threading.Event()
        calls = []

        def blocked_scan():
            calls.append(1)
            entered.set()
            release.wait()
            return ()

        discovery = CameraDiscovery(enumerate_fn=blocked_scan)
        discovery.start()
        self.assertTrue(entered.wait(1))
        try:
            start = time.monotonic()
            for _ in range(10):
                discovery.refresh()
                self.assertTrue(discovery.snapshot().scanning)
            self.assertLess(time.monotonic() - start, 0.1)
            start = time.monotonic()
            discovery.stop()
            self.assertLess(time.monotonic() - start, 0.6)
            self.assertEqual(len(calls), 1)
            self.assertIn("stopped", discovery.snapshot().status)
        finally:
            release.set()
            discovery._thread.join(timeout=1)


class FakeTracker:
    def __init__(self, config):
        self.config = config
        self.started = False
        self.closed = False
        self.hold_close = False
        self.stop_requested = False
        self.preview = False

    @property
    def is_stopped(self):
        return self.closed

    def start(self):
        self.started = True

    def stop(self):
        self.stop_requested = True
        if not self.hold_close:
            self.closed = True

    def set_preview_enabled(self, enabled):
        self.preview = enabled

    def snapshot(self):
        return TrackingSnapshot(ready=True, status=f"source {self.config.camera_index}")


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.created = []

        def factory(config):
            self.assertTrue(all(t.closed for t in self.created), "New tracker opened before old handle was released")
            tracker = FakeTracker(config)
            self.created.append(tracker)
            return tracker

        self.session = CameraSession(TrackingConfig(), tracker_factory=factory)

    def tearDown(self):
        for tracker in self.created:
            tracker.hold_close = False
            if tracker.stop_requested:
                tracker.closed = True
        self.session.stop()

    def test_select_closes_previous_source_and_carries_backend_path_preview(self):
        self.session.set_preview_enabled(True)
        self.session.start()
        wait_for(lambda: len(self.created) == 1)
        self.session.select(3, 700, "usb-stable-path")
        wait_for(lambda: len(self.created) == 2)
        new = self.created[-1]
        self.assertEqual((new.config.camera_index, new.config.camera_backend, new.config.camera_path), (3, 700, "usb-stable-path"))
        self.assertTrue(new.preview)
        wait_for(lambda: self.session.snapshot().ready)
        self.assertEqual(self.session.snapshot().status, "source 3")

    def test_rapid_clicks_while_driver_is_blocked_do_not_accumulate_workers(self):
        self.session.start()
        wait_for(lambda: len(self.created) == 1)
        first = self.created[0]
        first.hold_close = True
        start = time.monotonic()
        self.session.select(1, 700)
        wait_for(lambda: first.stop_requested)
        for index in range(2, 20):
            self.session.select(index, 700)
            self.session.snapshot()
        self.assertLess(time.monotonic() - start, 0.2)
        self.assertEqual(len(self.created), 1)
        self.assertFalse(self.session.snapshot().ready)
        first.closed = True
        wait_for(lambda: len(self.created) == 2)
        self.assertEqual(self.created[-1].config.camera_index, 19)

    def test_suspending_for_demo_releases_camera_and_resume_uses_selected_source(self):
        self.session.select(2, 700, "chosen")
        wait_for(lambda: len(self.created) == 1)
        self.session.suspend()
        wait_for(lambda: self.created[0].closed)
        self.assertFalse(self.session.snapshot().ready)
        self.session.start()
        wait_for(lambda: len(self.created) == 2)
        self.assertEqual(self.created[-1].config.camera_index, 2)
        self.assertEqual(self.created[-1].config.camera_path, "chosen")

    def test_session_stop_is_bounded_with_stuck_old_driver(self):
        self.session.start()
        wait_for(lambda: len(self.created) == 1)
        self.created[0].hold_close = True
        self.session.select(1, 700)
        wait_for(lambda: self.created[0].stop_requested)
        start = time.monotonic()
        self.session.stop()
        self.assertLess(time.monotonic() - start, 0.8)
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.session.snapshot().status, "Camera stopped")
        self.session.start()
        self.assertIn("restart", self.session.snapshot().status)
        self.assertEqual(len(self.created), 1)


if __name__ == "__main__":
    unittest.main()
