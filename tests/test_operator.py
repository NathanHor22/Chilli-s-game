"""Operator preview, source identity and hotplug policy without opening devices."""

from dataclasses import replace
import unittest
from unittest.mock import patch

from chilli.cameras import CameraInfo, DiscoverySnapshot
from chilli.config import Config
from chilli.game import PoseSample
from chilli.operator import CameraSetup
from chilli.tracking import TrackingSnapshot


class FakeSession:
    def __init__(self, config):
        self.config = config
        self.value = TrackingSnapshot()
        self.selections = []
        self.starts = 0
        self.suspends = 0
        self.stops = 0
        self.previews = []

    def snapshot(self):
        return self.value

    def start(self):
        self.starts += 1

    def suspend(self):
        self.suspends += 1
        self.value = TrackingSnapshot(status="Camera paused for demo mode")

    def stop(self):
        self.stops += 1

    def select(self, index, backend=0, camera_path=""):
        self.selections.append((index, backend, camera_path))
        self.value = TrackingSnapshot(status="Switching camera...")

    def set_preview_enabled(self, enabled):
        self.previews.append(enabled)


class FakeDiscovery:
    def __init__(self):
        self.value = DiscoverySnapshot()
        self.starts = 0
        self.refreshes = 0
        self.stops = 0

    def snapshot(self):
        return self.value

    def start(self):
        self.starts += 1

    def refresh(self):
        self.refreshes += 1
        self.value = replace(self.value, scanning=True, status="Looking for cameras...")

    def stop(self):
        self.stops += 1


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.session_patch = patch("chilli.operator.CameraSession", FakeSession)
        self.discovery_patch = patch("chilli.operator.CameraDiscovery", FakeDiscovery)
        self.session_patch.start()
        self.discovery_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.addCleanup(self.discovery_patch.stop)
        self.config = Config()
        self.setup = CameraSetup(self.config)
        self.setup.start()

    def inventory(self, *cameras, generation=1, scanning=False):
        self.setup.discovery.value = DiscoverySnapshot(
            cameras=cameras, generation=generation, scanning=scanning, updated_at=float(generation),
            revision=generation,
        )

    def live_snapshot(self, *, present=True, timestamp=100.0, ready=True, preview=True):
        self.setup.snapshot = TrackingSnapshot(
            sample=PoseSample(timestamp=timestamp, present=present), ready=ready,
            preview=object() if preview else None,
        )
        self.setup.session.value = self.setup.snapshot

    def test_start_enables_preview_and_only_starts_one_discovery_worker(self):
        self.assertTrue(self.setup.enabled)
        self.assertEqual(self.setup.session.previews, [True])
        self.setup.start()
        self.assertEqual(self.setup.discovery.starts, 1)
        self.assertEqual(self.setup.discovery.refreshes, 2)

    def test_can_start_with_live_preview_and_without_person_already_present(self):
        # Entering the game arms its attract screen; a person is not required
        # until the game itself detects somebody to start a round.
        for present in (True, False):
            with self.subTest(present=present):
                self.live_snapshot(present=present)
                self.assertTrue(self.setup.can_start(100.1))

    def test_cannot_start_with_stale_future_missing_or_incomplete_camera_snapshot(self):
        self.live_snapshot(timestamp=100.0 - self.config.game.stale_seconds - 0.01)
        self.assertFalse(self.setup.can_start(100.0))
        self.live_snapshot(timestamp=100.1)
        self.assertFalse(self.setup.can_start(100.0))
        self.live_snapshot(ready=False)
        self.assertFalse(self.setup.can_start(100.0))
        self.live_snapshot(preview=False)
        self.assertFalse(self.setup.can_start(100.0))
        self.setup.snapshot = TrackingSnapshot(ready=True, preview=object())
        self.assertFalse(self.setup.can_start(100.0))
        self.live_snapshot()
        self.setup._missing = True
        self.assertFalse(self.setup.can_start(100.0))

    def test_first_inventory_binds_configured_index_to_named_stable_source(self):
        camera = CameraInfo(0, "USB webcam", 700, "usb-device-A")
        self.inventory(camera)
        self.assertTrue(self.setup.update(100.0))
        self.assertEqual(self.setup.selected, camera)
        self.assertEqual(self.setup.session.selections, [(0, 700, "usb-device-A")])
        self.assertEqual(self.config.tracking.camera_path, "usb-device-A")

    def test_initial_missing_saved_identity_does_not_select_different_camera_at_same_index(self):
        self.config.tracking.camera_path = "saved-camera"
        self.config.tracking.camera_backend = 700
        other = CameraInfo(0, "Different camera", 700, "other-camera")
        self.inventory(other)
        self.assertTrue(self.setup.update(100.0))
        self.assertTrue(self.setup._missing)
        self.assertEqual(self.setup.session.suspends, 1)
        self.assertEqual(self.setup.session.selections, [])
        self.assertIn("disconnected", self.setup.notice)

    def test_manual_index_is_clamped_and_does_not_pick_an_unrelated_inventory_source(self):
        self.setup.manual(100)
        self.assertEqual(self.setup.session.selections[-1], (63, 0, ""))
        self.inventory(CameraInfo(0, "USB webcam", 700, "usb-device-A"))
        self.assertFalse(self.setup.update(100.0))
        self.assertEqual(self.setup.selected.index, 63)
        self.setup.manual(-5)
        self.assertEqual(self.setup.session.selections[-1], (0, 0, ""))

    def test_unplug_then_replug_with_new_index_preserves_device_identity(self):
        original = CameraInfo(0, "Chosen camera", 700, "stable-USB-path")
        self.inventory(original)
        self.setup.update(100.0)
        self.inventory(CameraInfo(0, "Other camera", 700, "different-path"), generation=2)
        self.assertTrue(self.setup.update(101.0))
        self.assertTrue(self.setup._missing)
        self.assertEqual(self.setup.session.suspends, 1)
        self.assertEqual(len(self.setup.session.selections), 1)
        reconnected = CameraInfo(2, "Chosen camera", 700, "stable-USB-path")
        self.inventory(CameraInfo(0, "Other camera", 700, "different-path"), reconnected, generation=3)
        self.assertTrue(self.setup.update(102.0))
        self.assertFalse(self.setup._missing)
        self.assertEqual(self.setup.selected, reconnected)
        self.assertEqual(self.setup.session.selections[-1], (2, 700, "stable-USB-path"))
        self.assertIn("Check the preview", self.setup.notice)

    def test_reindex_detected_without_intermediate_empty_inventory_requires_setup(self):
        original = CameraInfo(0, "Chosen camera", 700, "stable-USB-path")
        self.inventory(original)
        self.setup.update(100.0)
        moved = CameraInfo(3, "Chosen camera", 700, "STABLE-usb-PATH")
        self.inventory(moved, generation=2)
        self.assertTrue(self.setup.update(101.0))
        self.assertEqual(self.setup.session.selections[-1], (3, 700, "STABLE-usb-PATH"))

    def test_same_camera_refresh_does_not_restart_active_session(self):
        camera = CameraInfo(0, "USB webcam", 700, "usb-device-A")
        self.inventory(camera)
        self.setup.update(100.0)
        self.inventory(camera, generation=2)
        self.assertFalse(self.setup.update(101.0))
        self.assertEqual(len(self.setup.session.selections), 1)

    def test_pathless_virtual_camera_refresh_does_not_restart_active_session(self):
        camera = CameraInfo(0, "Virtual camera", 700, "")
        self.inventory(camera)
        self.assertTrue(self.setup.update(100.0))
        self.inventory(camera, generation=2)
        self.assertFalse(self.setup.update(101.0))
        self.assertEqual(len(self.setup.session.selections), 1)

    def test_new_other_camera_is_announced_without_changing_selected_source(self):
        camera = CameraInfo(0, "USB webcam", 700, "usb-device-A")
        self.inventory(camera)
        self.setup.update(100.0)
        self.inventory(camera, CameraInfo(1, "New webcam", 700, "usb-device-B"), generation=2)
        self.assertFalse(self.setup.update(101.0))
        self.assertEqual(self.setup.selected, camera)
        self.assertEqual(len(self.setup.session.selections), 1)
        self.assertIn("New webcam detected", self.setup.notice)

    def test_suspended_demo_session_ignores_hotplug_until_resumed(self):
        camera = CameraInfo(0, "USB webcam", 700, "usb-device-A")
        self.inventory(camera)
        self.setup.update(100.0)
        self.live_snapshot()
        self.setup.suspend()
        self.assertFalse(self.setup.can_start(100.0))
        self.inventory(generation=2)
        self.assertFalse(self.setup.update(101.0))
        self.assertEqual(self.setup.session.suspends, 1)
        self.assertFalse(self.setup._missing)
        self.setup.start()
        self.assertTrue(self.setup.update(102.0))
        self.assertTrue(self.setup._missing)

    def test_camera_backend_is_part_of_identity_when_saved_source_disappears(self):
        camera = CameraInfo(0, "USB webcam", 700, "shared-device-path")
        self.inventory(camera)
        self.setup.update(100.0)
        self.inventory(CameraInfo(0, "USB webcam", 1400, "shared-device-path"), generation=2)
        self.assertTrue(self.setup.update(101.0))
        self.assertTrue(self.setup._missing)
        self.assertEqual(self.setup.session.selections, [(0, 700, "shared-device-path")])

    def test_refresh_exposes_pending_scan_and_reports_failed_attempt_without_generation_change(self):
        camera = CameraInfo(0, "USB webcam", 700, "usb-device-A")
        self.inventory(camera)
        self.setup.update(100.0)
        self.setup.refresh()
        self.assertTrue(self.setup.inventory.scanning)
        self.assertEqual(self.setup.notice, "Refreshing connected webcams...")
        self.setup.update(100.1)
        self.assertEqual(self.setup.notice, "Refreshing connected webcams...")
        self.setup.discovery.value = DiscoverySnapshot(
            cameras=(camera,), generation=1, revision=2, scanning=False,
            error=True, status="Camera scan failed (RuntimeError); refresh to retry",
        )
        self.assertFalse(self.setup.update(100.2))
        self.assertIn("failed", self.setup.notice)
        self.assertEqual(self.setup.selected, camera)
        self.assertEqual(len(self.setup.session.selections), 1)

    def test_refresh_notice_waits_for_queued_followup_scan(self):
        self.inventory(generation=1)
        self.setup.update(100.0)
        self.setup.refresh()
        self.setup.discovery.value = DiscoverySnapshot(generation=2, revision=2, scanning=True,
                                                        status="Looking for cameras...")
        self.setup.update(100.1)
        self.assertEqual(self.setup.notice, "Refreshing connected webcams...")
        self.setup.discovery.value = DiscoverySnapshot(generation=3, revision=3, scanning=False,
                                                        status="No cameras found. Plug in a webcam.")
        self.setup.update(100.2)
        self.assertIn("No cameras found", self.setup.notice)

    def test_empty_inventory_then_first_nonzero_camera_is_selected_automatically(self):
        self.inventory(generation=1)
        self.assertFalse(self.setup.update(100.0))
        camera = CameraInfo(3, "Newly attached webcam", 700, "new-usb-device")
        self.inventory(camera, generation=2)
        self.assertTrue(self.setup.update(101.0))
        self.assertEqual(self.setup.selected, camera)
        self.assertEqual(self.setup.session.selections, [(3, 700, "new-usb-device")])

    def test_new_source_does_not_replace_healthy_manual_camera(self):
        self.setup.manual(0)
        self.live_snapshot(timestamp=100.0)
        self.inventory(CameraInfo(0, "Discovered webcam", 700, "new-path"))
        self.assertFalse(self.setup.update(100.1))
        self.assertEqual(self.setup.session.selections, [(0, 0, "")])
        self.assertEqual(self.setup.selected.backend, 0)

    def test_healthy_unbound_camera_is_not_replaced_by_nonmatching_first_source(self):
        self.live_snapshot(timestamp=100.0)
        self.inventory(CameraInfo(4, "New camera", 700, "new-path"))
        self.assertFalse(self.setup.update(100.1))
        self.assertEqual(self.setup.session.selections, [])

    def test_initial_healthy_default_capture_binds_matching_named_source_once(self):
        self.live_snapshot(timestamp=100.0)
        camera = CameraInfo(0, "Default webcam", 700, "default-stable-path")
        self.inventory(camera)
        self.assertTrue(self.setup.update(100.1))
        self.assertEqual(self.setup.selected, camera)
        self.assertEqual(self.config.tracking.camera_path, "default-stable-path")
        self.assertEqual(self.setup.session.selections, [(0, 700, "default-stable-path")])
        self.live_snapshot(timestamp=101.0)
        self.inventory(camera, generation=2)
        self.assertFalse(self.setup.update(101.1))
        self.assertEqual(len(self.setup.session.selections), 1)

    def test_pathless_source_removal_and_same_index_replacement_require_review(self):
        original = CameraInfo(1, "Chosen virtual camera", 700, "")
        self.inventory(original)
        self.setup.update(100.0)
        self.inventory(CameraInfo(1, "Different virtual camera", 700, ""), generation=2)
        self.assertTrue(self.setup.update(101.0))
        self.assertTrue(self.setup._missing)
        self.assertEqual(self.setup.session.suspends, 1)
        self.assertEqual(self.setup.session.selections, [(1, 700, "")])
        self.inventory(original, generation=3)
        self.assertTrue(self.setup.update(102.0))
        self.assertFalse(self.setup._missing)
        self.assertEqual(self.setup.session.selections[-1], (1, 700, ""))

    def test_suspended_menu_updates_inventory_without_opening_new_camera(self):
        self.setup.suspend()
        camera = CameraInfo(5, "New camera", 700, "new-path")
        self.inventory(camera, generation=1)
        self.assertFalse(self.setup.update(100.0))
        self.assertEqual(self.setup.inventory.cameras, (camera,))
        self.assertEqual(self.setup.session.selections, [])
        self.setup.start()
        self.assertTrue(self.setup.update(100.1))
        self.assertEqual(self.setup.session.selections[-1], (5, 700, "new-path"))


if __name__ == "__main__":
    unittest.main()
