import os
import tempfile
import unittest
from unittest.mock import patch
import random

from gtm.runner import (
    SessionRunner, InterleavedRunner, roll_action,
    PLATFORM_ACTIONS, get_available_actions, get_action_info,
)
from gtm.state import PLATFORMS


class TestRollAction(unittest.TestCase):
    def test_returns_valid_action_per_platform(self):
        for platform in PLATFORMS:
            valid = set(get_available_actions(platform))
            for _ in range(100):
                action = roll_action(platform)
                self.assertIn(action, valid)

    def test_distribution_roughly_correct(self):
        # Twitter: like should be ~20%, follow ~10%
        counts = {}
        n = 10000
        for _ in range(n):
            a = roll_action("twitter")
            counts[a] = counts.get(a, 0) + 1
        self.assertGreater(counts.get("like", 0) / n, 0.12)
        self.assertLess(counts.get("like", 0) / n, 0.30)
        self.assertGreater(counts.get("follow", 0) / n, 0.05)
        self.assertLess(counts.get("follow", 0) / n, 0.18)

    def test_limit_enforcement(self):
        # Simulate thread maxed out on twitter
        counts = {"thread": 1}
        results = set()
        for _ in range(500):
            results.add(roll_action("twitter", counts))
        self.assertNotIn("thread", results)

    def test_all_platforms_have_skip(self):
        for platform in PLATFORMS:
            actions = get_available_actions(platform)
            self.assertIn("skip", actions, f"{platform} missing skip action")


class TestInterleavedRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.state_path = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_covers_all_platforms(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        self.assertEqual(set(runner.platform_limits.keys()), set(PLATFORMS))

    def test_start_all_creates_sessions(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        self.assertEqual(set(runner.session_ids.keys()), set(PLATFORMS))

    def test_pick_next_returns_valid_platform(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        platform = runner.pick_next()
        self.assertIn(platform, PLATFORMS)

    def test_pick_next_avoids_repeat(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        picks = set()
        for _ in range(20):
            p = runner.pick_next()
            picks.add(p)
        # Should have picked multiple different platforms
        self.assertGreater(len(picks), 1)

    def test_pick_next_avoids_last_platform(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        first = runner.pick_next()
        # With 5 platforms available, next pick should differ from first
        consecutive_same = 0
        for _ in range(20):
            nxt = runner.pick_next()
            if nxt == first:
                consecutive_same += 1
            first = nxt
        # Should almost never pick the same platform twice in a row
        self.assertLess(consecutive_same, 5)

    def test_record_action_increments_counts(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.record_action("twitter", "like", "https://example.com/1")
        runner.record_action("reddit", "comment", "https://example.com/2", content="nice post")
        self.assertEqual(runner.platform_actions["twitter"], 1)
        self.assertEqual(runner.platform_actions["reddit"], 1)
        self.assertEqual(runner.total_actions, 2)

    def test_is_platform_done(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        # Force a low limit for testing
        runner.platform_limits["producthunt"] = 2
        runner.record_action("producthunt", "like", "https://ph.com/1")
        self.assertFalse(runner.is_platform_done("producthunt"))
        runner.record_action("producthunt", "like", "https://ph.com/2")
        self.assertTrue(runner.is_platform_done("producthunt"))

    def test_is_done_when_all_platforms_done(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        # Set all limits to 0 so they're immediately done
        for p in PLATFORMS:
            runner.platform_limits[p] = 0
        self.assertTrue(runner.is_done())

    def test_active_platforms_excludes_done(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.platform_limits["twitter"] = 1
        runner.record_action("twitter", "like", "https://x.com/1")
        self.assertNotIn("twitter", runner.active_platforms)
        self.assertEqual(len(runner.active_platforms), len(PLATFORMS) - 1)

    def test_pick_next_returns_none_when_all_done(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        for p in PLATFORMS:
            runner.platform_limits[p] = 0
        self.assertIsNone(runner.pick_next())

    def test_should_promote_with_no_history(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        # No actions yet, ratio is 0 which is < 0.1
        self.assertTrue(runner.should_promote("twitter"))

    def test_record_action_enrolls_comment_for_tracking(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.record_action("twitter", "comment", "https://x.com/post/1",
                             content="great thread tbh")
        from gtm.engagement import get_active_tracking_count
        count = get_active_tracking_count(self.db_path)
        self.assertEqual(count, 1)

    def test_record_action_skips_tracking_for_likes(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.record_action("twitter", "like", "https://x.com/post/1")
        from gtm.engagement import get_active_tracking_count
        count = get_active_tracking_count(self.db_path)
        self.assertEqual(count, 0)

    def test_record_action_enrolls_like_and_comment(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.record_action("reddit", "like_and_comment", "https://reddit.com/1",
                             content="so true lol")
        from gtm.engagement import get_active_tracking_count
        count = get_active_tracking_count(self.db_path)
        self.assertEqual(count, 1)

    def test_record_action_logs_decision(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.record_action("twitter", "comment", "https://x.com/1", content="nice")
        from gtm.decisions import get_recent_decisions
        decisions = get_recent_decisions(self.db_path, category="engagement")
        self.assertGreaterEqual(len(decisions), 1)

    def test_progress_shows_all_platforms(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.record_action("twitter", "like", "https://x.com/1")
        prog = runner.progress()
        self.assertEqual(len(prog), len(PLATFORMS))
        self.assertTrue(prog["twitter"].startswith("1/"))

    def test_finish_updates_state(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.finish()
        from gtm.state import load_state
        state = load_state(self.state_path)
        self.assertGreaterEqual(state["session_count_today"], 1)

    def test_summary(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.record_action("reddit", "comment", "https://reddit.com/1", content="test")
        s = runner.summary()
        self.assertEqual(s["total_actions"], 1)
        self.assertEqual(s["actions_per_platform"]["reddit"], 1)
        self.assertIn("limits_per_platform", s)

    def test_duration_range(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        self.assertGreaterEqual(runner.max_duration_min, 20)
        self.assertLessEqual(runner.max_duration_min, 50)

    def test_action_delay_range(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        delays = [runner.get_action_delay() for _ in range(100)]
        self.assertTrue(all(30 <= d <= 180 for d in delays))


class TestSessionRunner(unittest.TestCase):
    """Legacy sequential runner tests."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.state_path = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_covers_all_platforms(self):
        runner = SessionRunner(self.db_path, self.state_path)
        self.assertEqual(set(runner.platform_order), set(PLATFORMS))

    def test_session_duration_randomized(self):
        runner = SessionRunner(self.db_path, self.state_path)
        self.assertGreaterEqual(runner.max_duration_min, 30)
        self.assertLessEqual(runner.max_duration_min, 90)

    def test_should_promote_respects_ratio(self):
        runner = SessionRunner(self.db_path, self.state_path)
        runner.start_platform()
        self.assertTrue(runner.should_promote())

    def test_platform_progression(self):
        runner = SessionRunner(self.db_path, self.state_path)
        first = runner.current_platform
        runner.start_platform()
        runner.current_platform_actions = runner.actions_per_platform[first]
        self.assertTrue(runner.is_platform_done())
        second = runner.next_platform()
        self.assertNotEqual(first, second)
        self.assertIsNotNone(second)


if __name__ == "__main__":
    unittest.main()
