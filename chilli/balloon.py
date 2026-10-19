"""Bounded visual-only balloon motion. This module never changes game scoring."""
from __future__ import annotations

import math


PLAY_BOUNDS = (70.0, 140.0, 1210.0, 590.0)  # left, top, right, bottom


def _clamp(value, low, high):
    return max(low, min(high, value))


class Balloon:
    """Inertia, drag, wall bounce and a damped squash/stretch spring.

    Measured motion is consumed once per timestamp and weighted by its sampling
    interval. Repeated render frames cannot produce additional input impulses.
    ``impact_serial`` is monotonic, including across resets, for optional audio.
    """

    MAX_SPEED = 680.0
    DRAG = 0.7
    MAX_FRAME_SECONDS = 0.1
    MAX_STEP_SECONDS = 1.0 / 120.0
    INPUT_MAX_AGE = 0.4

    def __init__(self, bounds=PLAY_BOUNDS):
        self.bounds = tuple(float(value) for value in bounds)
        left, top, right, bottom = self.bounds
        if not all(math.isfinite(value) for value in self.bounds) or right <= left or bottom <= top:
            raise ValueError("Balloon bounds must be a finite, positive rectangle")
        self.impact_serial = 0
        self.reset()

    def reset(self, now=None):
        left, top, right, bottom = self.bounds
        self.x, self.y = (left + right) / 2, (top + bottom) / 2
        self.vx = self.vy = 0.0
        self.deformation = self.deformation_velocity = 0.0
        self.pop = self.movement_energy = 0.0
        self._target_energy = 0.0
        self._last_time = now
        self._last_motion_stamp = None
        self._last_pop_time = -math.inf
        self.impact_time = -math.inf
        self.impact_position = (self.x, self.y)
        self.impact_strength = 0.0

    def _impact(self, now, strength):
        self.impact_serial += 1
        self.impact_time = now
        self.impact_position = (self.x, self.y)
        self.impact_strength = _clamp(strength, 0.0, 1.0)
        self.pop = max(self.pop, self.impact_strength)

    def _consume(self, now, timestamp, motion_x, motion_y, energy):
        values = (timestamp, motion_x, motion_y, energy)
        if timestamp is None or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
            self._target_energy = 0.0
            return
        if not -0.03 <= now - timestamp <= self.INPUT_MAX_AGE:
            self._target_energy = 0.0
            return
        if self._last_motion_stamp is not None and timestamp <= self._last_motion_stamp:
            return
        interval = 1.0 / 15.0 if self._last_motion_stamp is None else timestamp - self._last_motion_stamp
        interval = min(interval, 0.1)
        self._last_motion_stamp = timestamp
        self._target_energy = _clamp(energy, 0.0, 1.0)
        if self._target_energy <= 0.01:
            return
        dx, dy = _clamp(motion_x, -1.0, 1.0), _clamp(motion_y, -1.0, 1.0)
        # Sideways body movement also gives the balloon a gentle vertical kick.
        # Hand input controls the full direction; positive y points down-screen.
        if abs(dy) < 0.08:
            dy += math.sin(timestamp * 2.3 + 0.7) * self._target_energy * 0.35
        self.vx += dx * 3700.0 * interval
        self.vy += dy * 3700.0 * interval
        speed = math.hypot(self.vx, self.vy)
        if speed > self.MAX_SPEED:
            factor = self.MAX_SPEED / speed
            self.vx *= factor
            self.vy *= factor
        if self._target_energy >= 0.68 and now - self._last_pop_time >= 0.35:
            self._last_pop_time = now
            self.deformation_velocity += (0.9 if abs(dy) > abs(dx) else -0.9)
            self._impact(now, self._target_energy)

    def constrain(self, half_width, half_height, now):
        """Keep the full transformed sprite inside the play area, including growth."""
        left, top, right, bottom = self.bounds
        half_width = _clamp(float(half_width), 0.0, (right - left) / 2)
        half_height = _clamp(float(half_height), 0.0, (bottom - top) / 2)
        min_x, max_x = left + half_width, right - half_width
        min_y, max_y = top + half_height, bottom - half_height
        hit_speed = 0.0
        if self.x < min_x or self.x > max_x:
            outward = self.vx < 0 if self.x < min_x else self.vx > 0
            self.x = _clamp(self.x, min_x, max_x)
            if outward:
                hit_speed = abs(self.vx)
                self.vx *= -0.86
                self.deformation, self.deformation_velocity = -0.16, 0.0
        if self.y < min_y or self.y > max_y:
            outward = self.vy < 0 if self.y < min_y else self.vy > 0
            self.y = _clamp(self.y, min_y, max_y)
            if outward:
                hit_speed = max(hit_speed, abs(self.vy))
                self.vy *= -0.86
                self.deformation, self.deformation_velocity = 0.16, 0.0
        if hit_speed >= 130.0:
            self._impact(now, min(1.0, hit_speed / self.MAX_SPEED))

    def update(self, now, *, motion_timestamp=None, motion_x=0.0, motion_y=0.0,
               energy=0.0, half_width=140.0, half_height=140.0):
        if not math.isfinite(now):
            raise ValueError("Balloon time must be finite")
        if self._last_time is not None and now < self._last_time:
            self.reset(now)
        elapsed = 0.0 if self._last_time is None else now - self._last_time
        self._last_time = now
        elapsed = min(elapsed, self.MAX_FRAME_SECONDS)
        steps = max(1, math.ceil(elapsed / self.MAX_STEP_SECONDS))
        dt = elapsed / steps
        for _ in range(steps):
            drag = math.exp(-self.DRAG * dt)
            distance = (1.0 - drag) / self.DRAG
            self.x += self.vx * distance
            self.y += self.vy * distance
            self.vx *= drag
            self.vy *= drag
            self.deformation_velocity += (-110.0 * self.deformation - 15.0 * self.deformation_velocity) * dt
            self.deformation = _clamp(self.deformation + self.deformation_velocity * dt, -0.2, 0.2)
            self.pop *= math.exp(-7.0 * dt)
            self.movement_energy += (self._target_energy - self.movement_energy) * (1.0 - math.exp(-8.0 * dt))
            self.constrain(half_width, half_height, now)
        # A sample received now changes future velocity. Applying it before the
        # elapsed interval would move farther when the renderer runs more slowly.
        self._consume(now, motion_timestamp, motion_x, motion_y, energy)
        return self

    @property
    def stretch(self):
        travel = 0.075 * (self.vx * self.vx - self.vy * self.vy) / self.MAX_SPEED ** 2
        squash = self.deformation + travel
        pulse = 1.0 + self.pop * 0.08
        return math.exp(squash) * pulse, math.exp(-squash) * pulse

    @property
    def angle(self):
        return _clamp(-self.vx * 0.018 + self.deformation * 18, -13.0, 13.0)
