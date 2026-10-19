"""Operator source selection and hotplug policy, independent of the UI."""
from __future__ import annotations

import time

from .cameras import CameraDiscovery, CameraInfo, CameraSession
from .config import save_camera_selection


class CameraSetup:
    def __init__(self, config, config_path=None):
        self.config = config
        self.config_path = config_path
        self.session = CameraSession(config.tracking)
        self.discovery = CameraDiscovery()
        self.selected = None
        self.inventory = self.discovery.snapshot()
        self.snapshot = self.session.snapshot()
        self.notice = ""
        self.enabled = False
        self._generation = -1
        self._missing = False
        self._started = False

    def start(self):
        self.enabled = True
        if not self._started:
            self.discovery.start()
            self._started = True
        self.session.set_preview_enabled(True)
        self.session.start()
        self.discovery.refresh()

    def suspend(self):
        self.enabled = False
        self.session.suspend()

    def stop(self):
        self.discovery.stop()
        self.session.stop()

    def select(self, camera):
        self.selected = camera
        t = self.config.tracking
        t.camera_index, t.camera_backend, t.camera_path = camera.index, camera.backend, camera.path
        self._missing = False
        self.session.select(camera.index, camera.backend, camera.path)
        self.snapshot = self.session.snapshot()
        self.notice = ""

    def manual(self, index):
        index = max(0, min(63, index))
        self.select(CameraInfo(index=index, name=f"Camera {index}", backend=0, path=""))

    def reconnect(self):
        # Restart even if the chosen source is unchanged.
        self.session.suspend()
        t = self.config.tracking
        self.session.select(t.camera_index, t.camera_backend, t.camera_path)
        self.session.start()
        self.discovery.refresh()
        self.notice = "Reconnecting to the selected camera..."

    def cycle(self, direction):
        cameras = self.inventory.cameras
        if not cameras:
            self.manual(self.config.tracking.camera_index+direction)
            return
        index = cameras.index(self.selected) if self.selected in cameras else (-1 if direction > 0 else 0)
        self.select(cameras[(index+direction) % len(cameras)])

    def update(self, now=None):
        """Return True when a hardware change requires returning to setup."""
        changed = False
        old_inventory = self.inventory
        self.inventory = self.discovery.snapshot()
        if self.enabled and self.inventory.generation != self._generation:
            self._generation = self.inventory.generation
            if self.notice == "Refreshing connected webcams...":
                self.notice = ""
            cameras = self.inventory.cameras
            t = self.config.tracking
            if t.camera_path:
                match = next((c for c in cameras if c.path.casefold() == t.camera_path.casefold()
                              and c.backend == t.camera_backend), None)
                if match is None and self.inventory.generation > 0:
                    if not self._missing:
                        self.session.suspend()
                        self.notice = "Selected webcam disconnected. Choose another source or reconnect it."
                        self._missing = True
                        changed = True
                elif match is not None:
                    if self._missing or (match.index, match.backend) != (t.camera_index, t.camera_backend):
                        self.select(match)
                        self.notice = "Camera connection changed. Check the preview before starting."
                        changed = True
                    else:
                        self.selected = match
            elif cameras:
                match = next((c for c in cameras if c.index == t.camera_index
                              and t.camera_backend in (0, c.backend)), None)
                if match is not None:
                    if self.selected is None or match != self.selected:
                        self.select(match)
                        changed = True
                    else:
                        self.selected = match
            old_ids = {c.identity for c in old_inventory.cameras}
            if old_inventory.generation > 0 and any(c.identity not in old_ids for c in cameras) and not changed:
                self.notice = "New webcam detected. Select it from Camera Source to switch."
        self.snapshot = self.session.snapshot()
        if self.notice == "Refreshing connected webcams..." and not self.inventory.scanning:
            self.notice = self.inventory.status
        if self.snapshot.ready and self.notice == "Reconnecting to the selected camera...":
            self.notice = ""
        return changed

    def can_start(self, now=None):
        now = time.monotonic() if now is None else now
        sample = self.snapshot.sample
        return bool(self.enabled and not self._missing and self.snapshot.ready
                    and self.snapshot.preview is not None and sample is not None
                    and 0 <= now-sample.timestamp <= self.config.game.stale_seconds)

    def save(self):
        save_camera_selection(self.config, self.config_path)
