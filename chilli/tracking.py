"""Latest-frame camera tracking, kept entirely off the game/render thread.

Importing this module does not import OpenCV, NumPy, or MediaPipe. The game can
therefore run its keyboard demo without a camera or the tracking dependencies.
Frames stay in memory and are never recorded. A single pose is not an identity
lock: camera placement and the marked play zone still matter in a busy room.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sys
import threading
import time
from typing import Any

from chilli.game import PoseSample


@dataclass
class TrackingConfig:
    camera_index: int = 0
    camera_backend: int = 0
    camera_path: str = ""
    width: int = 640
    height: int = 480
    fps: float = 15.0
    model_path: str = "models/pose_landmarker_lite.task"
    mirror: bool = True
    zone_left: float = 0.15
    zone_right: float = 0.85
    min_shoulder_width: float = 0.09
    confidence: float = 0.55
    retry_seconds: float = 3.0

    def __post_init__(self) -> None:
        if self.camera_index < 0:
            raise ValueError("camera_index must be nonnegative")
        if self.camera_backend < 0:
            raise ValueError("camera_backend must be nonnegative")
        if not isinstance(self.camera_path, str):
            raise ValueError("camera_path must be text")
        if self.width < 64 or self.height < 64:
            raise ValueError("camera width and height must be at least 64")
        if not math.isfinite(self.fps) or not 1.0 <= self.fps <= 60.0:
            raise ValueError("tracking fps must be between 1 and 60")
        if not 0.0 <= self.zone_left < self.zone_right <= 1.0:
            raise ValueError("play zone must satisfy 0 <= left < right <= 1")
        if self.zone_right - self.zone_left < 0.2:
            raise ValueError("play zone must cover at least 20% of the camera")
        if not 0.0 < self.min_shoulder_width < 1.0:
            raise ValueError("min_shoulder_width must be between 0 and 1")
        if not 0.0 < self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not math.isfinite(self.retry_seconds) or self.retry_seconds < 0.1:
            raise ValueError("retry_seconds must be at least 0.1")


@dataclass(frozen=True)
class TrackingSnapshot:
    sample: PoseSample | None = None
    ready: bool = False
    status: str = "Camera has not started"
    fps: float = 0.0
    # A read-only RGB uint8 array. This is created only when preview is enabled.
    preview: Any = None
    # MediaPipe's 33 landmark indices, normalized to the full mirrored frame.
    # Low-confidence/out-of-frame landmarks have coordinates (-1.0, -1.0).
    landmarks: tuple[tuple[float, float], ...] = ()


def _pose_sample(
    result: Any,
    timestamp: float,
    config: TrackingConfig,
    frame_width: int,
    frame_height: int,
    crop_left: int,
    crop_width: int,
) -> tuple[PoseSample, tuple[tuple[float, float], ...], str]:
    """Convert one model result into geometry with no third-party imports."""
    absent = PoseSample(timestamp=timestamp, present=False)
    poses = getattr(result, "pose_landmarks", ())
    if not poses or len(poses[0]) < 33:
        return absent, (), "Step into the marked area"
    pose = poses[0]

    def reliable(point: Any) -> bool:
        try:
            values = (point.x, point.y, point.visibility, point.presence)
            return (
                all(value is not None and math.isfinite(value) for value in values)
                and point.visibility >= config.confidence
                and point.presence >= config.confidence
                and 0.0 <= point.x <= 1.0
                and 0.0 <= point.y <= 1.0
            )
        except (AttributeError, TypeError):
            return False

    def global_xy(point: Any) -> tuple[float, float]:
        return ((crop_left + point.x * crop_width) / frame_width, point.y)

    landmarks = tuple(global_xy(point) if reliable(point) else (-1.0, -1.0) for point in pose)
    if not all(reliable(pose[index]) for index in (11, 12, 23, 24)):
        return absent, landmarks, "Keep your shoulders and hips in view"

    left_shoulder, right_shoulder = landmarks[11], landmarks[12]
    left_hip, right_hip = landmarks[23], landmarks[24]
    shoulder_x = (left_shoulder[0] + right_shoulder[0]) / 2.0
    shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2.0
    hip_x = (left_hip[0] + right_hip[0]) / 2.0
    hip_y = (left_hip[1] + right_hip[1]) / 2.0
    # Convert vertical distance to image-width units as well. This preserves
    # shoulder scale during leaning instead of treating rotation as approach.
    shoulder_span = math.hypot(
        left_shoulder[0] - right_shoulder[0],
        (left_shoulder[1] - right_shoulder[1]) * frame_height / frame_width,
    )
    if not config.zone_left <= shoulder_x <= config.zone_right:
        return absent, landmarks, "Move into the centre of the play area"
    if shoulder_span < config.min_shoulder_width:
        return absent, landmarks, "Move a little closer to the camera"
    if hip_y <= shoulder_y or hip_y - shoulder_y < 0.04:
        return absent, landmarks, "Stand facing the camera with your torso in view"
    lean = (shoulder_x - hip_x) / shoulder_span
    if abs(lean) > 2.0:
        return absent, landmarks, "Keep your shoulders and hips in view"
    return (
        PoseSample(timestamp=timestamp, present=True, x=shoulder_x, scale=shoulder_span, lean=lean),
        landmarks,
        "Player detected",
    )


class CameraTracker:
    """Nonblocking UI API around a single CPU pose detector and USB camera.

    ``start`` returns immediately. ``snapshot`` is safe on the render thread.
    ``stop`` waits at most 0.5 seconds; daemon workers prevent a stuck camera
    driver from hanging application exit. Camera resources are released by the
    capture worker itself, never while another thread is using VideoCapture.
    """

    # A driver/native call can block without raising. The render thread must
    # still invalidate its last good sample and explain what stopped responding.
    # This is a fault-display timeout; normal scoring uses the engine's shorter
    # stale-sample limit independently.
    _WATCHDOG_SECONDS = 3.0

    def __init__(self, config: TrackingConfig | None = None) -> None:
        self.config = config or TrackingConfig()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._frame_event = threading.Event()
        self._snapshot = TrackingSnapshot()
        self._thread: threading.Thread | None = None
        self._camera_thread: threading.Thread | None = None
        self._preview_enabled = False
        self._latest_frame: tuple[int, float, Any] | None = None
        self._sequence = 0
        self._camera_generation = 0
        self._camera_status = "Opening camera"
        self._capture_call_started: float | None = None
        self._inference_call_started: float | None = None
        self._source_problem = ""

    @property
    def is_stopped(self) -> bool:
        """True only after both native-resource-owning workers have finished."""
        return all(worker is None or not worker.is_alive() for worker in (self._thread, self._camera_thread))

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if self._camera_thread is not None and self._camera_thread.is_alive():
            # A blocked driver from a previous run must not share a new Event.
            self._publish(TrackingSnapshot(status="Camera driver is still stopping; restart the application"))
            return
        self._stop_event.clear()
        self._frame_event.clear()
        with self._lock:
            self._latest_frame = None
            self._capture_call_started = None
            self._inference_call_started = None
            self._snapshot = TrackingSnapshot(status="Loading body tracker")
        self._thread = threading.Thread(target=self._run, name="chilli-pose", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._frame_event.set()
        deadline = time.monotonic() + 0.5
        for worker in (self._thread, self._camera_thread):
            if worker is not None and worker is not threading.current_thread():
                worker.join(timeout=max(0.0, deadline - time.monotonic()))
        self._publish(TrackingSnapshot(status="Camera stopped"))

    def snapshot(self) -> TrackingSnapshot:
        with self._lock:
            snapshot = self._snapshot
            if self._stop_event.is_set():
                return snapshot
            now = time.monotonic()
            capture_stalled = (
                self._capture_call_started is not None
                and now - self._capture_call_started >= self._WATCHDOG_SECONDS
            )
            inference_stalled = (
                self._inference_call_started is not None
                and now - self._inference_call_started >= self._WATCHDOG_SECONDS
            )
            result_stale = (
                snapshot.ready and snapshot.sample is not None
                and now - snapshot.sample.timestamp >= self._WATCHDOG_SECONDS
            )
            if result_stale and not capture_stalled:
                latest_capture = self._latest_frame[1] if self._latest_frame else None
                capture_stalled = latest_capture is None or now - latest_capture >= self._WATCHDOG_SECONDS
                inference_stalled = not capture_stalled
            if capture_stalled or inference_stalled:
                status = (
                    "Camera not responding; check USB connection or restart the game"
                    if capture_stalled else
                    "Body tracking not responding; lower tracking settings or restart the game"
                )
                # Never touch the native camera/detector from this thread.
                # Return a synthetic absent sample; if the worker recovers, its
                # next fresh snapshot immediately restores normal operation.
                return TrackingSnapshot(sample=PoseSample(timestamp=now, present=False), status=status)
            return snapshot

    def set_preview_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._preview_enabled = bool(enabled)
            if not enabled and self._snapshot.preview is not None:
                old = self._snapshot
                self._snapshot = TrackingSnapshot(old.sample, old.ready, old.status, old.fps)

    def _publish(self, snapshot: TrackingSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def _camera_problem(self, message: str) -> None:
        with self._lock:
            if self._stop_event.is_set():
                return
            self._latest_frame = None
            self._capture_call_started = None
            self._camera_status = message
            self._snapshot = TrackingSnapshot(
                sample=PoseSample(timestamp=time.monotonic(), present=False),
                status=message,
            )
        self._frame_event.set()

    def _open_camera(self, cv2: Any) -> Any:
        self._source_problem = ""
        if self.config.camera_path:
            # Never silently reuse a stale USB index for another camera after
            # unplug/replug. Enumeration does not open a video stream. The
            # setup UI can explicitly reselect the matching stable device path.
            try:
                from chilli.cameras import enumerate_connected_cameras
                sources = enumerate_connected_cameras()
                matching = [source for source in sources if
                            source.path.casefold() == self.config.camera_path.casefold()
                            and (not self.config.camera_backend or source.backend == self.config.camera_backend)]
                if not matching:
                    self._source_problem = "Selected camera disconnected; reconnect it or choose another source"
                    return None
                if not any(source.index == self.config.camera_index for source in matching):
                    self._source_problem = "Selected camera index changed; choose the source again"
                    return None
            except Exception as exc:
                self._source_problem = f"Cannot verify selected camera ({type(exc).__name__}); refresh camera sources"
                return None
        backends = ([self.config.camera_backend] if self.config.camera_backend else
                    [cv2.CAP_DSHOW, cv2.CAP_ANY] if sys.platform == "win32" else [cv2.CAP_ANY])
        for backend in backends:
            if self._stop_event.is_set():
                return None
            camera = None
            try:
                camera = cv2.VideoCapture(self.config.camera_index, backend)
                if camera.isOpened():
                    camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
                    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
                    camera.set(cv2.CAP_PROP_FPS, self.config.fps)
                    # Not every driver honors this; continuous capture plus a
                    # single latest-frame slot bounds our own buffering anyway.
                    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    return camera
            except Exception:
                pass
            if camera is not None:
                camera.release()
        return None

    def _capture(self, cv2: Any) -> None:
        while not self._stop_event.is_set():
            self._camera_problem(f"Opening camera {self.config.camera_index}")
            with self._lock:
                self._capture_call_started = time.monotonic()
            camera = self._open_camera(cv2)
            with self._lock:
                self._capture_call_started = None
            if camera is None:
                self._camera_problem(
                    self._source_problem or
                    f"Camera {self.config.camera_index} unavailable; check USB/camera permissions. Retrying..."
                )
                self._stop_event.wait(self.config.retry_seconds)
                continue
            with self._lock:
                self._camera_generation += 1
            try:
                while not self._stop_event.is_set():
                    with self._lock:
                        self._capture_call_started = time.monotonic()
                    ok, frame = camera.read()
                    # Observation time, captured BEFORE potentially slow pose
                    # inference, is the only timestamp supplied to game scoring.
                    observed_at = time.monotonic()
                    if self._stop_event.is_set():
                        break
                    if not ok or frame is None or getattr(frame, "size", 0) == 0:
                        self._camera_problem("Camera signal lost; reconnecting...")
                        break
                    with self._lock:
                        self._capture_call_started = None
                        self._sequence += 1
                        self._latest_frame = (self._sequence, observed_at, frame)
                        self._camera_status = "Camera connected"
                    self._frame_event.set()
                    # Real webcams block read at their frame cadence. The small
                    # wait also avoids a busy loop with unusual virtual cameras.
                    self._stop_event.wait(0.002)
            except Exception as exc:
                self._camera_problem(f"Camera read failed ({type(exc).__name__}); reconnecting...")
            finally:
                camera.release()
            self._stop_event.wait(self.config.retry_seconds)

    def _run(self) -> None:
        model_path = Path(self.config.model_path)
        if not model_path.is_file():
            self._publish(TrackingSnapshot(status="Pose model missing; run setup.ps1 or use --demo"))
            return
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except (ImportError, OSError) as exc:
            self._publish(TrackingSnapshot(
                status=f"Tracking dependencies unavailable ({type(exc).__name__}); run setup.ps1 or use --demo"
            ))
            return

        detector = None
        try:
            options = vision.PoseLandmarkerOptions(
                base_options=python.BaseOptions(
                    model_asset_path=str(model_path), delegate=python.BaseOptions.Delegate.CPU
                ),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=self.config.confidence,
                min_pose_presence_confidence=self.config.confidence,
                min_tracking_confidence=self.config.confidence,
                output_segmentation_masks=False,
            )
            detector = vision.PoseLandmarker.create_from_options(options)
            if self._stop_event.is_set():
                return
            self._camera_thread = threading.Thread(target=self._capture, args=(cv2,), name="chilli-camera", daemon=True)
            self._camera_thread.start()
            last_sequence = -1
            last_ms = -1
            last_observed = 0.0
            generation_seen = -1
            warmup_until = 0.0
            measured_fps = 0.0
            next_inference_at = 0.0
            while not self._stop_event.is_set():
                delay = next_inference_at - time.monotonic()
                if delay > 0 and self._stop_event.wait(delay):
                    break
                with self._lock:
                    latest = self._latest_frame
                    generation = self._camera_generation
                    preview_enabled = self._preview_enabled
                if latest is None or latest[0] == last_sequence:
                    self._frame_event.wait(0.1)
                    self._frame_event.clear()
                    continue
                sequence, observed_at, frame = latest
                last_sequence = sequence
                started = time.monotonic()
                next_inference_at = started + 1.0 / self.config.fps
                if generation != generation_seen:
                    generation_seen = generation
                    warmup_until = observed_at + 0.4
                    last_observed = 0.0
                    measured_fps = 0.0
                if self.config.mirror:
                    frame = cv2.flip(frame, 1)
                frame_height, frame_width = frame.shape[:2]
                crop_left = int(self.config.zone_left * frame_width)
                crop_right = max(crop_left + 1, int(self.config.zone_right * frame_width))
                cropped_rgb = cv2.cvtColor(frame[:, crop_left:crop_right], cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cropped_rgb)
                timestamp_ms = max(last_ms + 1, int(observed_at * 1000))
                last_ms = timestamp_ms
                with self._lock:
                    self._inference_call_started = time.monotonic()
                result = detector.detect_for_video(mp_image, timestamp_ms)
                with self._lock:
                    self._inference_call_started = None
                if self._stop_event.is_set():
                    break
                sample, landmarks, status = _pose_sample(
                    result, observed_at, self.config, frame_width, frame_height,
                    crop_left, crop_right - crop_left,
                )
                if observed_at < warmup_until:
                    sample = PoseSample(timestamp=observed_at, present=False)
                    status = "Camera warming up"
                if last_observed:
                    instant_fps = 1.0 / max(0.001, observed_at - last_observed)
                    measured_fps = instant_fps if not measured_fps else 0.8 * measured_fps + 0.2 * instant_fps
                last_observed = observed_at
                preview = None
                if preview_enabled:
                    preview = cv2.cvtColor(
                        cv2.resize(frame, (320, max(1, round(frame_height * 320 / frame_width))), interpolation=cv2.INTER_AREA),
                        cv2.COLOR_BGR2RGB,
                    )
                    preview.setflags(write=False)
                with self._lock:
                    # Do not overwrite a disconnect status with the result of an
                    # inference that began just before the camera disconnected.
                    if self._latest_frame is not None and generation == self._camera_generation:
                        self._snapshot = TrackingSnapshot(
                            sample=sample, ready=True, status=status, fps=measured_fps,
                            preview=preview if self._preview_enabled else None,
                            landmarks=landmarks if self._preview_enabled else (),
                        )
        except Exception as exc:
            # Surface boot/model failures in the game instead of dying silently.
            if not self._stop_event.is_set():
                self._publish(TrackingSnapshot(
                    status=f"Body tracker failed ({type(exc).__name__}: {str(exc)[:160]}); restart or use --demo"
                ))
                self._stop_event.set()
        finally:
            if detector is not None:
                detector.close()
