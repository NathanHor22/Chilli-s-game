# Chilli Shimmy

A one-player, 10-second webcam game for a landscape projector. Step into the play area, watch the visual guide to swaying left and right, then get ready for the countdown. Keep swaying to grow the chilli to its maximum size before time runs out.

Every round begins with a dedicated how-to screen. During play, the screen focuses on a centred chilli, the timer, and a short encouragement at the bottom. The how-to screen and countdown do not use any of the 10 seconds of gameplay.

The game uses Python, OpenCV, MediaPipe Pose Landmarker Lite, and Pygame. It has simple cream-and-red 2D graphics, optional synthesized sound, and a keyboard demo. It runs locally after setup; the application does not record or upload webcam images. Internet access is needed to install dependencies and download the model, not to play.

MediaPipe 0.10.35 can attempt to send library performance/usage metrics when internet access is available; the webcam images are processed on the device. For an installation that must make no network connections, disconnect the PC from the network after setup. Gameplay and camera tracking work offline. See Google's [MediaPipe privacy notice](https://developers.google.com/edge/mediapipe/solutions/tasks#mediapipe_tasks_privacy_notice) and the [upstream metrics discussion](https://github.com/google-ai-edge/mediapipe/issues/6291).

## Try the game

If you have the packaged version, copy the **entire `ChilliShimmy` folder**, including `_internal`, to the PC. Double-click `ChilliShimmy.exe` or `Run Game.cmd`. The camera setup screen opens first: choose a webcam, check the live picture, then select **Start game**. Python is not needed for the packaged version.

To preview without a camera, double-click **`Run Demo.cmd`**, or choose **Keyboard demo** on the setup screen. Click the game window if it does not have keyboard focus. Press **Enter or Space** to start the how-to screen and countdown, then alternate the **left and right arrow keys** (or **A and D**) to sway. After a win or timeout, press Enter or Space to begin a new round with the how-to screen. The demo exercises the game flow; it does not measure camera tracking performance.

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
4. Choose the webcam in the setup screen and mount it near the projection surface, pointing toward the player. The camera needs to see both shoulders and hips throughout the sway. Adjust its height and distance using the live preview and body markers.
5. Mark one standing area on the floor and leave room to sway comfortably. Keep queued visitors outside the camera view. The default accepted torso centre is the middle 70% of the frame (15%–85%).
6. Position the projector to keep the player out of its beam and the timer visible. Test with the actual venue lighting and projected visuals running.

Example:

```powershell
.\.venv\Scripts\python.exe main.py --display 1 --camera 0
```

For the executable, use the same options:

```powershell
.\ChilliShimmy.exe --display 1 --camera 0
```

Full-screen output uses the selected display. The game draws a 1280 × 720 canvas and scales it with its aspect ratio preserved. Camera processing remains separate from projector resolution.

## Choose or change the webcam

The setup screen shows the discovered webcam sources on the right and a live preview on the left. Select a source to test it. **Start game** becomes available once a fresh camera picture is arriving; a player does not have to be standing in view yet. Check that the body markers appear when someone stands inside the guide before starting the installation.

Press **C** during the game to return to setup. Plug in another webcam, choose it from the list, check the picture, and start again. New sources appear automatically; **Refresh webcams** or **F5** requests another scan. If a device does not appear, use the source-number `−` / `+` buttons and **Reconnect** to try it. A reconnecting or disconnected camera cannot earn heat from a frozen picture.

The chosen source is saved beside the executable in `config.json` when you start the camera game. With `--config`, the choice is saved in that specified file instead. Other difficulty, display, and model settings are preserved. If that file cannot be written, the setup screen reports that the choice was not saved; press Start again to use the choice for this session. Camera numbering can change when devices are plugged in or removed, so check the preview after a hardware change.

The setup preview is part of the projected window. Finish setup before inviting players to begin.

## Controls

| Key | Action |
| --- | --- |
| `F` | Toggle fullscreen |
| `M` | Toggle sound |
| `F2` | Toggle diagnostics and camera preview |
| `D` | Camera mode only: toggle diagnostics |
| `C` | Open camera setup and select a source |
| `R` | Reset the current game |
| `Esc` | Quit |
| `Enter` / `Space` | Demo only: start or retry a round |
| Left/right arrows or `A` / `D` | Demo only: sway |
| `F5` | Setup only: refresh webcams |
| `K` | Setup only: keyboard demo |
| `Enter` | Setup only: start the camera game when ready |
| Up/down arrows | Setup only: choose a source |

Diagnostics are displayed in the game window, so turn them off before opening the installation to visitors. Use them to check camera framing, tracking status, and observed tracking speed.

Options include `--demo`, `--windowed`, `--mute`, `--camera INDEX`, `--display INDEX`, and `--config PATH`. Run `main.py --help` for all available options.

## Round behaviour

| Stage | Default behaviour |
| --- | --- |
| Idle | Chilli animation and an invitation to step in |
| Settle | Player remains visible for 1 second |
| How to play | 4-second visual demonstration of swaying left and right; no scoring |
| Countdown | 3 seconds to prepare; separate from the gameplay timer |
| Play | A fresh 10-second timer; movement grows the centred chilli |
| Win | Reaching full heat ends the round immediately |
| Timeout | Show the achieved heat and an invitation to retry |
| Result | Show the outcome for 3 seconds |
| Clear | The player must leave the zone for 1 second before the next round |

In keyboard demo mode, Enter/Space confirms presence and starts the how-to screen immediately, followed by the full countdown. Enter/Space after a result begins the same sequence without simulating a player leaving the camera zone. `R` also restarts the demo from the how-to screen. Start/retry keys do not skip preparation or restart an active round. These shortcuts do not change the webcam game's automatic player detection and empty-zone reset.

Heat never decreases during a round. Standing still should earn no meaningful heat. Scoring combines sideways torso displacement and changes in lean, normalized by body size, with smoothing, a noise threshold, and rejection of abrupt tracking jumps. It uses sample timestamps rather than points per frame.

Losing the player during the how-to screen or countdown cancels preparation. During play, a short tracking loss stops heat gain while the timer continues; 2 seconds of sustained loss cancels the round. Stale camera results stop earning heat. Reconnection requires a clear zone before a new round.

The model detects one pose at a time; it does **not** lock a person's identity or reliably choose one visitor from a crowd. Camera placement and queue control are part of the installation.

## Adjust difficulty and performance

Edit `config.json` and restart. In the packaged version, edit the copy beside `ChilliShimmy.exe`. JSON must use double quotes and cannot contain comments or trailing commas. Command-line camera/display options override the saved choices for that run.

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
| `game.instructions_seconds` | `4.0` | How-to screen duration before each countdown; `0` skips it |
| `game.round_seconds` | `10.0` | Gameplay duration |
| `audio.enabled`, `audio.volume` | See config | Sound on/off and volume from 0 to 1 |

Start with `target_motion` when tuning difficulty. Test several people moving comfortably and choose a value that allows sustained swaying to win near the end of the round. Raising sensitivity indiscriminately can turn tracking jitter into progress. Other scoring parameters are advanced controls; keep their defaults until a specific problem is measured.

The low-spec starting targets are 640 × 480 capture, 15 tracking updates per second, and 30 drawing frames per second. These are **targets, not measured guarantees**. MediaPipe runs on the CPU with one pose and segmentation disabled. Capture and inference run away from the drawing loop, retain only fresh frames, and never build an unlimited queue. Some webcams ignore requested resolution/frame rate.

If the PC struggles, first check lighting and framing. Try `tracking.fps` of `10`, then `display.fps` of `24`. The logical drawing canvas remains 1280 × 720; changing the preferred window size does not lower its rendering cost. The Pose Landmarker model also has a fixed inference input size, so reducing camera resolution alone does not necessarily reduce inference time much. Test the result on the actual PC before the event.

## Build a portable Windows executable

After source setup, build on Windows with:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The output is `dist/ChilliShimmy/ChilliShimmy.exe`. Copy the **whole output folder**, including `_internal`, the launchers, configuration, and notices. This is a one-folder build so the runtime/model do not need to be unpacked into a temporary directory at every launch. Build dependencies require internet access the first time. The destination PC does not need Python or internet access.

`ChilliShimmy.spec` includes MediaPipe's native libraries/data and the model. The executable is built for the same OS/architecture as the build environment. This project targets Windows x64; a Windows build is not a Linux/macOS executable.

## Troubleshooting

- **No camera / camera reconnecting:** press `C`, close other apps using the webcam, check Windows camera access for desktop apps, reconnect USB, then refresh or select another source. The application retries failed camera connections. Use Keyboard demo to isolate display/game issues from camera issues.
- **Keyboard demo does not react:** click inside the game window, press Enter or Space, wait for the how-to screen and countdown, then alternate left and right. Practice movement during preparation does not earn heat. Holding only one direction moves to one side and eventually stops earning heat. After Alt-Tab or losing focus, press the movement keys again; held-key state is cleared to prevent phantom movement.
- **No player detected:** enable diagnostics, show shoulders and hips, step into the central zone, improve even front lighting, and reduce backlighting. Avoid a tiny or cropped body in the frame.
- **Heat rises while still:** improve lighting and keep other people out of frame first. Use a stable camera mount. Confirm actual swaying works before changing advanced noise thresholds.
- **Game starts on the wrong display:** change `--display` or `display.index`. Display order can change after HDMI reconnection.
- **Model missing or invalid:** rerun setup. To explicitly replace it, run `.\.venv\Scripts\python.exe tools\download_model.py --force`.
- **No sound:** press `M`, check the Windows playback device/HDMI audio destination, and inspect the volume setting. The game can still run when an audio device is unavailable.
- **Packaged game cannot launch after copying:** ensure the complete folder was copied and `_internal` was retained. Test the source version or rebuild on the intended Windows architecture if native library loading fails.

Application logs are written to `logs/chilli.log` beside the source/executable, or `chilli-shimmy.log` in Windows' temporary folder if that location is not writable. Logs are replaced at startup and contain game/camera status, not video frames.

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

Then run a keyboard demo and a webcam session on the installation PC. Confirm that the how-to screen appears before each round and retry, and that gameplay starts with the full 10 seconds. Also check standing still, comfortable swaying, brief occlusion, leaving mid-round, camera reconnection, winning, timeout, and empty-zone reset. Check at least ten successive rounds and an extended unattended run with the final projector, camera, lighting, and speakers. Automated tests and a demo do not substitute for that installation check.

## Project layout

- `main.py`: application entry point, display/input, configuration, and game loop.
- `chilli/`: game state, motion scoring, webcam discovery/tracking, setup UI, keyboard input, graphics, and audio.
- `config.json`: operator-editable settings.
- `tests/`: deterministic scoring/state tests.
- `tools/download_model.py`: explicit setup-time model download and validation.
- `setup.ps1`, `build.ps1`, `ChilliShimmy.spec`: source setup and executable packaging.

See [THIRD_PARTY.md](THIRD_PARTY.md) for dependency and model sources. MediaPipe's [Pose Landmarker documentation](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) describes the Lite model and pose options; PyInstaller's [packaging documentation](https://pyinstaller.org/en/stable/operating-mode.html) explains portable bundles.
