"""Small synthesized cues; no audio assets or mixer dependency in game logic."""
from __future__ import annotations

from array import array
import math
import random
import pygame


class Audio:
    def __init__(self, enabled: bool = True, volume: float = .35):
        self.enabled = enabled
        self.available = False
        self.sounds = {}
        self.volume = max(0., min(1., volume))
        self._sizzle_channel = None
        self._seen_impact = 0
        self._last_impact = -math.inf
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            rate, _, channels = pygame.mixer.get_init()
            for name, notes in {
                "tick": [(660, .085)],
                "go": [(660, .08), (880, .15)],
                "won": [(523.25, .10), (659.25, .10), (783.99, .10), (1046.5, .28)],
                "timeout": [(440, .12), (329.63, .22)],
            }.items():
                pcm = array("h")
                for frequency, duration in notes:
                    count = int(rate * duration)
                    for i in range(count):
                        envelope = min(1., i / (rate * .008), (count - i) / (rate * .04))
                        value = int(11000 * envelope * math.sin(math.tau * frequency * i / rate))
                        pcm.extend([value] * channels)
                sound = pygame.mixer.Sound(buffer=pcm.tobytes())
                sound.set_volume(volume)
                self.sounds[name] = sound
            for name, duration in (("pop", .10), ("boing", .19), ("sizzle", 1.0)):
                pcm = array("h")
                count = int(rate*duration)
                rng = random.Random(74)
                phase = 0.
                for i in range(count):
                    t = i/rate
                    envelope = min(1., i/(rate*.004), (count-i)/(rate*.012))
                    if name == "sizzle":
                        value = 5200*rng.uniform(-1., 1.)*(.65+.35*math.sin(t*math.tau*17)**2)
                    else:
                        frequency = (850-600*t/duration if name == "pop"
                                     else 150+90*math.sin(t*math.tau*9)*math.exp(-t*10))
                        phase += math.tau*frequency/rate
                        value = 10000*math.sin(phase)*math.exp(-t*18)
                    pcm.extend([int(value*envelope)]*channels)
                sound = pygame.mixer.Sound(buffer=pcm.tobytes())
                sound.set_volume(1. if name == "sizzle" else self.volume*.7)
                self.sounds[name] = sound
            pygame.mixer.set_reserved(1)
            self._sizzle_channel = pygame.mixer.Channel(0)
            self.available = True
        except pygame.error:
            pass  # A disconnected speaker must never stop the installation.

    def play(self, name: str):
        if self.enabled and self.available and name in self.sounds:
            try:
                self.sounds[name].play()
            except pygame.error:
                self.available = False

    def update(self, now, *, playing=False, heat=0., energy=0., impact_serial=0):
        """One quiet heat loop plus rate-limited pops; no new buffers per frame."""
        changed = impact_serial != self._seen_impact
        self._seen_impact = impact_serial
        if not self.available:
            return
        try:
            if not self.enabled or not playing:
                self._sizzle_channel.stop()
                return
            heat = max(0., min(1., heat))
            energy = max(0., min(1., energy))
            if not self._sizzle_channel.get_busy():
                self._sizzle_channel.play(self.sounds["sizzle"], loops=-1)
            self._sizzle_channel.set_volume(self.volume*(.04 + .20*heat + .08*energy))
            if changed and now-self._last_impact >= .16:
                self.play("pop" if energy > .65 else "boing")
                self._last_impact = now
        except pygame.error:
            self.available = False

    def toggle(self):
        self.enabled = not self.enabled
        if not self.enabled and self.available:
            try:
                pygame.mixer.stop()
            except pygame.error:
                self.available = False
