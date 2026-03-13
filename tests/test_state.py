import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from gtm.state import load_state, save_state, can_start_session, create_default_state


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_default_state(self):
        state = create_default_state()
        self.assertIn("last_session", state)
        self.assertIn("session_count_today", state)
        self.assertIn("daily_reset", state)

    def test_load_creates_if_missing(self):
        state = load_state(self.state_path)
        self.assertIn("last_session", state)
        self.assertTrue(os.path.exists(self.state_path))

    def test_save_and_load_roundtrip(self):
        state = create_default_state()
        state["session_count_today"] = 2
        save_state(self.state_path, state)
        loaded = load_state(self.state_path)
        self.assertEqual(loaded["session_count_today"], 2)

    def test_can_start_session_ready(self):
        state = create_default_state()
        ok, reason = can_start_session(state)
        self.assertTrue(ok)
        self.assertEqual(reason, "Ready")

    def test_can_start_session_cooldown(self):
        state = create_default_state()
        state["last_session"] = (datetime.utcnow() - timedelta(minutes=5)).isoformat() + "Z"
        ok, reason = can_start_session(state)
        self.assertFalse(ok)
        self.assertIn("Cooldown", reason)

    def test_can_start_session_daily_limit(self):
        state = create_default_state()
        state["session_count_today"] = 3
        ok, reason = can_start_session(state)
        self.assertFalse(ok)
        self.assertIn("limit", reason)

    def test_daily_reset(self):
        state = create_default_state()
        state["daily_reset"] = "2026-03-01"  # old date
        state["session_count_today"] = 3
        save_state(self.state_path, state)
        loaded = load_state(self.state_path)
        self.assertEqual(loaded["session_count_today"], 0)

    def test_migrates_old_per_platform_state(self):
        """Old state format with per-platform data should migrate."""
        old_state = {
            "platforms": {
                "reddit": {"last_session": "2026-03-05T10:00:00Z", "cooldown_min": 180, "session_count_today": 1},
                "twitter": {"last_session": "2026-03-05T12:00:00Z", "cooldown_min": 120, "session_count_today": 0},
                "producthunt": {"last_session": "2026-03-04T18:00:00Z", "cooldown_min": 240, "session_count_today": 0},
                "indiehackers": {"last_session": "2026-03-04T09:00:00Z", "cooldown_min": 180, "session_count_today": 0},
            },
            "daily_reset": "2026-03-05",
        }
        save_state(self.state_path, old_state)
        loaded = load_state(self.state_path)
        self.assertIn("last_session", loaded)
        self.assertNotIn("platforms", loaded)
        self.assertEqual(loaded["last_session"], "2026-03-05T12:00:00Z")
        self.assertEqual(loaded["session_count_today"], 1)


if __name__ == "__main__":
    unittest.main()
