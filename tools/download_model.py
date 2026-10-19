"""Explicit setup-time download; the game itself never downloads its model."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request
import zipfile


MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "models" / "pose_landmarker_lite.task"
MAX_BYTES = 32 * 1024 * 1024
EXPECTED_SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"


def validate(path: Path) -> str:
    size = path.stat().st_size
    if not 1_000_000 <= size <= MAX_BYTES:
        raise ValueError(f"Unexpected model size: {size:,} bytes")
    # MediaPipe task bundles are ZIP files containing the detector and landmarker.
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        expected = {"pose_detector.tflite", "pose_landmarks_detector.tflite"}
        if not expected.issubset(names):
            raise ValueError(f"Not a Pose Landmarker bundle; found {sorted(names)}")
        if archive.testzip() is not None:
            raise ValueError("The model archive is corrupt")
        for name in expected:
            with archive.open(name) as model:
                if model.read(8)[4:8] != b"TFL3":
                    raise ValueError(f"Invalid TensorFlow Lite model: {name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f"Model SHA-256 mismatch: expected {EXPECTED_SHA256}, got {digest}")
    return digest


def download(destination: Path, force: bool = False) -> None:
    if destination.is_file() and not force:
        try:
            digest = validate(destination)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            print(f"Existing model is invalid ({error}); downloading a replacement.")
        else:
            print(f"Model already available: {destination}\nSHA-256: {digest}")
            return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        # Write beside the destination so os.replace is atomic on the same volume.
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix="pose_", suffix=".part", delete=False
        ) as output:
            temporary = Path(output.name)
            print(f"Downloading the MediaPipe Pose Landmarker Lite model to {destination}")
            request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "ChilliShimmy-Setup/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                total = 0
                while chunk := response.read(128 * 1024):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError("Model download exceeds the expected size limit")
                    output.write(chunk)
        digest = validate(temporary)
        os.replace(temporary, destination)
        temporary = None
        print(f"Model ready ({total:,} bytes).\nSHA-256: {digest}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--force", action="store_true", help="Replace an existing model")
    args = parser.parse_args()
    try:
        download(args.output.resolve(), args.force)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Model setup failed: {error}\nCheck internet access, then run setup.ps1 again.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
