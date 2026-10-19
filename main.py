"""Run How HOT are you. Use --demo --windowed to try it without a camera."""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "2")


def arguments():
    from chilli import __version__
    parser = argparse.ArgumentParser(description="How HOT are you - a motion-controlled projector game")
    parser.add_argument("--version", action="version", version=f"How HOT are you {__version__}")
    parser.add_argument("--demo", action="store_true", help="Use keyboard mode when Start is selected; no webcam needed")
    parser.add_argument("--windowed", action="store_true", help="Start in a movable window")
    parser.add_argument("--mute", action="store_true", help="Start with sound muted")
    parser.add_argument("--config", type=Path, help="Read an alternate JSON configuration")
    parser.add_argument("--camera", type=int, help="Override camera index")
    parser.add_argument("--display", type=int, help="Override projector/monitor index")
    parser.add_argument("--self-test", action="store_true", help="Check graphics, dependencies and model without a camera")
    parser.add_argument("--report", type=Path, help="Write self-test results as JSON")
    parser.add_argument("--screenshot", type=Path, help="Render a preview PNG without opening a window")
    parser.add_argument("--scene", choices=["menu", "setup", "idle", "instructions", "countdown", "playing", "won", "timeout", "clear", "error"], default="menu")
    return parser.parse_args()


def configure_logging():
    from chilli.config import app_root
    directory = app_root() / "logs"
    try:
        directory.mkdir(exist_ok=True)
        handler = logging.FileHandler(directory / "chilli.log", encoding="utf-8", mode="w")
    except OSError:
        handler = logging.FileHandler(Path(tempfile.gettempdir()) / "how-hot-are-you.log", encoding="utf-8", mode="w")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")


def preview_game(scene, config):
    return SimpleNamespace(state=scene, heat=1. if scene == "won" else (.64 if scene in ("playing", "timeout") else 0.),
        remaining=0 if scene == "timeout" else (4.2 if scene in ("playing", "won") else config.game.round_seconds),
        countdown=3, sway=.3 if scene == "playing" else 0., player_visible=scene != "idle",
        message="", round_number=1, config=config.game, motion_x=.6, motion_y=-.4,
        motion_energy=.7 if scene == "playing" else 0., motion_timestamp=4.25,
        best_time=5.8, new_record=scene == "won", result_elapsed=5.8 if scene == "won" else None)


def write_report(report, path):
    payload = json.dumps(report, indent=2)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    if sys.stdout:
        print(payload)


def self_test(config, report_path=None):
    """Exercise actual native dependencies, drawing and the bundled model, not a webcam."""
    import importlib.metadata
    import pygame
    from chilli.render import Renderer
    from chilli import __version__
    report = {"ok": False, "version": __version__, "python": sys.version.split()[0], "frozen": bool(getattr(sys, "frozen", False)), "checks": {}}
    try:
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((1280, 720))
        renderer = Renderer()
        from chilli.menu_ui import MenuScreen
        menu = MenuScreen(renderer)
        menu.draw()
        report["checks"]["main_menu"] = "Start, Settings, Quit rendered"
        for state in ("idle", "instructions", "countdown", "playing", "won", "timeout", "clear", "error"):
            renderer.draw(preview_game(state, config), 4.25, demo=True)
        report["checks"]["all_screens"] = "passed"
        from chilli.audio import Audio
        audio = Audio(enabled=False, volume=config.audio.volume)
        if not audio.available:
            raise RuntimeError("Synthesized audio could not initialize with the dummy device")
        report["checks"]["audio_cues"] = "passed (dummy audio device)"
        from chilli.game import Game
        from chilli.demo import DemoController
        for label, keys in (("sway", (pygame.K_LEFT, pygame.K_RIGHT)),
                            ("hands", (pygame.K_UP, pygame.K_DOWN))):
            game = Game(config.game)
            demo = DemoController(game)
            demo.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN), 100.)
            demo.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_RETURN), 100.)
            won, held = False, None
            seen_states = {game.state}
            simulation_seconds = config.game.instructions_seconds + config.game.countdown_seconds + config.game.round_seconds + 2
            for i in range(1, math.ceil(simulation_seconds*30)):
                now = 100.+i / 30.
                direction = keys[(i//15) % 2] if game.state == "playing" else None
                if direction != held:
                    if held is not None:
                        demo.handle_event(pygame.event.Event(pygame.KEYUP, key=held), now)
                    if direction is not None:
                        demo.handle_event(pygame.event.Event(pygame.KEYDOWN, key=direction), now)
                    held = direction
                game.update(now, demo.update(now, 1/30.))
                seen_states.add(game.state)
                if game.state in ("instructions", "countdown"):
                    if game.heat != 0 or game.remaining != config.game.round_seconds:
                        raise RuntimeError("Preparation used gameplay time or awarded heat")
                if game.state == "playing" and i % 3 == 0:
                    renderer.draw(game, now, demo=True)
                if game.state == "won":
                    won = True
                    break
            if not won:
                raise RuntimeError(f"Keyboard {label} events did not complete a round")
            if config.game.instructions_seconds > 0 and "instructions" not in seen_states:
                raise RuntimeError("The how-to-play screen was skipped")
            report["checks"][f"simulated_{label}_round"] = "won"
        report["checks"]["tutorial_flow"] = "instructions and countdown preserve the full round timer"
        report["checks"]["keyboard_events"] = "Sway-only and hand-only arrow key events each reached a win"
        import cv2
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        report["versions"] = {name: importlib.metadata.version(name) for name in ("pygame", "mediapipe", "numpy", "opencv-contrib-python", "cv2-enumerate-cameras")}
        from chilli.cameras import DiscoverySnapshot, enumerate_connected_cameras
        from chilli.setup_ui import SetupScreen
        from chilli.tracking import TrackingSnapshot
        sources = enumerate_connected_cameras()
        setup_screen = SetupScreen(renderer)
        setup_screen.draw(TrackingSnapshot(), DiscoverySnapshot(cameras=sources), None)
        report["checks"]["camera_setup"] = f"rendered; enumerated {len(sources)} camera sources without opening video"
        model = Path(config.tracking.model_path)
        if not model.is_file():
            raise FileNotFoundError(f"Model missing: {model}. Run setup.ps1 first.")
        options = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model), delegate=python.BaseOptions.Delegate.CPU),
            running_mode=vision.RunningMode.VIDEO, num_poses=1, output_segmentation_masks=False)
        with vision.PoseLandmarker.create_from_options(options) as detector:
            frame = cv2.cvtColor(np.zeros((480, 640, 3), dtype=np.uint8), cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            start = time.perf_counter()
            for i in range(5):
                detector.detect_for_video(image, 100+i*100)
            report["checks"]["model_blank_frame_ms"] = round((time.perf_counter()-start)*200, 2)
        report["checks"]["camera"] = "not opened; real player and venue testing still required"
        report["ok"] = True
    except Exception as exc:
        logging.exception("Self-test failed")
        report["error"] = str(exc)
    finally:
        pygame.quit()
    write_report(report, report_path)
    return 0 if report["ok"] else 1


def screenshot(config, path, scene):
    import pygame
    from chilli.render import Renderer
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1280, 720))
    renderer = Renderer()
    if scene == "menu":
        from chilli.menu_ui import MenuScreen
        canvas = MenuScreen(renderer).draw()
    elif scene == "setup":
        from chilli.setup_ui import SetupScreen
        from chilli.tracking import TrackingSnapshot
        from chilli.cameras import DiscoverySnapshot
        canvas = SetupScreen(renderer).draw(TrackingSnapshot(), DiscoverySnapshot(), None,
            camera_index=config.tracking.camera_index)
    else:
        canvas = renderer.draw(preview_game(scene, config), 4.25, demo=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(canvas, str(path))
    pygame.quit()
    return 0


def play(config, args):
    import pygame
    from chilli.audio import Audio
    from chilli.game import Game
    from chilli.demo import DemoController
    from chilli.operator import CameraSetup
    from chilli.render import Renderer
    from chilli.menu_ui import MenuScreen, MENU_ACTIONS
    from chilli.setup_ui import SetupScreen, canvas_position
    from chilli.records import ResultStore
    from chilli.config import app_root

    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("How HOT are you")
    displays = pygame.display.get_desktop_sizes()
    index = config.display.index
    if index >= len(displays):
        logging.warning("Display %s unavailable; using display 0", index)
        index = 0
    fullscreen = config.display.fullscreen and not args.windowed
    page = "menu"
    mode = "demo" if args.demo else "camera"
    menu_selected = 0

    def make_window():
        if fullscreen:
            screen = pygame.display.set_mode(displays[index], pygame.FULLSCREEN, display=index)
        else:
            dw, dh = displays[index]
            factor = min(1., (dw*.9)/config.display.width, (dh*.9)/config.display.height)
            size = (max(320, int(config.display.width*factor)), max(180, int(config.display.height*factor)))
            screen = pygame.display.set_mode(size, pygame.RESIZABLE, display=index)
        pygame.mouse.set_visible(page != "game" or not fullscreen)
        return screen

    screen = make_window()
    renderer = Renderer()
    pygame.display.set_icon(pygame.transform.smoothscale(renderer.pepper, (48, 48)))
    audio = Audio(config.audio.enabled and not args.mute, config.audio.volume)
    game = Game(config.game)
    record_root = Path(args.config).parent if getattr(args, "config", None) else app_root()
    records = ResultStore(record_root / "results.json")
    game.best_time = records.best(mode, game.config)
    game.new_record, game.result_elapsed = False, None
    demo = DemoController(game)
    menu_screen = MenuScreen(renderer)
    setup_screen = SetupScreen(renderer)
    camera_setup = None
    clock = pygame.time.Clock()
    running, diagnostics = True, False
    last_state, last_countdown = game.state, 0
    last_status = ""
    unsaved_choice = None

    def clear_result():
        game.best_time = records.best(mode, game.config)
        game.new_record, game.result_elapsed = False, None

    def ensure_camera():
        nonlocal camera_setup
        if camera_setup is None:
            camera_setup = CameraSetup(config, getattr(args, "config", None))
        camera_setup.start()

    def open_menu(now):
        nonlocal page, menu_selected, diagnostics
        page, menu_selected, diagnostics = "menu", 0, False
        game.reset(now)
        clear_result()
        if camera_setup is not None:
            camera_setup.suspend()
        pygame.mouse.set_visible(True)

    def open_settings(now):
        nonlocal page, diagnostics
        page, diagnostics = "settings", False
        game.reset(now)
        clear_result()
        ensure_camera()
        pygame.mouse.set_visible(True)

    def start_game(now):
        nonlocal page, demo, diagnostics
        page, diagnostics = "game", False
        clear_result()
        if mode == "demo":
            if camera_setup is not None:
                camera_setup.suspend()
            demo = DemoController(game)
            demo.reset(now)
        else:
            ensure_camera()
            camera_setup.session.set_preview_enabled(False)
            game.begin(now)
        pygame.mouse.set_visible(not fullscreen)

    def menu_action(action, now):
        nonlocal running
        if action == "start":
            start_game(now)
        elif action == "settings":
            open_settings(now)
        elif action == "quit":
            running = False

    def setup_action(action, now):
        nonlocal mode, unsaved_choice
        if action is None:
            return
        name, value = action
        if name == "camera":
            camera_setup.select(value)
        elif name == "index":
            camera_setup.manual(config.tracking.camera_index+value)
        elif name == "reconnect":
            camera_setup.reconnect()
        elif name == "refresh":
            camera_setup.refresh()
        elif name == "save" and camera_setup.can_start(now):
            choice = (config.tracking.camera_index, config.tracking.camera_backend, config.tracking.camera_path)
            if choice != unsaved_choice:
                try:
                    camera_setup.save()
                except (OSError, ValueError) as exc:
                    logging.warning("Camera choice could not be saved: %s", exc)
                    unsaved_choice = choice
                    camera_setup.notice = "Could not save. Press Save & Back again to use this camera for this session."
                    return
            mode = "camera"
            open_menu(now)
        elif name == "demo":
            mode = "demo"
            open_menu(now)
        elif name == "back":
            open_menu(now)

    try:
        while running:
            dt = min(clock.tick(config.display.fps)/1000., .1)
            now = time.monotonic()
            if camera_setup is not None:
                source_changed = camera_setup.update(now)
                if (page == "game" and mode == "camera"
                        and game.state in ("countdown", "playing")
                        and (source_changed or not camera_setup.snapshot.ready)):
                    open_settings(now)
            for event in pygame.event.get():
                if not running:
                    break
                if event.type == pygame.QUIT:
                    running = False
                    continue
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if page == "menu":
                            running = False
                        else:
                            open_menu(now)
                        continue
                    if event.key == pygame.K_f:
                        fullscreen = not fullscreen
                        screen = make_window()
                        continue
                    if event.key == pygame.K_m:
                        audio.toggle()
                        continue
                    if event.key == pygame.K_c:
                        open_settings(now)
                        continue
                if page == "menu":
                    if event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_UP, pygame.K_w):
                            menu_selected = (menu_selected-1) % len(MENU_ACTIONS)
                        elif event.key in (pygame.K_DOWN, pygame.K_s):
                            menu_selected = (menu_selected+1) % len(MENU_ACTIONS)
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                            menu_action(MENU_ACTIONS[menu_selected], now)
                    elif event.type == pygame.MOUSEMOTION:
                        action = menu_screen.click(canvas_position(event.pos, screen.get_size()))
                        if action is not None:
                            menu_selected = MENU_ACTIONS.index(action)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        menu_action(menu_screen.click(canvas_position(event.pos, screen.get_size())), now)
                    continue
                if page == "settings":
                    if event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            setup_action(("save", None), now)
                        elif event.key == pygame.K_k:
                            setup_action(("demo", None), now)
                        elif event.key == pygame.K_F5:
                            setup_action(("refresh", None), now)
                        elif event.key == pygame.K_r:
                            setup_action(("reconnect", None), now)
                        elif event.key in (pygame.K_UP, pygame.K_DOWN):
                            camera_setup.cycle(-1 if event.key == pygame.K_UP else 1)
                            if camera_setup.selected in camera_setup.inventory.cameras:
                                selected_row = camera_setup.inventory.cameras.index(camera_setup.selected)
                                setup_screen.scroll = max(0, selected_row-3)
                    elif event.type == pygame.MOUSEWHEEL:
                        setup_screen.scroll -= event.y
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        setup_action(setup_screen.click(canvas_position(event.pos, screen.get_size())), now)
                    continue
                if mode == "demo":
                    demo.handle_event(event, now)
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        if mode == "demo":
                            demo.reset(now)
                        else:
                            game.begin(now)
                    elif event.key == pygame.K_F2 or (event.key == pygame.K_d and mode == "camera"):
                        diagnostics = not diagnostics
                        if camera_setup is not None:
                            camera_setup.session.set_preview_enabled(diagnostics)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    point = canvas_position(event.pos, screen.get_size())
                    if mode == "demo" and renderer.demo_start_hit(point, game.state):
                        demo.reset(now)
            if not running:
                break
            snapshot = camera_setup.snapshot if camera_setup is not None else None
            if page == "game":
                if mode == "demo":
                    game.update(now, demo.update(now, dt), camera_ready=True)
                else:
                    if snapshot.status != last_status:
                        logging.info("Camera: %s", snapshot.status)
                        last_status = snapshot.status
                    game.update(now, snapshot.sample, camera_ready=snapshot.ready)
                    if game.state == "error":
                        open_settings(now)
                if game.state == "countdown" and (last_state != "countdown" or last_countdown != game.countdown):
                    audio.play("tick")
                if game.state != last_state:
                    logging.info("Game state: %s; heat %.3f", game.state, game.heat)
                    if game.state == "playing":
                        clear_result()
                        audio.play("go")
                    elif game.state in ("won", "timeout"):
                        if game.state == "won":
                            game.result_elapsed = game.config.round_seconds-game.remaining
                            game.new_record = records.record_win(mode, game.config, game.result_elapsed)
                            game.best_time = records.best(mode, game.config)
                        audio.play(game.state)
            last_state, last_countdown = game.state, game.countdown
            if page == "menu":
                canvas = menu_screen.draw(selected=menu_selected)
            elif page == "settings":
                canvas = setup_screen.draw(camera_setup.snapshot, camera_setup.inventory, camera_setup.selected,
                    can_start=camera_setup.can_start(now), camera_index=config.tracking.camera_index,
                    camera_backend=config.tracking.camera_backend, notice=camera_setup.notice,
                    zone=(config.tracking.zone_left, config.tracking.zone_right), now=now)
            else:
                canvas = renderer.draw(game, now, demo=mode == "demo", muted=not audio.enabled or not audio.available,
                    diagnostics=diagnostics, snapshot=snapshot if mode == "camera" else None, render_fps=clock.get_fps(),
                    zone=(config.tracking.zone_left, config.tracking.zone_right))
            audio.update(now, playing=page == "game" and game.state == "playing", heat=game.heat,
                energy=renderer.movement_energy, impact_serial=renderer.impact_serial)
            width, height = screen.get_size()
            factor = min(width/1280, height/720)
            target = (max(1, round(1280*factor)), max(1, round(720*factor)))
            screen.fill((0, 0, 0))
            output = canvas if target == (1280, 720) else pygame.transform.scale(canvas, target)
            screen.blit(output, ((width-target[0])//2, (height-target[1])//2))
            pygame.display.flip()
    finally:
        if camera_setup is not None:
            camera_setup.stop()
        pygame.quit()
    return 0


def main():
    args = arguments()
    if args.self_test or args.screenshot:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    from chilli.config import load_config
    config = load_config(args.config)
    configure_logging()
    if args.camera is not None:
        if args.camera < 0:
            raise ValueError("Camera index must be nonnegative")
        config.tracking.camera_index = args.camera
        config.tracking.camera_backend = 0
        config.tracking.camera_path = ""
    if args.display is not None:
        if args.display < 0:
            raise ValueError("Display index must be nonnegative")
        config.display.index = args.display
    if args.self_test:
        return self_test(config, args.report)
    if args.screenshot:
        return screenshot(config, args.screenshot, args.scene)
    return play(config, args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("How HOT are you could not start")
        if sys.stderr:
            print(f"How HOT are you could not start: {exc}", file=sys.stderr)
        if getattr(sys, "frozen", False) and sys.platform == "win32" and "--self-test" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"How HOT are you could not start.\n\n{exc}\n\nCheck config.json and logs/chilli.log.", "How HOT are you", 0x10)
        raise SystemExit(1)
