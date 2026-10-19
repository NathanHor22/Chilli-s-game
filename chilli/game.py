"""Clock-driven game rules and inexpensive, frame-rate-independent sway scoring.

This module deliberately has no camera or rendering dependencies. All times are
seconds on the same monotonic clock. Repeated observations never earn points.
"""

from dataclasses import dataclass
import math
from statistics import median


@dataclass(frozen=True)
class PoseSample:
    timestamp: float
    present: bool
    x: float = 0.5
    scale: float = 0.2
    lean: float = 0.0


@dataclass
class GameConfig:
    round_seconds: float = 10.0
    instructions_seconds: float = 4.0
    countdown_seconds: float = 3.0
    settle_seconds: float = 1.0
    result_seconds: float = 3.0
    clear_seconds: float = 1.0
    lost_seconds: float = 2.0
    stale_seconds: float = 0.4
    target_motion: float = 6.0
    noise_speed: float = 0.10
    max_speed: float = 3.0
    # Time constants are in seconds; distances are in shoulder widths.
    smoothing_seconds: float = 0.08
    scale_smoothing_seconds: float = 1.0
    movement_deadband: float = 0.025
    lean_deadband: float = 0.04
    lean_weight: float = 0.35
    # Reject likely tracking/person changes rather than scoring the jump.
    max_position_jump: float = 1.25
    max_scale_ratio: float = 1.65
    max_observed_speed: float = 8.0

    def __post_init__(self) -> None:
        positive = (
            "round_seconds", "lost_seconds", "stale_seconds", "target_motion",
            "max_speed", "smoothing_seconds", "scale_smoothing_seconds",
            "max_position_jump", "max_observed_speed",
        )
        nonnegative = (
            "instructions_seconds", "countdown_seconds", "settle_seconds", "result_seconds",
            "clear_seconds", "noise_speed", "movement_deadband",
            "lean_deadband", "lean_weight",
        )
        for name in positive:
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and greater than zero")
        for name in nonnegative:
            if not math.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not math.isfinite(self.max_scale_ratio) or self.max_scale_ratio <= 1:
            raise ValueError("max_scale_ratio must be finite and greater than one")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class Game:
    """State machine for a single visitor and a ten-second movement challenge.

    ``update`` may run more frequently than the camera. Pass the latest sample,
    or ``None`` when no new sample exists; a cached pose expires automatically.
    A sample explicitly marked absent takes effect immediately.
    Instructions and countdown precede every round without consuming play time.
    """

    MESSAGES = {
        "idle": "Step into the play area",
        "instructions": "Sway left and right to grow the chilli",
        "countdown": "Sway side to side to turn up the heat!",
        "playing": "Keep swaying!",
        "won": "MAX HEAT! YOU WIN!",
        "timeout": "Almost! Give it another go!",
        "clear": "Step out to let the next player play",
        "error": "Camera disconnected. Reconnecting...",
    }

    def __init__(self, config: GameConfig):
        self.config = config
        self.round_number = 0
        self._last_now: float | None = None
        self.reset(0.0)
        self._last_now = None

    def reset(self, now: float) -> None:
        """Operator reset. Round numbers remain cumulative for this process."""
        if not math.isfinite(now):
            raise ValueError("now must be finite")
        self._last_now = now
        self.state = "idle"
        self.message = self.MESSAGES[self.state]
        self.heat = 0.0
        self.remaining = self.config.round_seconds
        self.countdown = 0
        self.sway = 0.0
        self.player_visible = False
        self._state_started = now
        self._round_started: float | None = None
        self._present_since: float | None = None
        self._lost_since: float | None = None
        self._empty_since: float | None = None
        self._latest: PoseSample | None = None
        self._last_sample_timestamp = -math.inf
        self._calibration: list[tuple[float, float]] = []
        self._scale = 0.2
        self._center_x = 0.5
        self._motion_seeded = False
        self._clear_motion()

    def _clear_motion(self) -> None:
        self._motion_sample: PoseSample | None = None
        self._filtered_x = 0.0
        self._filtered_lean = 0.0
        self._scored_x = 0.0
        self._scored_lean = 0.0
        self.sway = 0.0

    def _set_state(self, state: str, now: float) -> None:
        self.state = state
        self.message = self.MESSAGES[state]
        self._state_started = now
        self.countdown = 0
        self._present_since = None
        self._lost_since = None
        self._empty_since = None
        self._clear_motion()
        if state == "idle":
            self.heat = 0.0
            self.remaining = self.config.round_seconds
            self._calibration.clear()
        elif state == "playing":
            self._round_started = now
            self._motion_seeded = False
            self.round_number += 1
            self.heat = 0.0
            self.remaining = self.config.round_seconds
            if self._calibration:
                self._center_x = median(item[0] for item in self._calibration)
                self._scale = median(item[1] for item in self._calibration)
        elif state == "error":
            self.heat = 0.0

    @staticmethod
    def _valid_pose(sample: PoseSample) -> bool:
        return (
            sample.present
            and all(math.isfinite(v) for v in (sample.x, sample.scale, sample.lean))
            and 0.0 <= sample.x <= 1.0
            and 0.02 <= sample.scale <= 1.0
            and abs(sample.lean) <= 5.0
        )

    def _observe(self, now: float, sample: PoseSample | None) -> PoseSample | None:
        new = None
        if (
            sample is not None
            and math.isfinite(sample.timestamp)
            and self._last_sample_timestamp < sample.timestamp <= now
        ):
            self._latest = sample
            self._last_sample_timestamp = sample.timestamp
            new = sample
        latest = self._latest
        self.player_visible = bool(
            latest is not None
            and self._valid_pose(latest)
            and 0 <= now - latest.timestamp <= self.config.stale_seconds
        )
        return new if self.player_visible else None

    def update(
        self, now: float, sample: PoseSample | None, camera_ready: bool = True
    ) -> None:
        if not math.isfinite(now) or (self._last_now is not None and now < self._last_now):
            raise ValueError("update timestamps must be finite and monotonic")
        self._last_now = now
        new = self._observe(now, sample)

        if not camera_ready:
            self.player_visible = False
            if self.state != "error":
                self._set_state("error", now)
            return
        if self.state == "error":
            self._set_state("clear", now)

        if self.state in ("won", "timeout"):
            if now - self._state_started < self.config.result_seconds:
                return
            self._set_state("clear", now)

        if self.state == "clear":
            if self.player_visible:
                self._empty_since = None
            else:
                if self._empty_since is None:
                    self._empty_since = now
                if now - self._empty_since >= self.config.clear_seconds:
                    self._set_state("idle", now)
            return

        if self.state == "idle":
            if not self.player_visible:
                self._present_since = None
                self._calibration.clear()
                return
            if self._present_since is None:
                self._present_since = now
            if new is not None:
                self._calibrate(new)
            if now - self._present_since < self.config.settle_seconds:
                return
            self._set_state("instructions", now)

        if self.state == "instructions":
            if not self.player_visible:
                self._set_state("idle", now)
                return
            if new is not None:
                self._calibrate(new)
            instructions_end = self._state_started + self.config.instructions_seconds
            if now < instructions_end:
                return
            self._set_state("countdown", instructions_end)

        if self.state == "countdown":
            if not self.player_visible:
                self._set_state("idle", now)
                return
            if new is not None:
                self._calibrate(new)
            countdown_end = self._state_started + self.config.countdown_seconds
            self.countdown = max(0, math.ceil(countdown_end - now))
            if now < countdown_end:
                return
            self._set_state("playing", countdown_end)

        if self.state == "playing":
            assert self._round_started is not None
            deadline = self._round_started + self.config.round_seconds
            self.remaining = max(0.0, deadline - now)
            # No new scoring at/after the deadline, including delayed results.
            if now >= deadline:
                self._set_state("timeout", now)
                return
            if not self.player_visible:
                self._clear_motion()
                if self._lost_since is None:
                    latest = self._latest
                    self._lost_since = now
                    if latest is not None:
                        self._lost_since = min(
                            now,
                            latest.timestamp + (
                                self.config.stale_seconds if self._valid_pose(latest) else 0.0
                            ),
                        )
                if now - self._lost_since >= self.config.lost_seconds:
                    self._set_state("clear", now)
                return
            if new is not None:
                # A slow render loop must not rescue a round just because the
                # player returns on the first update after a long disappearance.
                loss_started = self._lost_since
                if loss_started is None and self._motion_sample is not None:
                    loss_started = self._motion_sample.timestamp + self.config.stale_seconds
                if (
                    loss_started is not None
                    and new.timestamp - loss_started >= self.config.lost_seconds
                ):
                    self._set_state("clear", now)
                    return
            self._lost_since = None
            if new is not None and self._round_started <= new.timestamp < deadline:
                self._score(new)
                if self.heat >= 1.0:
                    self._set_state("won", now)

    def _calibrate(self, sample: PoseSample) -> None:
        self._calibration.append((sample.x, sample.scale))
        if len(self._calibration) > 90:
            del self._calibration[0]

    def _seed_motion(self, sample: PoseSample) -> None:
        self._motion_sample = sample
        self._filtered_x = self._scored_x = sample.x
        self._filtered_lean = self._scored_lean = sample.lean
        self._update_sway()

    def _update_sway(self) -> None:
        self.sway = _clamp(
            (self._filtered_x - self._center_x) / self._scale
            + 0.5 * self._filtered_lean,
            -1.0, 1.0,
        )

    def _score(self, sample: PoseSample) -> None:
        previous = self._motion_sample
        if previous is None:
            if self._motion_seeded:
                # After occlusion, a new participant or a change in distance
                # must not inherit an outdated body-size normalization.
                self._scale = sample.scale
            self._motion_seeded = True
            self._seed_motion(sample)
            return
        dt = sample.timestamp - previous.timestamp
        if dt <= 0:
            return
        scale_ratio = max(sample.scale, previous.scale) / min(sample.scale, previous.scale)
        raw_distance = abs(sample.x - previous.x) / max(self._scale, 0.02)
        if (
            dt > self.config.stale_seconds
            or scale_ratio > self.config.max_scale_ratio
            or raw_distance > self.config.max_position_jump
            or raw_distance / dt > self.config.max_observed_speed
            or abs(sample.lean - previous.lean) > 1.5
        ):
            # Reappearance and likely player switches establish a new baseline.
            self._scale = sample.scale
            self._seed_motion(sample)
            return

        alpha = -math.expm1(-dt / self.config.smoothing_seconds)
        scale_alpha = -math.expm1(-dt / self.config.scale_smoothing_seconds)
        self._scale += scale_alpha * (sample.scale - self._scale)
        self._filtered_x += alpha * (sample.x - self._filtered_x)
        self._filtered_lean += alpha * (sample.lean - self._filtered_lean)

        x_delta = self._filtered_x - self._scored_x
        lean_delta = self._filtered_lean - self._scored_lean
        x_distance = max(0.0, abs(x_delta) / self._scale - self.config.movement_deadband)
        lean_distance = max(0.0, abs(lean_delta) - self.config.lean_deadband)
        if x_distance:
            self._scored_x = self._filtered_x - math.copysign(
                self.config.movement_deadband * self._scale, x_delta
            )
        if lean_distance:
            self._scored_lean = self._filtered_lean - math.copysign(
                self.config.lean_deadband, lean_delta
            )

        distance = x_distance + self.config.lean_weight * lean_distance
        # Integrate movement, subtract a speed floor, and cap implausible bursts.
        motion = _clamp(distance - self.config.noise_speed * dt, 0.0, self.config.max_speed * dt)
        self.heat = min(1.0, self.heat + motion / self.config.target_motion)
        self._motion_sample = sample
        self._update_sway()
