# How HOT are you

A one-player, 10-second webcam game for a landscape projector. In version **1.4.1**, sway your body or wave either hand in any direction to grow a balloon-like chilli. Reach maximum size before time runs out. One hand, both hands, or body movement alone can win; there are no bubbles to collect, targets to hit, or gesture patterns to memorize.

Every round begins with a dedicated how-to screen. During play, the screen focuses on the moving chilli, the timer, and one short encouragement such as “Bring the heat!” or “Scorching moves!” The chilli bounces, squashes, and stretches in response to movement. These playful effects are visual feedback: a bounce does not earn extra heat, and standing still does not keep scoring. The how-to screen and countdown do not use any of the 10 seconds of gameplay.

The game uses Python, OpenCV, MediaPipe Pose Landmarker Lite, and Pygame. The round uses a pure black background with the red chilli and bright text for projection onto a wall. Tutorial, countdown, results, and window letterboxing also use black. Decorative sparks, confetti, and filled prompt backgrounds are removed; the chilli still bounces, squashes, and stretches with sound. The tutorial retains its movement demonstration. The title menu and camera settings use cream. Optional synthesized sound and a keyboard demo are included. It runs locally after setup; the application does not record or upload webcam images. Internet access is needed to install dependencies and download the model, not to play.

MediaPipe 0.10.35 can attempt to send library performance/usage metrics when internet access is available; the webcam images are processed on the device. For an installation that must make no network connections, disconnect the PC from the network after setup. Gameplay and camera tracking work offline. See Google's [MediaPipe privacy notice](https://developers.google.com/edge/mediapipe/solutions/tasks#mediapipe_tasks_privacy_notice) and the [upstream metrics discussion](https://github.com/google-ai-edge/mediapipe/issues/6291).

## Try the game

If you have the packaged version, copy the **entire `HowHotAreYou` folder**, including `_internal`, to the PC. Double-click `HowHotAreYou.exe` or `Run Game.cmd`. The title menu has three buttons: **Start**, **Settings**, and **Quit**. Opening this menu does not start the webcam. Python is not needed for the packaged version.

Choose **Start** to show the visual how-to immediately while the camera starts in the background. The guide stays visible until the camera is ready and a player stands in view. A 3–2–1 countdown then leads into the full 10-second round. Choose **Settings** to select a webcam and check its live picture first.

To preview without a camera, double-click **`Run Demo.cmd`**, or choose **Settings → Keyboard demo**. Both open the same title menu with demo mode selected; choose **Start**. After the how-to screen and countdown, alternate the **left and right arrow keys** (or **A and D**) to sway, or **up and down arrows** (or **W and S**) to wave a simulated hand. Either movement can win on its own. Click the game window if it does not have keyboard focus. After a win or timeout, press Enter or Space to retry with the how-to screen. The demo exercises the game flow; it does not measure camera tracking performance.

## Run from Python source

The supported setup is **Windows x64 with Python 3.11 x64**. The eventual installation PC still needs a real performance check; there is no verified minimum processor/RAM specification yet.

Open PowerShell in this folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.\.venv\Scripts\python.exe main.py --demo --windowed
```

The execution-policy option applies to this PowerShell process only. Setup creates a local `.venv`, installs pinned direct dependencies, and downloads Google's version-1 Pose Landmarker Lite model to `models/pose_landmarker_lite.task`. It can be rerun after an interrupted installation.

If Python is installed at a custom location:

```powershell
.\setup.ps1 -Python "C:\Path\To\Python311\python.exe"
```

To play with a webcam:

```powershell
.\.venv\Scripts\python.exe main.py
```

Use the provided virtual environment instead of mixing packages into an existing installation. Only `opencv-contrib-python` should own the `cv2` module; do not additionally install `opencv-python` or either headless OpenCV wheel in this environment.

## Projector and camera setup

1. Connect the projector by HDMI, the webcam by USB, and speakers if needed.
2. In Windows display settings, set the screens to **Extend** and the projector to **landscape**. Set a suitable native projector resolution.
3. Start on the projector with `--display 1`. Display indices start at zero; use `0` if the projector is the primary/only screen. If Windows orders the displays differently, try the appropriate index.
4. Open **Settings**, choose the webcam, and mount it near the projection surface, pointing toward the player. The camera needs to see both shoulders and hips throughout the movement. Leave space around the torso for hands to move; use the live preview, wrist markers, and **Hands: N/2** indicator to check visibility. Then choose **Save & Back**.
5. Mark one standing area on the floor and leave room to sway comfortably. Keep queued visitors outside the camera view. The default accepted torso centre is the middle 70% of the frame (15%–85%).
6. Position the projector to keep the player out of its beam and the timer visible. Test with the actual venue lighting and projected visuals running.

Example:

```powershell
.\.venv\Scripts\python.exe main.py --display 1 --camera 0
```

For the executable, use the same options:

```powershell
.\HowHotAreYou.exe --display 1 --camera 0
```

Full-screen output uses the selected display. The game draws a 1280 × 720 canvas and scales it with its aspect ratio preserved. Camera processing remains separate from projector resolution.

Use fullscreen (`F`) for projection so the desktop and window border are hidden. Pure black requests the projector's darkest output; it cannot guarantee a completely invisible image rectangle. Projector light leakage and room reflections can make black areas faintly visible, as described in [Barco's contrast whitepaper](https://assets.barco.com/m/7f458cbdce2ad3e4/original/ANSI-Contrast-pdf.pdf). Check the effect on the actual wall with the venue lighting.

## Choose or change the webcam

**Settings** shows the discovered webcam sources on the right and a live preview on the left. Select a source to test it. **Save & Back** becomes available once a fresh camera picture is arriving; a player does not have to be standing in view yet. It saves the choice and returns to the menu, where **Start** begins the how-to screen. Check that the body markers appear when someone stands inside the guide before starting the installation.

The preview highlights reliable wrists and reports **Hands: 0/2**, **1/2**, or **2/2** when the body is detected. This counts visible wrists, not fingers or gestures. Keep shoulders and hips in view even when waving. Hands can extend beyond the marked torso zone anywhere inside the camera picture. If a hand goes offscreen or is hidden, the other visible hand and body sway still work; the game does not require both hands. Body-only play remains available when neither wrist is visible.

Press **C** to open Settings. Plug in another webcam, choose it from the list, check the picture, and save. Background discovery checks roughly every two seconds while active; **Refresh webcams** or **F5** requests another scan. If a device does not appear, use the source-number `−` / `+` buttons and **Reconnect** to try it. A reconnecting or disconnected camera cannot earn heat from a frozen picture.

The chosen source is saved beside the executable in `config.json` when you choose **Save & Back**. With `--config`, the choice is saved in that specified file instead. Other difficulty, display, and model settings are preserved. If that file cannot be written, Settings reports that the choice was not saved; press **Save & Back** again to use it for this session. Camera numbering can change when devices are plugged in or removed, so check the preview after a hardware change.

**Back** or **Esc** returns to the menu even when no camera is connected. **Keyboard demo** selects demo mode and returns to the menu; **Save & Back** selects camera mode. The live preview is part of the projected window, so finish Settings before inviting players to begin.

## Controls

| Key | Action |
| --- | --- |
| `F` | Toggle fullscreen |
| `M` | Toggle sound |
| `F2` | Toggle diagnostics and camera preview |
| `D` | Camera mode only: toggle diagnostics |
| `C` | Open Settings and select a source |
| `R` | Reset the current game |
| `Esc` | Game/Settings: return to menu; menu: quit |
| Up/down arrows or `W` / `S` | Menu: select Start, Settings, or Quit |
| `Enter` / `Space` | Menu: activate the selected button |
| `Enter` / `Space` | Demo only: start or retry a round |
| Left/right arrows or `A` / `D` | Demo only: sway |
| Up/down arrows or `W` / `S` | Demo only: wave a hand |
| `F5` | Settings only: refresh webcams |
| `K` | Settings only: select keyboard demo and return to menu |
| `Enter` | Settings only: Save & Back when the camera is ready |
| Up/down arrows | Settings only: choose a source |

Diagnostics are displayed in the game window, so turn them off before opening the installation to visitors. Use them to check camera framing, tracking status, and observed tracking speed.

Options include `--demo`, `--windowed`, `--mute`, `--camera INDEX`, `--display INDEX`, and `--config PATH`. Run `main.py --help` for all available options.

## Round behaviour

| Stage | Default behaviour |
| --- | --- |
| Menu | Start, Settings, or Quit |
| How to play | Start shows the visual guide immediately; at least 4 seconds with no scoring |
| Player ready | The guide waits for the camera and 1 second of continuous player visibility |
| Countdown | 3 seconds to prepare; separate from the gameplay timer |
| Play | A fresh 10-second timer; body sway or hand movement grows and nudges the balloon chilli |
| Win | Reaching full heat ends the round immediately |
| Timeout | Show the final chilli size and an invitation to retry |
| Result | Show the outcome, heat rating, and any fastest-win record for 3 seconds |
| Clear | The player must leave the zone for 1 second before the next round |

In keyboard demo mode, menu **Start** confirms presence and starts the how-to screen immediately, followed by the full countdown. Enter/Space after a result begins the same sequence without simulating a player leaving the camera zone. `R` also restarts the demo from the how-to screen. Start/retry keys do not skip preparation or restart an active round. After a camera round, the next visitor must let the zone clear before the automatic detection and preparation sequence begins again.

Heat never decreases during a round. Standing still should earn no meaningful heat. Scoring measures sideways torso movement and lean, plus movement of either wrist in any direction relative to the shoulders. Distances are normalized by shoulder width, with smoothing, noise thresholds, and rejection of abrupt tracking jumps. An unseen or unreliable wrist stops contributing until it is tracked again; reappearing elsewhere does not award heat for the missing movement. Both hands can contribute, while a shared maximum rate keeps combined body-and-hand movement from producing an instant win. Scoring uses sample timestamps rather than points per rendered frame.

The result rating is **Warm** below 40% heat, **Spicy** from 40% to below 80%, **Scorching** from 80% without a win, and **Volcanic** for a win. Feedback celebrates movement with short, inclusive phrases such as “Nice moves!” and “You're on fire!”

The fastest winning time is stored locally in `results.json`, with separate records for camera mode, keyboard demo, and scoring difficulty. The result screen shows the current best and identifies a new record. No names, photos, or video are stored. With `--config PATH`, the records file goes beside that configuration file; otherwise it goes beside the source/executable. If the location is read-only, a new record remains available for the current session. Records cover up to 64 mode/difficulty combinations.

Optional sound includes a quiet sizzle that builds with heat, short pop/boing cues for the balloon, and countdown/result cues. Pop/boing playback is rate-limited. Press **M** to mute or unmute; playing does not require speakers.

If the camera or player is unavailable after menu **Start**, the how-to screen waits without consuming gameplay time. Losing the player during its countdown returns to preparation. During play, a short tracking loss stops heat gain while the timer continues; 2 seconds of sustained loss cancels the round. Stale camera results stop earning heat. Check the preview in Settings after a camera change or reconnection.

The model detects one pose at a time; it does **not** lock a person's identity or reliably choose one visitor from a crowd. Camera placement and queue control are part of the installation.

## Adjust difficulty and performance

Edit `config.json` and restart. In the packaged version, edit the copy beside `HowHotAreYou.exe`. JSON must use double quotes and cannot contain comments or trailing commas. Command-line camera/display options override the saved choices for that run.

| Setting | Default | Purpose |
| --- | --- | --- |
| `display.width`, `display.height` | `1280`, `720` | Preferred window size; fullscreen uses the display size |
| `display.fps` | `30` | Maximum drawing frame rate |
| `display.index` | `0` | Projector/display index |
| `display.fullscreen` | `true` | Start fullscreen |
| `tracking.camera_index` | `0` | USB camera index |
| `tracking.camera_backend` | `0` | Capture backend, managed by source selection |
| `tracking.camera_path` | `""` | Device identifier when available, managed by source selection |
| `tracking.width`, `tracking.height` | `640`, `480` | Requested camera resolution |
| `tracking.fps` | `15` | Target tracking updates per second |
| `tracking.zone_left`, `tracking.zone_right` | `0.15`, `0.85` | Accepted torso-centre range in the frame |
| `tracking.confidence` | `0.55` | Required pose confidence |
| `tracking.min_shoulder_width` | `0.09` | Reject very small/distant bodies |
| `tracking.mirror` | `true` | Mirror movement and diagnostic view |
| `game.target_motion` | `6.0` | Motion required to win: **lower is easier** |
| `game.hand_weight` | `0.60` | Contribution from wrist movement |
| `game.hand_deadband` | `0.05` | Ignore small wrist travel, in shoulder widths |
| `game.hand_noise_speed` | `0.25` | Wrist speed removed as noise, in shoulder widths per second |
| `game.max_combined_speed` | `1.6` | Shared scoring-rate cap for body and hands |
| `game.instructions_seconds` | `4.0` | Minimum how-to duration; waiting for camera/player readiness can extend it |
| `game.round_seconds` | `10.0` | Gameplay duration |
| `audio.enabled`, `audio.volume` | See config | Sound on/off and volume from 0 to 1 |

Start with `target_motion` when tuning difficulty. Test several people moving comfortably, including body-only play and one-hand-only play. Choose a value that lets sustained comfortable movement win within the round. Raising sensitivity indiscriminately can turn tracking jitter into progress. Other scoring parameters are advanced controls; keep their defaults until a specific problem is measured.

New hand-scoring settings are optional. Missing values use the defaults in `GameConfig`; an existing `config.json` does not need to be replaced or rewritten to enable hand movement. Additional advanced defaults are `hand_max_speed: 8.0`, `hand_max_observed_speed: 20.0` (shoulder widths per second), and `hand_max_jump: 4.5` (shoulder widths between observations). The last two reject implausible tracking jumps. Saving a camera choice preserves existing game settings.

The low-spec starting targets are 640 × 480 capture, 15 tracking updates per second, and 30 drawing frames per second. These are **targets, not measured guarantees**. MediaPipe runs one Pose Landmarker Lite model on the CPU with one pose and segmentation disabled. Wrist tracking uses that model's existing pose landmarks; there is no separate hand/finger model. Capture and inference run away from the drawing loop, retain only fresh frames, and never build an unlimited queue. The 2D balloon uses bounded motion and bounded sprite/text caches; audio buffers are generated at startup. Some webcams ignore requested resolution/frame rate.

If the PC struggles, first check lighting and framing. Try `tracking.fps` of `10`, then `display.fps` of `24`. The logical drawing canvas remains 1280 × 720; changing the preferred window size does not lower its rendering cost. The Pose Landmarker model also has a fixed inference input size, so reducing camera resolution alone does not necessarily reduce inference time much. Test the result on the actual PC before the event.

## Build a portable Windows executable

After source setup, build on Windows with:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The output is `dist/HowHotAreYou/HowHotAreYou.exe`. Copy the **whole output folder**, including `_internal`, the launchers, configuration, and notices. This is a one-folder build so the runtime/model do not need to be unpacked into a temporary directory at every launch. Build dependencies require internet access the first time. The destination PC does not need Python or internet access.

`HowHotAreYou.spec` includes MediaPipe's native libraries/data and the model. The executable is built for the same OS/architecture as the build environment. This project targets Windows x64; a Windows build is not a Linux/macOS executable.

Rebuilding preserves an existing `results.json` in the output folder. A portable release archive excludes local records and logs, so another installation starts with its own records.

## Troubleshooting

- **No camera / camera reconnecting:** press `C`, close other apps using the webcam, check Windows camera access for desktop apps, reconnect USB, then refresh or select another source. The application retries failed camera connections. Use Keyboard demo to isolate display/game issues from camera issues.
- **Keyboard demo does not react:** select **Start** on the menu, click inside the game window if needed, wait for the how-to screen and countdown, then alternate left/right to sway or up/down to wave. Practice movement during preparation does not earn heat. Holding only one direction moves to one side and eventually stops earning heat. After Alt-Tab or losing focus, press the movement keys again; held-key state is cleared to prevent phantom movement.
- **No player detected:** enable diagnostics, show shoulders and hips, step into the central zone, improve even front lighting, and reduce backlighting. Avoid a tiny or cropped body in the frame.
- **Waving does not grow the chilli:** check the wrist markers and **Hands: N/2** in Settings. Keep the torso and at least one wrist visible, move the hand relative to the shoulders, and avoid covering it with the body. Swaying still works if hands cannot be tracked.
- **Heat rises while still:** improve lighting and keep other people out of frame first. Use a stable camera mount. Confirm actual swaying works before changing advanced noise thresholds.
- **Game starts on the wrong display:** change `--display` or `display.index`. Display order can change after HDMI reconnection.
- **Model missing or invalid:** rerun setup. To explicitly replace it, run `.\.venv\Scripts\python.exe tools\download_model.py --force`.
- **No sound:** press `M`, check the Windows playback device/HDMI audio destination, and inspect the volume setting. The game can still run when an audio device is unavailable.
- **Packaged game cannot launch after copying:** ensure the complete folder was copied and `_internal` was retained. Test the source version or rebuild on the intended Windows architecture if native library loading fails.

Application logs are written to `logs/chilli.log` beside the source/executable, or `how-hot-are-you.log` in Windows' temporary folder if that location is not writable. Logs are replaced at startup and contain game/camera status, not video frames.

## Verification before installation

Run the automated logic tests from source:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run a headless renderer/model check and save its measurements:

```powershell
.\.venv\Scripts\python.exe main.py --self-test --report artifacts\self-test.json
```

This checks a blank frame through the model and a rendered game screen; it does not verify detection of a real person. A preview image can also be exported without opening the game:

```powershell
.\.venv\Scripts\python.exe main.py --screenshot artifacts\playing.png --scene playing
```

Then run a keyboard demo and a webcam session on the installation PC. Confirm that the how-to screen appears before each round and retry, and that gameplay starts with the full 10 seconds. Check standing still, comfortable body-only swaying, one-hand waves in several directions, both hands moving in opposite directions, and hands briefly hidden or offscreen. Also check leaving mid-round, camera reconnection, winning, timeout, empty-zone reset, sound/mute, and fastest-time records after restarting. Check at least ten successive rounds and an extended unattended run with the final projector, camera, lighting, and speakers. Automated tests and a demo do not substitute for that installation check.

Physical installation testing of the new hand controls, balloon effects, and low-spec performance is still pending. Physical USB unplug/replug and new-camera attachment have not yet been tested on the installation hardware. Discovery, switching, and return-to-menu behavior have automated coverage using simulated devices; test real USB changes before the event.

## Project layout

- `main.py`: application entry point, display/input, configuration, and game loop.
- `chilli/`: game state, motion scoring, webcam discovery/tracking, menu/settings UI, keyboard input, balloon physics/graphics, audio, and local records. The Python package name stays `chilli`.
- `config.json`: operator-editable settings.
- `results.json`: local fastest-win records, created when a result is saved.
- `tests/`: deterministic scoring/state tests.
- `tools/download_model.py`: explicit setup-time model download and validation.
- `setup.ps1`, `build.ps1`, `HowHotAreYou.spec`: source setup and executable packaging.

See [THIRD_PARTY.md](THIRD_PARTY.md) for dependency and model sources. MediaPipe's [Pose Landmarker documentation](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) describes the Lite model and pose options; PyInstaller's [packaging documentation](https://pyinstaller.org/en/stable/operating-mode.html) explains portable bundles.
