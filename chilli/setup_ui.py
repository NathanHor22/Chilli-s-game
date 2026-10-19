"""Camera setup screen; consumes snapshots and never opens a device itself."""
from __future__ import annotations

import pygame

from .render import CREAM, GREEN, INK, MUTED, RED


class SetupScreen:
    def __init__(self, renderer):
        self.renderer = renderer
        self.actions = []
        self.scroll = 0

    def click(self, point):
        if point is not None:
            for rect, action, enabled in reversed(self.actions):
                if enabled and rect.collidepoint(point):
                    return action
        return None

    def _button(self, label, rect, action, *, enabled=True, primary=False):
        surface = self.renderer.canvas
        box = pygame.Rect(rect)
        fill = RED if primary else (255, 253, 247)
        if not enabled:
            fill = (229, 216, 199)
        pygame.draw.rect(surface, fill, box, border_radius=12)
        if not primary and enabled:
            pygame.draw.rect(surface, (222, 202, 179), box, 1, border_radius=12)
        self.renderer.text(label, box.center, 18, CREAM if primary and enabled else INK if enabled else MUTED,
                           True, "center")
        self.actions.append((box, action, enabled))

    def _fit_text(self, value, max_width, size=18, bold=False):
        value = str(value)
        if self.renderer.font(size, bold).size(value)[0] <= max_width:
            return value
        while value and self.renderer.font(size, bold).size(value + "...")[0] > max_width:
            value = value[:-1]
        return value + "..."

    def draw(self, snapshot, discovery, selected, *, can_start=False, camera_index=0,
             camera_backend=0, notice="", zone=(.15, .85), now=0.):
        r, s = self.renderer, self.renderer.canvas
        s.fill(CREAM)
        self.actions = []
        s.blit(r.small_pepper, (55, 17))
        r.text("CHILLI SHIMMY", (116, 36), 23, RED, True)
        r.text("SET UP YOUR SPACE", (1216, 46), 16, MUTED, True, "midright")
        pygame.draw.line(s, (224, 203, 180), (64, 87), (1216, 87))
        r.text("A quick camera check.", (64, 104), 36, INK, True)
        r.text("Find your webcam. Check your framing. Then bring the heat.", (65, 148), 18, MUTED)

        viewport = pygame.Rect(64, 187, 720, 390)
        pygame.draw.rect(s, (46, 43, 36), viewport, border_radius=16)
        preview = getattr(snapshot, "preview", None)
        fresh = bool(can_start)
        if preview is not None and fresh:
            height, width = preview.shape[:2]
            image = pygame.image.frombuffer(preview.tobytes(), (width, height), "RGB")
            factor = min(viewport.width / width, viewport.height / height)
            size = (max(1, int(width*factor)), max(1, int(height*factor)))
            image = pygame.transform.scale(image, size)
            box = image.get_rect(center=viewport.center)
            s.blit(image, box)
            zone_rect = pygame.Rect(box.x+zone[0]*box.width, box.y+12,
                                    (zone[1]-zone[0])*box.width, box.height-24)
            pygame.draw.rect(s, (255, 219, 120), zone_rect, 2, border_radius=8)
            points = getattr(snapshot, "landmarks", ())
            for a, b in ((11, 12), (11, 23), (12, 24), (23, 24)):
                if len(points) > max(a, b) and points[a][0] >= 0 and points[b][0] >= 0:
                    start = (int(box.x+points[a][0]*box.width), int(box.y+points[a][1]*box.height))
                    end = (int(box.x+points[b][0]*box.width), int(box.y+points[b][1]*box.height))
                    pygame.draw.line(s, (103, 255, 166), start, end, 3)
                    pygame.draw.circle(s, (103, 255, 166), start, 5)
        else:
            # A simple camera glyph remains legible if the webcam is absent.
            pygame.draw.rect(s, (124, 117, 102), (379, 304, 90, 62), 3, border_radius=12)
            pygame.draw.circle(s, (124, 117, 102), (424, 335), 17, 3)
            r.text("Waiting for a live picture", (424, 400), 25, (244, 230, 208), True, "center")
            r.text("Choose a source on the right, or connect a webcam.", (424, 440), 17,
                   (202, 192, 174), anchor="center")
        pygame.draw.rect(s, (29, 34, 28), (80, 201, 132, 30), border_radius=15)
        pygame.draw.circle(s, (125, 221, 140) if fresh else (235, 179, 98), (97, 216), 4)
        r.text("LIVE PREVIEW" if fresh else "NO PICTURE", (111, 216), 12, CREAM, True, "midleft")

        pygame.draw.rect(s, (255, 251, 243), (812, 104, 404, 473), border_radius=16)
        r.text("CAMERA SOURCE", (832, 123), 18, INK, True)
        cameras = tuple(getattr(discovery, "cameras", ()))
        self.scroll = max(0, min(self.scroll, max(0, len(cameras)-4)))
        if cameras:
            for row, camera in enumerate(cameras[self.scroll:self.scroll+4]):
                box = pygame.Rect(832, 159+row*53, 364, 48)
                is_selected = selected is not None and camera == selected
                pygame.draw.rect(s, (255, 228, 207) if is_selected else (249, 241, 228), box, border_radius=9)
                if is_selected:
                    pygame.draw.rect(s, RED, box, 2, border_radius=9)
                r.text(self._fit_text(camera.name, 328, 18, True), (847, box.y+5), 18, INK, True)
                backend_name = {700: "DirectShow", 1400: "Media Foundation", 0: "Auto"}.get(camera.backend, str(camera.backend))
                r.text(f"Source {camera.index}  /  {backend_name}", (847, box.y+28), 12, MUTED)
                self.actions.append((box, ("camera", camera), True))
        else:
            r.text("Looking for connected webcams..." if getattr(discovery, "scanning", False) else "No webcams found yet.",
                   (832, 177), 18, MUTED)
            r.text("Connect one, then press Refresh.", (832, 213), 17, MUTED)
            r.text("You can also try a source number below.", (832, 248), 16, MUTED)
        if len(cameras) > 4:
            r.text(f"{self.scroll+1}-{min(self.scroll+4,len(cameras))} of {len(cameras)}  /  scroll for more", (832, 375), 13, MUTED)
        self._button("Refreshing..." if getattr(discovery, "scanning", False) else "Refresh webcams", (832, 404, 364, 42), ("refresh", None))
        r.text("OR TRY A SOURCE NUMBER", (832, 462), 13, MUTED, True)
        self._button("-", (832, 489, 45, 43), ("index", -1), enabled=camera_index > 0)
        r.text(str(camera_index), (917, 511), 23, INK, True, "center")
        self._button("+", (956, 489, 45, 43), ("index", 1), enabled=camera_index < 63)
        self._button("Reconnect", (1012, 489, 184, 43), ("reconnect", None))
        scan_status = getattr(discovery, "status", "New webcams appear automatically.")
        r.text(self._fit_text(scan_status, 364, 14), (832, 548), 14, MUTED)

        sample = getattr(snapshot, "sample", None)
        visible = fresh and sample is not None and sample.present
        r.text("Camera ready" if fresh else "Camera not ready", (65, 589), 18, GREEN if fresh else RED, True)
        r.text("Body detected" if visible else "Keep shoulders and hips inside the guide", (242, 589), 17, GREEN if visible else MUTED)
        r.text(f"{getattr(snapshot, 'fps', 0):.0f} tracking fps", (782, 592), 15, MUTED, anchor="topright")
        status = notice or getattr(snapshot, "status", "Choose a camera to begin")
        r.text(self._fit_text(status, 720, 16), (65, 619), 16, MUTED)
        self._button("Keyboard demo", (64, 650, 248, 42), ("demo", None))
        r.text("No webcam needed", (330, 671), 16, MUTED, anchor="midleft")
        self._button("Start game" if can_start else "Waiting for camera", (832, 598, 364, 54), ("start", None),
                     enabled=can_start, primary=True)
        r.text("ENTER start   /   K demo   /   F5 refresh", (1014, 680), 14, MUTED, anchor="center")
        return s


def canvas_position(position, screen_size):
    """Map window clicks into the letterboxed 1280x720 canvas."""
    width, height = screen_size
    factor = min(width/1280, height/720)
    if factor <= 0:
        return None
    x = (position[0] - (width-1280*factor)/2) / factor
    y = (position[1] - (height-720*factor)/2) / factor
    return (x, y) if 0 <= x < 1280 and 0 <= y < 720 else None
