from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chilli.game import GameConfig
from chilli.records import ResultStore


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "results.json"
        self.config = GameConfig()
        self.store = ResultStore(self.path)

    def test_only_faster_wins_replace_persisted_best(self):
        self.assertTrue(self.store.record_win("camera", self.config, 8.2))
        self.assertFalse(self.store.record_win("camera", self.config, 9.0))
        self.assertTrue(self.store.record_win("camera", self.config, 7.5))
        self.assertEqual(ResultStore(self.path).best("camera", self.config), 7.5)

    def test_demo_and_difficulty_have_separate_records(self):
        self.store.record_win("demo", self.config, 5.0)
        self.assertIsNone(self.store.best("camera", self.config))
        harder = replace(self.config, target_motion=10.0)
        self.assertIsNone(self.store.best("demo", harder))
        self.assertEqual(self.store.best("demo", replace(self.config, instructions_seconds=8)), 5.0)

    def test_invalid_times_never_create_a_record_file(self):
        for seconds in (0, -1, 11, float("inf"), float("nan"), True, "5"):
            self.assertFalse(self.store.record_win("camera", self.config, seconds))
        self.assertFalse(self.path.exists())

    def test_corrupt_or_malformed_records_do_not_stop_the_game(self):
        for value in ("broken", "[]", '{"version":1,"best_times":{"bad":null,"other":-1}}'):
            self.path.write_text(value)
            store = ResultStore(self.path)
            self.assertIsNone(store.best("camera", self.config))
            self.assertTrue(store.record_win("camera", self.config, 6))

    def test_read_only_file_keeps_session_best_without_losing_old_file(self):
        self.store.record_win("camera", self.config, 8)
        before = self.path.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("read only")):
            self.assertTrue(self.store.record_win("camera", self.config, 6))
        self.assertEqual(self.store.best("camera", self.config), 6)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_records_contain_no_player_identifiers(self):
        self.store.record_win("camera", self.config, 8)
        payload = json.loads(self.path.read_text())
        self.assertEqual(set(payload), {"version", "best_times"})
        self.assertEqual(list(payload["best_times"].values()), [8.0])


if __name__ == "__main__":
    unittest.main()
