# Build on Windows with the supported Python 3.11 x64 virtual environment.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, collect_delvewheel_libs_directory, copy_metadata

project = Path(SPECPATH)
model = project / "models" / "pose_landmarker_lite.task"
if not model.is_file():
    raise SystemExit("Pose model missing. Run setup.ps1 before building.")

mp_data, mp_binaries, mp_hidden = collect_all("mediapipe")
camera_data, camera_binaries = collect_delvewheel_libs_directory("cv2_enumerate_cameras")
datas = mp_data + camera_data + [
    (str(project / "config.json"), "."),
    (str(model), "models"),
    (str(project / "THIRD_PARTY.md"), "."),
    (str(project / "licenses" / "pygame-LGPL-2.1.txt"), "licenses/pygame"),
]
for dependency in ("mediapipe", "numpy", "pygame", "opencv-contrib-python", "cv2-enumerate-cameras"):
    datas += copy_metadata(dependency, recursive=True)
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    datas.append((str(python_license), "licenses/python"))

a = Analysis(
    [str(project / "main.py")],
    pathex=[str(project)],
    binaries=mp_binaries + camera_binaries,
    datas=datas,
    hiddenimports=mp_hidden + ["cv2_enumerate_cameras.windows_backend", "cv2_enumerate_cameras._windows_backend"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HowHotAreYou",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(project / "assets" / "chilli.ico") if (project / "assets" / "chilli.ico").is_file() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="HowHotAreYou",
)
