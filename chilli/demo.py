"""Event-driven keyboard stand-in for a visitor, without changing camera rules."""

from __future__ import annotations

import math

import pygame

from chilli.game import Game, PoseSample


class DemoController:
    """Turn start and sway key events into a bounded, smoothly moving torso.

    Feed every pygame event to ``handle_event``, then pass the sample returned
    by ``update`` to the normal ``game.update``. Key transitions are remembered,
    so even a press and release delivered in the same frame produces a sway.
    ``reset`` starts fresh instructions followed by the countdown; it is also
    the demo's R-key action.
    """

    LEFT_KEYS = frozenset((pygame.K_LEFT, pygame.K_a))
    RIGHT_KEYS = frozenset((pygame.K_RIGHT, pygame.K_d))
    START_KEYS = frozenset((pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE))
    TAP_SECONDS = 0.12
    STANCE_OFFSET = 0.18
    RESPONSE_SECONDS = 0.09
    MAX_SPEED = 0.65
    MIN_X = 0.24
    MAX_X = 0.76

    def __init__(self, game: Game):
        self.game = game
        self.active = False
        self.x = 0.5
        self.direction = 0
        self._held: set[int] = set()
        self._pulses: dict[int, float] = {}
        self._start_held: set[int] = set()

    def _clear_movement(self) -> None:
        self._held.clear()
        self._pulses.clear()
        self.direction = 0

    def reset(self, now: float) -> None:
        """Start/retry with the full configured instructions and countdown.

        A keyboard start already confirms player presence. Supply the settling
        observations through the public engine API instead of altering its
        camera configuration or reaching into its internal state machine.
        """
        self.active = True
        self.x = 0.5
        self._clear_movement()
        settled_at = now - self.game.config.settle_seconds
        self.game.reset(settled_at)
        self.game.update(settled_at, PoseSample(settled_at, True))
        self.game.update(now, PoseSample(now, True))

    def handle_event(self, event: pygame.event.Event, now: float) -> None:
        if event.type == pygame.WINDOWFOCUSLOST or (
            event.type == pygame.ACTIVEEVENT
            and not getattr(event, "gain", 1)
            and getattr(event, "state", 0) & pygame.APPINPUTFOCUS
        ):
            self._clear_movement()
            self._start_held.clear()
            return

        if event.type == pygame.KEYUP:
            key = event.key
            self._held.discard(key)
            self._start_held.discard(key)
            # A short tap keeps its minimum pulse even after key release.
            return

        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        if key in self.START_KEYS:
            if key in self._start_held or getattr(event, "repeat", False):
                return
            self._start_held.add(key)
            if self.game.state not in ("instructions", "countdown", "playing"):
                self.reset(now)
            return

        if key in self.LEFT_KEYS | self.RIGHT_KEYS and self.active:
            if key not in self._held:
                self._pulses[key] = now + self.TAP_SECONDS
            self._held.add(key)

    def update(self, now: float, dt: float) -> PoseSample:
        if not math.isfinite(now) or not math.isfinite(dt) or dt < 0:
            raise ValueError("demo time and frame duration must be finite and nonnegative")
        self._pulses = {key: until for key, until in self._pulses.items() if until > now}
        pressing = self._held | self._pulses.keys()
        left = bool(pressing & self.LEFT_KEYS)
        right = bool(pressing & self.RIGHT_KEYS)
        # Opposing inputs cancel. Releasing a direction naturally recenters,
        # rather than leaving the simulated body stuck against an image edge.
        self.direction = int(right) - int(left) if self.active else 0
        target = 0.5 + self.STANCE_OFFSET * self.direction
        step = (target - self.x) * -math.expm1(-dt / self.RESPONSE_SECONDS)
        limit = self.MAX_SPEED * min(dt, 0.1)
        self.x += max(-limit, min(limit, step))
        self.x = max(self.MIN_X, min(self.MAX_X, self.x))
        if abs(self.x - target) < 1e-7:
            self.x = target
        return PoseSample(now, self.active, x=self.x, scale=0.2, lean=(self.x - 0.5) * 0.6)

    def hint(self, state: str | None = None) -> str:
        state = state or self.game.state
        if not self.active or state == "idle":
            return "Press ENTER or SPACE to start"
        if state == "instructions":
            return "Sway LEFT and RIGHT, or use A and D. Your round starts shortly"
        if state == "countdown":
            return "Get ready! Alternate LEFT and RIGHT, or A and D"
        if state == "playing":
            return "Alternate LEFT / RIGHT or A / D to grow the chilli"
        return "Press ENTER or SPACE to play again"
