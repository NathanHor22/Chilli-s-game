"""Asynchronous camera discovery and serialized source switching.

Windows discovery uses cv2-enumerate-cameras' device metadata APIs, never
VideoCapture probes. Both its DirectShow and Media Foundation calls release the
GIL while enumerating, and they do not start a video stream. Camera identities
include their device path: callers should not treat a USB index as permanent.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import sys
import threading
import time
from typing import Callable

from .tracking import CameraTracker, TrackingConfig, TrackingSnapshot


@dataclass(frozen=True)
class CameraInfo:
    index: int
    name: str
    backend: int
    path: str = ""

    @property
    def identity(self) -> tuple[int, str | int]:
        return self.backend, self.path.casefold() if self.path else self.index


@dataclass(frozen=True)
class DiscoverySnapshot:
    cameras: tuple[CameraInfo, ...] = ()
    scanning: bool = False
    status: str = "Camera scan has not started"
    # Successful scan number; errors preserve the last successful inventory.
    generation: int = 0
    updated_at: float = 0.0


def enumerate_connected_cameras() -> tuple[CameraInfo, ...]:
    """Read native camera names/indices; do not open devices to test them.

    Explicit backends retain plain camera indices. CAP_ANY's encoded indices
    are deliberately avoided. DirectShow is preferred when both Windows APIs
    report the exact same device path; distinct/unknown paths remain separate.
    """
    import cv2
    from cv2_enumerate_cameras import enumerate_cameras, supported_backends

    if sys.platform == "win32":
        backends = (cv2.CAP_DSHOW, cv2.CAP_MSMF)
    elif sys.platform == "darwin":
        backends = (cv2.CAP_AVFOUNDATION,)
    elif sys.platform.startswith("linux"):
        backends = (cv2.CAP_V4L2,)
    else:
        raise RuntimeError("Named camera discovery is not supported on this operating system")
    found: list[CameraInfo] = []
    paths: set[str] = set()
    indices: set[tuple[int, int]] = set()
    errors: list[Exception] = []
    successful_backends = 0
    for backend in backends:
        if backend not in supported_backends:
            continue
        try:
            sources = enumerate_cameras(backend)
            successful_backends += 1
            for source in sources:
                index = int(source.index)
                path = str(source.path or "")
                name = str(source.name or f"Camera {index}").strip()
                canonical_path = path.casefold().removeprefix("@device:pnp:")
                if (backend, index) in indices or canonical_path and canonical_path in paths:
                    continue
                found.append(CameraInfo(index, name or f"Camera {index}", backend, path))
                indices.add((backend, index))
                if canonical_path:
                    paths.add(canonical_path)
        except Exception as exc:
            errors.append(exc)
    if not successful_backends:
        if errors:
            raise RuntimeError(f"Camera enumeration failed: {type(errors[0]).__name__}: {errors[0]}") from errors[0]
        raise RuntimeError("No supported native camera enumeration backend")
    return tuple(found)


class CameraDiscovery:
    """One daemon scans periodically; UI reads and refresh requests never wait."""

    def __init__(self, refresh_seconds: float = 4.0, *, enumerate_fn: Callable[[], tuple[CameraInfo, ...]] | None = None) -> None:
        if not math.isfinite(refresh_seconds) or refresh_seconds <= 0:
            raise ValueError("refresh_seconds must be positive")
        self.refresh_seconds = refresh_seconds
        self._enumerate = enumerate_fn or enumerate_connected_cameras
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot = DiscoverySnapshot()
        self._scan_started: float | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._wake_event.clear()
        with self._lock:
            self._snapshot = replace(self._snapshot, scanning=True, status="Looking for cameras...")
        self._thread = threading.Thread(target=self._run, name="chilli-camera-discovery", daemon=True)
        self._thread.start()

    def refresh(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self.start()
        else:
            self._wake_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=0.2)
        with self._lock:
            self._snapshot = replace(self._snapshot, scanning=False, status="Camera scan stopped")

    def snapshot(self) -> DiscoverySnapshot:
        with self._lock:
            snapshot = self._snapshot
            if snapshot.scanning and self._scan_started is not None and time.monotonic() - self._scan_started > 8.0:
                return replace(snapshot, status="Camera scan is taking longer than usual; check connected devices")
            return snapshot

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._wake_event.clear()
            with self._lock:
                self._scan_started = time.monotonic()
                self._snapshot = replace(self._snapshot, scanning=True, status="Looking for cameras...")
            try:
                cameras = tuple(self._enumerate())
                with self._lock:
                    if self._stop_event.is_set():
                        return
                    count = len(cameras)
                    self._snapshot = DiscoverySnapshot(
                        cameras=cameras, status=f"{count} camera{'s' if count != 1 else ''} found" if count else "No cameras found. Plug in a webcam.",
                        generation=self._snapshot.generation + 1, updated_at=time.monotonic(),
                    )
            except (ImportError, OSError) as exc:
                with self._lock:
                    if self._stop_event.is_set():
                        return
                    self._snapshot = replace(self._snapshot, scanning=False,
                                             status=f"Camera discovery unavailable ({type(exc).__name__}); run setup.ps1")
            except Exception as exc:
                with self._lock:
                    if self._stop_event.is_set():
                        return
                    self._snapshot = replace(self._snapshot, scanning=False,
                                             status=f"Camera scan failed ({type(exc).__name__}); refresh to retry")
            finally:
                with self._lock:
                    self._scan_started = None
            self._wake_event.wait(self.refresh_seconds)


class CameraSession:
    """Single-owner supervisor for nonblocking preview/source changes.

    A new tracker starts only when the preceding tracker's capture AND inference
    workers have ended. A broken driver can therefore block switching safely,
    but repeated clicks never accumulate camera handles or detector workers.
    ``suspend`` releases the camera for demo mode; ``start`` resumes the chosen
    source. ``select`` also resumes and accepts the stable device path.
    """

    def __init__(self, config: TrackingConfig | None = None, *, tracker_factory: Callable[[TrackingConfig], CameraTracker] | None = None) -> None:
        self.config = replace(config or TrackingConfig())
        self._factory = tracker_factory or CameraTracker
        self._lock = threading.Lock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._tracker: CameraTracker | None = None
        self._desired: TrackingConfig | None = None
        self._revision = 0
        self._active_revision = -1
        self._preview_enabled = False
        self._control_snapshot: TrackingSnapshot | None = TrackingSnapshot(status="Camera has not started")

    def _ensure_thread(self) -> None:
        # Public methods call this after releasing _lock. Only the UI calls
        # start/select/suspend/stop, while the supervisor owns native resources.
        if self._thread is not None and self._thread.is_alive():
            self._wake_event.set()
            return
        if self._stop_event.is_set() and self._tracker is not None and not self._tracker.is_stopped:
            with self._lock:
                self._control_snapshot = TrackingSnapshot(status="Previous camera has not closed; restart the game")
            return
        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(target=self._run, name="chilli-camera-session", daemon=True)
        self._thread.start()

    def start(self) -> None:
        with self._lock:
            if self._desired is None:
                self._desired = replace(self.config)
                self._revision += 1
                self._control_snapshot = TrackingSnapshot(status="Starting selected camera...")
        self._ensure_thread()

    def select(self, camera_index: int, backend: int = 0, camera_path: str = "") -> None:
        config = replace(self.config, camera_index=camera_index, camera_backend=backend, camera_path=camera_path)
        with self._lock:
            self.config = config
            self._desired = replace(config)
            self._revision += 1
            self._control_snapshot = TrackingSnapshot(status="Switching camera...")
        self._ensure_thread()

    def suspend(self) -> None:
        with self._lock:
            self._desired = None
            self._revision += 1
            self._control_snapshot = TrackingSnapshot(status="Camera paused for demo mode")
        self._wake_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=0.6)
        with self._lock:
            self._desired = None
            self._revision += 1
            self._control_snapshot = TrackingSnapshot(status="Camera stopped")

    def set_preview_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._preview_enabled = bool(enabled)
            tracker = self._tracker
        if tracker is not None:
            tracker.set_preview_enabled(enabled)

    def snapshot(self) -> TrackingSnapshot:
        with self._lock:
            control, tracker = self._control_snapshot, self._tracker
        if control is not None:
            return control
        return tracker.snapshot() if tracker is not None else TrackingSnapshot(status="Starting selected camera...")

    def _run(self) -> None:
        tracker: CameraTracker | None = None
        try:
            while not self._stop_event.is_set():
                self._wake_event.clear()
                with self._lock:
                    desired, revision = self._desired, self._revision
                    active_revision = self._active_revision
                    tracker = self._tracker
                if tracker is not None and revision != active_revision:
                    tracker.stop()
                    waiting_since = time.monotonic()
                    while not tracker.is_stopped and not self._stop_event.is_set():
                        with self._lock:
                            status = ("Previous camera is not closing; restart the game" if time.monotonic() - waiting_since >= 3.0
                                      else "Waiting for previous camera to close...")
                            self._control_snapshot = TrackingSnapshot(status=status)
                        self._wake_event.wait(0.05)
                        self._wake_event.clear()
                    if self._stop_event.is_set():
                        break
                    with self._lock:
                        self._tracker = None
                    tracker = None
                if self._stop_event.is_set():
                    break
                with self._lock:
                    desired, revision = self._desired, self._revision
                    preview_enabled = self._preview_enabled
                if desired is None:
                    with self._lock:
                        self._control_snapshot = TrackingSnapshot(status="Camera paused for demo mode")
                elif tracker is None:
                    tracker = self._factory(replace(desired))
                    tracker.set_preview_enabled(preview_enabled)
                    tracker.start()
                    with self._lock:
                        self._tracker = tracker
                        self._active_revision = revision
                        tracker.set_preview_enabled(self._preview_enabled)
                        if revision == self._revision:
                            self._control_snapshot = None
                self._wake_event.wait(0.1)
        except Exception as exc:
            with self._lock:
                self._control_snapshot = TrackingSnapshot(status=f"Camera switch failed ({type(exc).__name__}); restart the game")
        finally:
            if tracker is not None:
                tracker.stop()
