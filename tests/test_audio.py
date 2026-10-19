import os
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest
from unittest.mock import Mock, patch
import pygame
from chilli.audio import Audio


class AudioTests(unittest.TestCase):
    def tearDown(self):
        pygame.mixer.quit()

    def audio(self):
        audio = Audio(True)
        self.assertTrue(audio.available)
        audio._sizzle_channel = Mock()
        audio._sizzle_channel.get_busy.return_value = False
        return audio

    def test_heat_loop_builds_and_stops_on_menu_or_mute(self):
        audio = self.audio()
        audio.update(0, playing=True, heat=0, energy=0)
        low = audio._sizzle_channel.set_volume.call_args.args[0]
        audio.update(1, playing=True, heat=1, energy=1)
        self.assertGreater(audio._sizzle_channel.set_volume.call_args.args[0], low)
        audio.update(2, playing=False)
        audio._sizzle_channel.stop.assert_called()
        audio.toggle()
        audio.update(3, playing=True, impact_serial=3)
        audio._sizzle_channel.stop.assert_called()

    def test_pop_cues_are_rate_limited_and_not_repeated_for_cached_impacts(self):
        audio = self.audio()
        with patch.object(audio, "play") as play:
            audio.update(0, playing=True, energy=.9, impact_serial=1)
            audio.update(.01, playing=True, energy=.9, impact_serial=1)
            audio.update(.05, playing=True, energy=.9, impact_serial=2)
            audio.update(.2, playing=True, energy=.3, impact_serial=3)
            self.assertEqual([c.args[0] for c in play.call_args_list], ["pop", "boing"])

    def test_muted_impacts_do_not_replay_after_unmute(self):
        audio = self.audio()
        audio.enabled = False
        with patch.object(audio, "play") as play:
            audio.update(1, playing=True, impact_serial=20)
            audio.enabled = True
            audio.update(2, playing=True, impact_serial=20)
            play.assert_not_called()

    def test_audio_device_loss_does_not_crash_gameplay(self):
        audio = self.audio()
        audio._sizzle_channel.play.side_effect = pygame.error("device removed")
        audio.update(1, playing=True)
        self.assertFalse(audio.available)
        audio.play("won")
        audio.toggle()


if __name__ == "__main__":
    unittest.main()
