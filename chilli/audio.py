"""Small synthesized cues; no audio assets or mixer dependency in game logic."""
from __future__ import annotations

from array import array
import math
import pygame


class Audio:
    def __init__(self, enabled: bool = True, volume: float = .35):
        self.enabled = enabled
        self.available = False
        self.sounds = {}
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
            self.available = True
        except pygame.error:
            pass  # A disconnected speaker must never stop the installation.

    def play(self, name: str):
        if self.enabled and self.available and name in self.sounds:
            self.sounds[name].play()

    def toggle(self):
        self.enabled = not self.enabled
        if not self.enabled and self.available:
            pygame.mixer.stop()
