"""Geometry and lifecycle checks that need neither a webcam nor MediaPipe."""

import math
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from chilli.game import PoseSample
from chilli.tracking import CameraTracker, TrackingConfig, TrackingSnapshot, _pose_sample


def pose_result():
    points = [SimpleNamespace(x=0.5, y=0.3, visibility=0.99, presence=0.99) for _ in range(33)]
    points[11].x, points[11].y = 0.3, 0.3
    points[12].x, points[12].y = 0.7, 0.3
    points[23].x, points[23].y = 0.4, 0.65
    points[24].x, points[24].y = 0.6, 0.65
    return SimpleNamespace(pose_landmarks=[points])


class PoseGeometryTests(unittest.TestCase):
    def sample(self, result, **kwargs):
        config = TrackingConfig(**kwargs)
        return _pose_sample(result, 123.456, config, 640, 480, 96, 448)

    def test_crop_geometry_returns_full_frame_coordinates_and_capture_time(self):
        result = pose_result()
        sample, landmarks, _ = self.sample(result)
        self.assertTrue(sample.present)
        self.assertEqual(sample.timestamp, 123.456)
        self.assertAlmostEqual(sample.x, 0.5)
        self.assertAlmostEqual(sample.scale, 0.28)
        self.assertAlmostEqual(sample.lean, 0.0)
        self.assertEqual(len(landmarks), 33)
        self.assertAlmostEqual(landmarks[11][0], 0.36)

    def test_sideways_torso_lean_is_normalized_by_shoulders(self):
        result = pose_result()
        result.pose_landmarks[0][11].x += 0.1
        result.pose_landmarks[0][12].x += 0.1
        sample, _, _ = self.sample(result)
        self.assertTrue(sample.present)
        self.assertAlmostEqual(sample.x, 0.57)
        self.assertAlmostEqual(sample.lean, 0.25)

    def test_shoulder_scale_accounts_for_aspect_ratio(self):
        result = pose_result()
        result.pose_landmarks[0][12].y = 0.4
        sample, _, _ = self.sample(result)
        self.assertTrue(sample.present)
        self.assertAlmostEqual(sample.scale, math.hypot(0.28, 0.075))

    def test_missing_pose_is_explicitly_absent(self):
        sample, landmarks, _ = self.sample(SimpleNamespace(pose_landmarks=[]))
        self.assertFalse(sample.present)
        self.assertEqual(landmarks, ())

    def test_uncertain_hips_do_not_create_a_player(self):
        for field, value in (("visibility", 0.2), ("presence", 0.2), ("x", float("nan"))):
            with self.subTest(field=field):
                result = pose_result()
                setattr(result.pose_landmarks[0][23], field, value)
                sample, landmarks, _ = self.sample(result)
                self.assertFalse(sample.present)
                self.assertEqual(landmarks[23], (-1.0, -1.0))

    def test_outside_crop_or_too_distant_body_is_rejected(self):
        result = pose_result()
        result.pose_landmarks[0][11].x = -0.1
        sample, _, _ = self.sample(result)
        self.assertFalse(sample.present)
        result = pose_result()
        result.pose_landmarks[0][11].x = 0.49
        result.pose_landmarks[0][12].x = 0.51
        sample, _, status = self.sample(result)
        self.assertFalse(sample.present)
        self.assertIn("closer", status)

    def test_invalid_torso_geometry_is_rejected(self):
        result = pose_result()
        for index in (23, 24):
            result.pose_landmarks[0][index].y = 0.2
        sample, _, _ = self.sample(result)
        self.assertFalse(sample.present)


class TrackerLifecycleTests(unittest.TestCase):
    def test_missing_model_is_reported_without_loading_camera_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            tracker = CameraTracker(TrackingConfig(model_path=str(Path(directory) / "missing.task")))
            tracker.start()
            tracker._thread.join(timeout=1.0)
            snapshot = tracker.snapshot()
            self.assertFalse(snapshot.ready)
            self.assertIn("model missing", snapshot.status)
            tracker.stop()

    def test_preview_can_be_removed_without_mutating_old_snapshot(self):
        tracker = CameraTracker()
        original = TrackingSnapshot(ready=True, preview=object(), landmarks=((0.5, 0.5),))
        tracker._publish(original)
        tracker.set_preview_enabled(False)
        self.assertIsNone(tracker.snapshot().preview)
        self.assertEqual(tracker.snapshot().landmarks, ())
        self.assertIsNotNone(original.preview)

    def test_windows_camera_fallback_releases_failed_backend(self):
        attempts = []

        class FakeCamera:
            def __init__(self, index, backend):
                self.backend = backend
                self.released = False
                attempts.append(self)

            def isOpened(self):
                return self.backend == 0

            def set(self, *args):
                return True

            def release(self):
                self.released = True

        cv2 = SimpleNamespace(
            VideoCapture=FakeCamera, CAP_DSHOW=700, CAP_ANY=0,
            CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4,
            CAP_PROP_FPS=5, CAP_PROP_BUFFERSIZE=38,
        )
        with patch("chilli.tracking.sys.platform", "win32"):
            camera = CameraTracker()._open_camera(cv2)
        self.assertEqual(len(attempts), 2)
        self.assertTrue(attempts[0].released)
        self.assertIs(camera, attempts[1])

    def test_invalid_configuration_fails_early(self):
        for config in ({"fps": 0}, {"fps": float("nan")}, {"zone_left": 0.9}, {"confidence": 2}, {"width": 0}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                TrackingConfig(**config)

    def test_explicit_backend_never_falls_back_to_a_different_device_list(self):
        camera = Mock()
        camera.isOpened.return_value = False
        cv2 = SimpleNamespace(CAP_DSHOW=700, CAP_ANY=0, VideoCapture=Mock(return_value=camera))
        tracker = CameraTracker(TrackingConfig(camera_index=2, camera_backend=1400))
        self.assertIsNone(tracker._open_camera(cv2))
        cv2.VideoCapture.assert_called_once_with(2, 1400)
        camera.release.assert_called_once()

    def test_stable_device_path_prevents_reopening_a_reassigned_index(self):
        from chilli.cameras import CameraInfo
        cv2 = SimpleNamespace(VideoCapture=Mock())
        tracker = CameraTracker(TrackingConfig(camera_index=0, camera_backend=700, camera_path="original"))
        with patch("chilli.cameras.enumerate_connected_cameras", return_value=(
            CameraInfo(0, "Different webcam", 700, "different"), CameraInfo(1, "Original webcam", 700, "original"),
        )):
            self.assertIsNone(tracker._open_camera(cv2))
        self.assertIn("index changed", tracker._source_problem)
        cv2.VideoCapture.assert_not_called()

    def test_missing_selected_device_does_not_open_another_camera(self):
        from chilli.cameras import CameraInfo
        cv2 = SimpleNamespace(VideoCapture=Mock())
        tracker = CameraTracker(TrackingConfig(camera_index=0, camera_backend=700, camera_path="original"))
        with patch("chilli.cameras.enumerate_connected_cameras", return_value=(CameraInfo(0, "Other camera", 700, "other"),)):
            self.assertIsNone(tracker._open_camera(cv2))
        self.assertIn("disconnected", tracker._source_problem)
        cv2.VideoCapture.assert_not_called()

    def test_stale_camera_snapshot_is_absent_with_diagnostic(self):
        tracker = CameraTracker()
        tracker._latest_frame = (1, 90.0, object())
        previous = TrackingSnapshot(sample=PoseSample(timestamp=90.0, present=True), ready=True, preview=object())
        tracker._publish(previous)
        with patch("chilli.tracking.time.monotonic", return_value=100.0):
            snapshot = tracker.snapshot()
        self.assertFalse(snapshot.ready)
        self.assertFalse(snapshot.sample.present)
        self.assertEqual(snapshot.sample.timestamp, 100.0)
        self.assertIn("Camera not responding", snapshot.status)
        self.assertIsNone(snapshot.preview)
        self.assertEqual(snapshot.fps, 0)
        self.assertIs(tracker._snapshot, previous)

    def test_stale_result_with_fresh_camera_reports_inference_stall(self):
        tracker = CameraTracker()
        tracker._latest_frame = (10, 99.9, object())
        tracker._publish(TrackingSnapshot(sample=PoseSample(timestamp=90.0, present=True), ready=True))
        with patch("chilli.tracking.time.monotonic", return_value=100.0):
            snapshot = tracker.snapshot()
        self.assertFalse(snapshot.ready)
        self.assertFalse(snapshot.sample.present)
        self.assertIn("Body tracking not responding", snapshot.status)

    def test_blocked_first_native_calls_are_reported_before_any_result(self):
        for field, expected_status in (
            ("_capture_call_started", "Camera not responding"),
            ("_inference_call_started", "Body tracking not responding"),
        ):
            with self.subTest(field=field):
                tracker = CameraTracker()
                setattr(tracker, field, 90.0)
                with patch("chilli.tracking.time.monotonic", return_value=100.0):
                    snapshot = tracker.snapshot()
                self.assertFalse(snapshot.ready)
                self.assertFalse(snapshot.sample.present)
                self.assertIn(expected_status, snapshot.status)

    def test_watchdog_recovers_on_fresh_sample(self):
        tracker = CameraTracker()
        tracker._latest_frame = (1, 90.0, object())
        tracker._publish(TrackingSnapshot(sample=PoseSample(timestamp=90.0, present=True), ready=True))
        with patch("chilli.tracking.time.monotonic", return_value=100.0):
            self.assertFalse(tracker.snapshot().ready)
            fresh = TrackingSnapshot(sample=PoseSample(timestamp=99.9, present=True), ready=True)
            tracker._latest_frame = (2, 99.9, object())
            tracker._publish(fresh)
            self.assertIs(tracker.snapshot(), fresh)

    def test_retry_status_is_not_overwritten_by_watchdog(self):
        tracker = CameraTracker()
        tracker._publish(TrackingSnapshot(status="Camera unavailable; retrying..."))
        with patch("chilli.tracking.time.monotonic", return_value=100.0):
            self.assertIn("retrying", tracker.snapshot().status)

    def test_stop_is_bounded_when_both_native_workers_are_blocked(self):
        tracker = CameraTracker()
        release_workers = threading.Event()
        tracker._thread = threading.Thread(target=release_workers.wait, daemon=True)
        tracker._camera_thread = threading.Thread(target=release_workers.wait, daemon=True)
        tracker._thread.start()
        tracker._camera_thread.start()
        try:
            started = time.monotonic()
            tracker.stop()
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 1.2)
            self.assertTrue(tracker._thread.is_alive())
            self.assertTrue(tracker._camera_thread.is_alive())
            self.assertEqual(tracker.snapshot().status, "Camera stopped")
            # A late read error must not replace the final stopped state.
            tracker._camera_problem("Camera signal lost; reconnecting...")
            self.assertEqual(tracker.snapshot().status, "Camera stopped")
        finally:
            release_workers.set()
            tracker._thread.join(timeout=1)
            tracker._camera_thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
