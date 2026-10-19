"""Small local fastest-win records, separated by input mode and difficulty."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import logging
import math
from pathlib import Path
import tempfile


class ResultStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries = {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") == 1 and isinstance(payload.get("best_times"), dict):
                self.entries = {
                    key: float(value) for key, value in payload["best_times"].items()
                    if isinstance(key, str) and len(key) < 100
                    and isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) and value > 0
                }
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError, TypeError):
            logging.warning("Local records could not be read; using session records")

    @staticmethod
    def _key(mode, config):
        # Keep results comparable when an operator changes scoring parameters.
        data = asdict(config)
        for name in ("instructions_seconds", "countdown_seconds", "settle_seconds",
                     "result_seconds", "clear_seconds"):
            data.pop(name, None)
        digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
        return f"hands-v1:{mode}:{digest}"

    def best(self, mode, config):
        return self.entries.get(self._key(mode, config))

    def record_win(self, mode, config, seconds):
        if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or not 0 < seconds <= config.round_seconds):
            return False
        key = self._key(mode, config)
        previous = self.entries.get(key)
        if previous is not None and seconds >= previous:
            return False
        self.entries[key] = float(seconds)
        # Operators can experiment with difficulty without unbounded growth.
        while len(self.entries) > 64:
            self.entries.pop(next(iter(self.entries)))
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".tmp",
                                             dir=self.path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({"version": 1, "best_times": self.entries}, handle, indent=2)
                handle.write("\n")
            temporary.replace(self.path)
        except OSError:
            logging.warning("Local record could not be saved; keeping it for this session")
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
        return True
