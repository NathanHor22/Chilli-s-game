"""Validated, portable configuration shared by the source and frozen app."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
import math
from pathlib import Path
import sys

from .game import GameConfig
from .tracking import TrackingConfig


@dataclass
class DisplayConfig:
    width: int = 1280
    height: int = 720
    fps: int = 30
    fullscreen: bool = True
    index: int = 0


@dataclass
class AudioConfig:
    enabled: bool = True
    volume: float = 0.35


@dataclass
class Config:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    game: GameConfig = field(default_factory=GameConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def app_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else resource_root()


def _construct(cls, data: dict, section: str):
    if not isinstance(data, dict):
        raise ValueError(f"{section} must be a JSON object")
    defaults = cls()
    allowed = {f.name for f in fields(cls)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown {section} setting: {', '.join(sorted(unknown))}")
    for key, value in data.items():
        default = getattr(defaults, key)
        if isinstance(default, bool):
            valid = isinstance(value, bool)
        elif isinstance(default, int):
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif isinstance(default, float):
            valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        else:
            valid = isinstance(value, type(default))
        if not valid:
            raise ValueError(f"Invalid value for {section}.{key}: {value!r}")
    return cls(**data)


def load_config(path: str | Path | None = None) -> Config:
    selected = Path(path).resolve() if path else app_root() / "config.json"
    if not selected.exists() and not path:
        selected = resource_root() / "config.json"
    if path and not selected.is_file():
        raise ValueError(f"Configuration file not found: {selected}")
    data = json.loads(selected.read_text(encoding="utf-8-sig")) if selected.is_file() else {}
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a JSON object")
    unknown = set(data) - {"display", "game", "tracking", "audio"}
    if unknown:
        raise ValueError(f"Unknown configuration section: {', '.join(sorted(unknown))}")
    config = Config(*(_construct(cls, data.get(name, {}), name) for cls, name in (
        (DisplayConfig, "display"), (GameConfig, "game"), (TrackingConfig, "tracking"), (AudioConfig, "audio")
    )))
    d, g, t, a = config.display, config.game, config.tracking, config.audio
    if not (640 <= d.width <= 3840 and 360 <= d.height <= 2160 and 10 <= d.fps <= 60 and d.index >= 0):
        raise ValueError("Display needs width 640–3840, height 360–2160, fps 10–60, and index >= 0")
    if not (0 <= t.zone_left < t.zone_right <= 1 and t.zone_right - t.zone_left >= .3):
        raise ValueError("Tracking zone must be within 0–1 and at least 0.3 wide")
    if not (160 <= t.width <= 1920 and 120 <= t.height <= 1080 and 3 <= t.fps <= 30 and t.camera_index >= 0):
        raise ValueError("Invalid camera dimensions, index, or tracking fps (3–30)")
    if not (0 < t.confidence <= 1 and .02 <= t.min_shoulder_width <= .5 and 0 <= a.volume <= 1):
        raise ValueError("Invalid confidence, minimum shoulder size, or audio volume")
    for key in ("round_seconds", "countdown_seconds", "settle_seconds", "result_seconds", "clear_seconds", "lost_seconds", "stale_seconds", "target_motion", "max_speed"):
        if getattr(g, key) <= 0:
            raise ValueError(f"game.{key} must be positive")
    if not 0 <= g.noise_speed < g.max_speed:
        raise ValueError("game.noise_speed must be nonnegative and below max_speed")
    model = Path(t.model_path)
    if not model.is_absolute():
        external = selected.parent / model
        t.model_path = str(external if external.is_file() else resource_root() / model)
    return config


def config_dict(config: Config) -> dict:
    return asdict(config)


def save_camera_selection(config: Config, path: str | Path | None = None) -> None:
    """Persist only the operator's source choice, preserving other settings."""
    selected = Path(path).resolve() if path else app_root() / "config.json"
    if selected.is_file():
        data = json.loads(selected.read_text(encoding="utf-8-sig"))
    else:
        data = {}
    if not isinstance(data, dict) or not isinstance(data.get("tracking", {}), dict):
        raise ValueError("Cannot save camera selection into an invalid configuration")
    tracking = data.setdefault("tracking", {})
    tracking.update(camera_index=config.tracking.camera_index,
                    camera_backend=config.tracking.camera_backend,
                    camera_path=config.tracking.camera_path)
    # Replace atomically; a failed save cannot truncate the previous setup.
    import tempfile
    selected.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".tmp",
                                         dir=selected.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=2)
            handle.write("\n")
        temporary.replace(selected)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
