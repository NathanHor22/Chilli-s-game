"""Cached 2D projector graphics. All illustrations are drawn locally."""
from __future__ import annotations

from collections import OrderedDict
import math
import random
import pygame

from .balloon import Balloon, PLAY_BOUNDS

CREAM = (255, 246, 233)
INK = (64, 36, 26)
RED = (218, 45, 34)
MUTED = (145, 111, 90)
GREEN = (60, 101, 45)
BLACK = (0, 0, 0)
LIGHT_TEXT = (255, 255, 255)
SOFT_TEXT = (210, 210, 210)
HOT_TEXT = (255, 141, 98)


def curve(start, *segments):
    """Sample cubic Beziers for antialiased, code-native illustration paths."""
    points = [start]
    p0 = start
    for p1, p2, p3 in segments:
        for step in range(1, 25):
            t = step / 24
            u = 1 - t
            points.append((u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0],
                           u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]))
        p0 = p3
    return points


def pepper_art():
    # Draw at double resolution once, then downsample for clean contours.
    surface = pygame.Surface((1000, 1000), pygame.SRCALPHA)
    def poly(color, points):
        pygame.draw.polygon(surface, color, [(int(x*2), int(y*2)) for x, y in points])
    def line(color, points, width):
        pts = [(int(x*2), int(y*2)) for x, y in points]
        pygame.draw.lines(surface, color, False, pts, width*2)
        for point in (pts[0], pts[-1]):
            pygame.draw.circle(surface, color, point, width)
    body = curve((319, 113),
        ((360, 101), (391, 128), (384, 181)),
        ((369, 292), (284, 387), (177, 411)),
        ((104, 428), (47, 396), (28, 355)),
        ((65, 384), (112, 369), (151, 342)),
        ((211, 300), (246, 242), (260, 176)),
        ((268, 133), (283, 115), (319, 113)))
    poly((173, 27, 26), [(x+2, y+6) for x, y in body])
    poly((240, 56, 45), body)
    poly((207, 34, 32), curve((381, 156),
        ((380, 275), (282, 385), (177, 411)),
        ((111, 427), (54, 400), (28, 355)),
        ((91, 402), (189, 379), (263, 308)),
        ((324, 249), (358, 201), (381, 156))))
    poly((255, 91, 70), curve((307, 138),
        ((264, 162), (280, 229), (231, 295)),
        ((272, 257), (315, 189), (327, 147)),
        ((329, 136), (318, 133), (307, 138))))
    line((255, 206, 176), curve((305, 156), ((292, 169), (288, 188), (283, 204))), 12)
    line((255, 128, 105), curve((239, 296), ((212, 325), (181, 347), (153, 355))), 5)
    stem = curve((326, 123), ((328, 77), (350, 45), (385, 49)))
    line((41, 77, 34), stem, 24)
    line((77, 125, 49), curve((323, 101), ((332, 69), (351, 50), (378, 51))), 8)
    cap = curve((302, 109),
        ((310, 101), (332, 100), (346, 113)),
        ((355, 117), (365, 132), (364, 145)),
        ((349, 143), (344, 132), (336, 133)),
        ((329, 145), (320, 146), (313, 135)),
        ((299, 141), (283, 137), (279, 125)),
        ((288, 120), (293, 115), (302, 109)))
    poly((48, 89, 39), cap)
    return pygame.transform.smoothscale(surface, (500, 500))


DEMO_START_RECT = (360, 610, 560, 66)


def encouragement(heat, player_visible=True):
    """One instruction at a time, readable across a projection space."""
    if not player_visible:
        return "Step back into view"
    if heat < .25:
        return "Bring the heat!"
    if heat < .5:
        return "Keep going!"
    if heat < .8:
        return "Scorching moves!"
    return "Almost there!"


def heat_rating(heat, won=False):
    if won:
        return "Volcanic"
    return "Warm" if heat < .4 else "Spicy" if heat < .8 else "Scorching"


def _sway_person(lean, wave):
    """Pre-render one rounded silhouette pose at 2x for smooth projection."""
    surface = pygame.Surface((640, 640), pygame.SRCALPHA)
    color = (174, 220, 161)
    def pt(x, y):
        return (round(x*2), round(y*2))
    def limb(points, width):
        points = [pt(x, y) for x, y in points]
        pygame.draw.lines(surface, color, False, points, width*2)
        for point in points:
            pygame.draw.circle(surface, color, point, width)
    hips = 160 + lean*8
    shoulders = 160 + lean*33
    head = 160 + lean*46
    for side in (-1, 1):
        limb([(hips+side*17, 209), (160+side*32+lean*8, 254), (160+side*49, 292)], 22)
        limb([(160+side*49, 292), (160+side*61, 295)], 18)
    limb([(shoulders, 134), (hips, 204)], 60)
    limb([(head, 95), (shoulders, 129)], 18)
    pygame.draw.circle(surface, color, pt(head, 74), 45)
    for side in (-1, 1):
        lift = (wave*side+1)/2
        limb([(shoulders+side*29, 136), (shoulders+side*58, 146-lift*33),
              (shoulders+side*(82-lift*7), 133-lift*76)], 18)
    return pygame.transform.smoothscale(surface, (320, 320))


class Renderer:
    def __init__(self):
        self.canvas = pygame.Surface((1280, 720)).convert()
        self.fonts = {}
        self.text_cache = OrderedDict()
        self.pepper = pepper_art().convert_alpha()
        # Keep original assets for the operator screen. Gameplay crops away the
        # illustration's asymmetric empty margins before centring/scaling it.
        self.hero_pepper = self.pepper.subsurface(self.pepper.get_bounding_rect()).copy()
        self.sprite_cache = OrderedDict()
        self.balloon_cache = OrderedDict()
        self.balloon = Balloon()
        self._play_identity = None
        self._previous_state = None
        self._previous_remaining = None
        self.balloon_rect = None
        self.background = self._background()
        self.small_pepper = pygame.transform.smoothscale(self.pepper, (58, 58))
        self.people = tuple(_sway_person(math.sin(index*math.tau/24)*.65,
                                        math.sin(index*math.tau/12)).convert_alpha()
                            for index in range(24))

    @property
    def impact_serial(self):
        """Monotonic visual impact counter; callers may use changes for audio."""
        return self.balloon.impact_serial

    @property
    def movement_energy(self):
        return self.balloon.movement_energy

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont("Arial", size, bold=bold)
        return self.fonts[key]

    def text(self, value, pos, size=24, color=INK, bold=False, anchor="topleft", surface=None):
        key = (str(value), size, color, bold)
        if key not in self.text_cache:
            self.text_cache[key] = self.font(size, bold).render(str(value), True, color)
            if len(self.text_cache) > 220:
                self.text_cache.popitem(last=False)
        rendered = self.text_cache[key]
        rect = rendered.get_rect(**{anchor: pos})
        (surface if surface is not None else self.canvas).blit(rendered, rect)
        return rect

    def _background(self):
        # Retained for operator/setup consumers; the game uses pure black.
        bg = pygame.Surface((1280, 720)).convert()
        bg.fill(CREAM)
        pygame.draw.rect(bg, (255, 240, 220), (0, 0, 1280, 8))
        pygame.draw.circle(bg, (255, 234, 208), (846, 322), 222)
        pygame.draw.circle(bg, (250, 224, 190), (846, 322), 222, 1)
        pygame.draw.circle(bg, (255, 240, 220), (846, 322), 193, 1)
        rng = random.Random(6)
        for _ in range(1700):
            x, y = rng.randrange(1280), rng.randrange(720)
            bg.set_at((x, y), (244, 229, 210))
        pygame.draw.line(bg, (224, 203, 180), (64, 87), (1216, 87), 1)
        pygame.draw.line(bg, (224, 203, 180), (64, 665), (1216, 665), 1)
        return bg

    def _sprite(self, size, angle):
        key = (max(8, round(size / 8)*8), round(angle / 3)*3)
        if key not in self.sprite_cache:
            self.sprite_cache[key] = pygame.transform.rotozoom(
                self.hero_pepper, key[1], key[0]/max(self.hero_pepper.get_size()))
            if len(self.sprite_cache) > 32:
                self.sprite_cache.popitem(last=False)
        self.sprite_cache.move_to_end(key)
        return self.sprite_cache[key]

    def _hero(self, size, angle=0., center=(640, 330)):
        sprite = self._sprite(size, angle)
        rect = sprite.get_rect(center=center)
        self.canvas.blit(sprite, rect)
        return rect

    def _balloon_sprite(self, heat):
        # Cap the *transformed* footprint, leaving travel space even at full heat.
        # Quantisation and a small LRU keep transforms and memory bounded.
        sx, sy = self.balloon.stretch
        key = (round((225+heat*120)/8)*8, round(self.balloon.angle/3)*3,
               round(sx*20), round(sy*20))
        if key not in self.balloon_cache:
            base = self._sprite(key[0], key[1])
            width, height = max(1, round(base.get_width()*key[2]/20)), max(1, round(base.get_height()*key[3]/20))
            fit = min(1., 390/width, 330/height)
            size = (max(1, round(width*fit)), max(1, round(height*fit)))
            self.balloon_cache[key] = pygame.transform.scale(base, size)
            if len(self.balloon_cache) > 24:
                self.balloon_cache.popitem(last=False)
        self.balloon_cache.move_to_end(key)
        return self.balloon_cache[key]

    def _playing_balloon(self, game, now, heat):
        identity = (id(game), getattr(game, "round_number", None))
        new_round = (self._previous_state != "playing" or self._play_identity != identity
                     or (self._previous_remaining is not None and game.remaining > self._previous_remaining+.1))
        if new_round:
            self.balloon.reset(now)
        self._play_identity = identity
        sprite = self._balloon_sprite(heat)
        self.balloon.update(now,
            motion_timestamp=getattr(game, "motion_timestamp", None) if game.player_visible else None,
            motion_x=getattr(game, "motion_x", 0.), motion_y=getattr(game, "motion_y", 0.),
            energy=getattr(game, "motion_energy", 0.),
            half_width=sprite.get_width()/2+2, half_height=sprite.get_height()/2+2)
        sprite = self._balloon_sprite(heat)
        # Growth or a collision can change the footprint during this frame.
        self.balloon.constrain(sprite.get_width()/2+2, sprite.get_height()/2+2, now)
        self.balloon_rect = sprite.get_rect(center=(round(self.balloon.x), round(self.balloon.y)))
        previous_clip = self.canvas.get_clip()
        left, top, right, bottom = PLAY_BOUNDS
        self.canvas.set_clip(pygame.Rect(left, top, right-left, bottom-top))
        self.canvas.blit(sprite, self.balloon_rect)
        self.canvas.set_clip(previous_clip)

    @staticmethod
    def demo_start_hit(point, state):
        return bool(point is not None and state in ("idle", "won", "timeout", "clear")
                    and pygame.Rect(DEMO_START_RECT).collidepoint(point))

    def _start_prompt(self, label):
        box = pygame.Rect(DEMO_START_RECT)
        self.text(label, box.center, 25, LIGHT_TEXT, True, "center")

    def _arrow(self, center, direction, active):
        x, y = center
        color = HOT_TEXT if active else (130, 130, 130)
        pygame.draw.line(self.canvas, color, (x-direction*19, y), (x+direction*19, y), 9)
        pygame.draw.polygon(self.canvas, color, [(x+direction*35, y),
                            (x+direction*8, y-23), (x+direction*8, y+23)])

    def _how_to(self, game, now, demo):
        instructions = game.state == "instructions"
        self.text("HOW TO PLAY" if instructions else "How HOT are you", (640, 45), 18, HOT_TEXT, True, "center")
        self.text("Sway or wave your hands", (640, 105), 52, LIGHT_TEXT, True, "center")
        self.text("Your moves make the chilli grow.", (640, 161), 26, SOFT_TEXT, False, "center")
        phase = math.sin(now*1.8)
        person = self.people[int(now*1.8/math.tau*24) % len(self.people)]
        self.canvas.blit(person, person.get_rect(center=(388, 328)))
        self._arrow((190, 330), -1, phase < -.12)
        self._arrow((586, 330), 1, phase > .12)
        # A restrained connector makes the physical action -> chilli response
        # clear without adding another paragraph of instructions.
        pygame.draw.line(self.canvas, (205, 178, 145), (669, 330), (721, 330), 4)
        pygame.draw.polygon(self.canvas, (205, 178, 145), [(734, 330), (717, 319), (717, 341)])
        # Both sway directions earn growth in the real game. A gradual loop
        # teaches that cumulative response instead of shrinking on a left lean.
        teaching_growth = (now % 4.0) / 4.0
        self._hero(175 + teaching_growth*110, phase*5, (928, 331))
        self.text("Arrows / A D: sway" if demo else "SWAY OR WAVE",
                  (388, 505), 19, SOFT_TEXT, True, "center")
        if demo:
            self.text("Up Down / W S: wave", (388, 532), 19, SOFT_TEXT, True, "center")
        self.text("WATCH IT GROW", (928, 505), 19, SOFT_TEXT, True, "center")
        self.text(f"Grow it to full size in {game.config.round_seconds:g} seconds.",
                  (640, 577), 30, LIGHT_TEXT, True, "center")
        if instructions:
            self.text(getattr(game, "message", "") or "Your turn in a moment",
                      (640, 644), 25, SOFT_TEXT, False, "center")
        elif demo:
            self._start_prompt("Press Enter or Space to start")
        else:
            self._start_prompt("Player found. Get ready!" if game.player_visible else "Step into the play area")

    def _result(self, game, now, demo):
        state = game.state
        heat = max(0., min(1., game.heat))
        if state == "won":
            self.text("You're on fire!", (640, 75), 62, HOT_TEXT, True, "center")
            self._hero(345+math.sin(now*9)*15, math.sin(now*7)*10, (640, 342+math.sin(now*5)*13))
            bottom = "Certified spicy!"
        elif state == "timeout":
            self.text("Nice moves!", (640, 75), 60, LIGHT_TEXT, True, "center")
            self._hero(240+heat*110, math.sin(now*1.8)*3, (640, 342))
            bottom = "Give it another go!"
        else:
            self.text("Ready for the next round?", (640, 105), 52, LIGHT_TEXT, True, "center")
            self._hero(330, math.sin(now*1.8)*3, (640, 344))
            bottom = "Let's turn up the heat again." if demo else "Step out of the play area to reset."
        if state in ("won", "timeout"):
            self.text(heat_rating(heat, state == "won").upper(), (640, 134), 24, HOT_TEXT, True, "center")
            elapsed, best = getattr(game, "result_elapsed", None), getattr(game, "best_time", None)
            parts = []
            if state == "won" and elapsed is not None:
                parts.append(f"{'New record! ' if getattr(game, 'new_record', False) else ''}{elapsed:.1f}s")
            if best is not None:
                parts.append(f"Best: {best:.1f}s")
            if parts:
                self.text("   |   ".join(parts), (640, 555), 25, SOFT_TEXT, True, "center")
            if demo:
                self._start_prompt("Press Enter or Space to play again")
            else:
                self.text(bottom, (640, 640), 34, LIGHT_TEXT, True, "center")
            return
        if demo:
            self.text(bottom, (640, 568), 30, LIGHT_TEXT, True, "center")
            self._start_prompt("Press Enter or Space to play again")
        else:
            self.text(bottom, (640, 640), 34, LIGHT_TEXT, True, "center")

    def draw(self, game, now, *, demo=False, muted=False, diagnostics=False,
             snapshot=None, render_fps=0., zone=(.15, .85)):
        self.canvas.fill(BLACK)
        state = game.state
        heat = max(0., min(1., game.heat))
        if state != "playing" and self._previous_state == "playing":
            self.balloon.reset(now)
            self._play_identity = None
            self.balloon_rect = None
        if state in ("idle", "instructions"):
            self._how_to(game, now, demo)
        elif state == "playing":
            self._playing_balloon(game, now, heat)
            seconds = max(0, math.ceil(game.remaining))
            self.text(f"{seconds:02d}s", (1216, 69), 54,
                      HOT_TEXT if game.remaining <= 3 else LIGHT_TEXT, True, "topright")
            self.text(encouragement(heat, game.player_visible), (640, 650), 43, LIGHT_TEXT, True, "center")
        elif state == "countdown":
            self._hero(285, math.sin(now*2)*2, (640, 360))
            self.text(str(game.countdown or 1), (640, 108), 104, HOT_TEXT, True, "center")
            self.text("Get ready to move", (640, 650), 38, LIGHT_TEXT, True, "center")
        elif state in ("won", "timeout", "clear"):
            self._result(game, now, demo)
        else:
            self.text("Finding your camera...", (640, 128), 52, LIGHT_TEXT, True, "center")
            self._hero(320, 0, (640, 370))
            self.text("Please wait a moment.", (640, 640), 30, SOFT_TEXT, False, "center")
        if diagnostics:
            self._diagnostics(snapshot, render_fps, game, zone)
        self._previous_state = state
        self._previous_remaining = game.remaining if state == "playing" else None
        return self.canvas

    def _diagnostics(self, snapshot, fps, game, zone):
        panel = pygame.Surface((472, 430), pygame.SRCALPHA)
        panel.fill((29, 28, 25, 245))
        self.canvas.blit(panel, (58, 100))
        self.text("OPERATOR VIEW", (76, 112), 20, (255, 240, 220), True)
        self.text(f"Display {fps:.1f} fps  |  Pose {getattr(snapshot, 'fps', 0):.1f} fps", (76, 145), 16, (230, 230, 220))
        preview = getattr(snapshot, "preview", None)
        if preview is not None:
            height, width = preview.shape[:2]
            view = pygame.image.frombuffer(preview.tobytes(), (width, height), "RGB")
            view = pygame.transform.scale(view, (320, 240))
            self.canvas.blit(view, (76, 175))
            pygame.draw.rect(self.canvas, (255, 205, 90), (76+zone[0]*320, 175, (zone[1]-zone[0])*320, 240), 2)
            points = getattr(snapshot, "landmarks", ())
            for index in (11, 12, 23, 24):
                if index < len(points) and points[index][0] >= 0:
                    x, y = points[index][:2]
                    pygame.draw.circle(self.canvas, (100, 255, 160), (int(76+x*320), int(175+y*240)), 4)
        else:
            self.text("Camera preview appears here", (76, 210), 18, (200, 200, 190))
        status = getattr(snapshot, "status", "Keyboard demo; no camera in use")
        words, line, y = str(status).split(), "", 425
        for word in words:
            if self.font(15).size(line + word)[0] > 430:
                self.text(line, (76, y), 15, (255, 219, 170)); y += 19; line = ""
            line += word + " "
            if y > 463:
                break
        self.text(line, (76, y), 15, (255, 219, 170))
        self.text("F2 close   C settings   F fullscreen   M sound   ESC menu", (76, 502), 14, (230, 230, 220))
