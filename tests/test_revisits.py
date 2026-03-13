import os
import tempfile
import unittest
from datetime import datetime, timedelta

from gtm.db import init_db, get_connection
from gtm.engagement import enroll_for_tracking, record_check, get_due_checks


class TestEscalatingIntervals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)
        from gtm.db import create_session, log_action
        self.session_id = create_session(self.db_path, "twitter")
        self.action_id = log_action(
            self.db_path, self.session_id, "twitter", "comment",
            "https://x.com/post/1", content="test comment",
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_check_scheduled_15_min(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        next_check = datetime.fromisoformat(row["next_check_at"])
        now = datetime.utcnow()
        diff = (next_check - now).total_seconds() / 60
        self.assertGreater(diff, 13)
        self.assertLess(diff, 17)

    def test_second_check_scheduled_15_min(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        record_check(self.db_path, tid, replies=0)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["checks_done"], 1)
        next_check = datetime.fromisoformat(row["next_check_at"])
        last_check = datetime.fromisoformat(row["last_checked_at"])
        diff = (next_check - last_check).total_seconds() / 60
        self.assertGreater(diff, 13)
        self.assertLess(diff, 17)

    def test_third_check_scheduled_30_min(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        record_check(self.db_path, tid, replies=0)
        record_check(self.db_path, tid, replies=0)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["checks_done"], 2)
        next_check = datetime.fromisoformat(row["next_check_at"])
        last_check = datetime.fromisoformat(row["last_checked_at"])
        diff = (next_check - last_check).total_seconds() / 60
        self.assertGreater(diff, 28)
        self.assertLess(diff, 32)

    def test_exhausted_after_3_checks(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        record_check(self.db_path, tid, replies=0)
        record_check(self.db_path, tid, replies=0)
        record_check(self.db_path, tid, replies=0)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "exhausted")


from gtm.revisits import (
    parse_reddit_comment_replies, parse_hn_comment_replies, parse_devto_comment_replies,
)
from gtm.revisits import get_due_revisits, schedule_next_check, run_revisits


class TestReplyParsers(unittest.TestCase):

    def test_parse_reddit_reply_found(self):
        mock_data = [
            {"kind": "Listing", "data": {"children": [{"kind": "t3", "data": {"title": "Post"}}]}},
            {"kind": "Listing", "data": {"children": [
                {"kind": "t1", "data": {
                    "author": "us",
                    "body": "our comment",
                    "replies": {"kind": "Listing", "data": {"children": [
                        {"kind": "t1", "data": {
                            "author": "replier1",
                            "body": "I agree with this take",
                            "created_utc": 1710000000,
                        }},
                    ]}},
                }},
            ]}},
        ]
        result = parse_reddit_comment_replies(mock_data, "us")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["author"], "replier1")
        self.assertEqual(result[0]["content"], "I agree with this take")

    def test_parse_reddit_no_replies(self):
        mock_data = [
            {"kind": "Listing", "data": {"children": [{"kind": "t3", "data": {"title": "Post"}}]}},
            {"kind": "Listing", "data": {"children": [
                {"kind": "t1", "data": {
                    "author": "us",
                    "body": "our comment",
                    "replies": "",
                }},
            ]}},
        ]
        result = parse_reddit_comment_replies(mock_data, "us")
        self.assertEqual(len(result), 0)

    def test_parse_hn_reply_found(self):
        mock_item = {"id": 123, "by": "us", "text": "our comment", "kids": [456, 789]}
        mock_kids = [
            {"id": 456, "by": "replier1", "text": "Nice point!", "time": 1710000000},
            {"id": 789, "by": "replier2", "text": "Disagree tbh", "time": 1710000100},
        ]
        result = parse_hn_comment_replies(mock_item, mock_kids)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["author"], "replier1")

    def test_parse_hn_no_replies(self):
        mock_item = {"id": 123, "by": "us", "text": "our comment"}
        result = parse_hn_comment_replies(mock_item, [])
        self.assertEqual(len(result), 0)

    def test_parse_devto_reply_found(self):
        mock_comment = {
            "id_code": "abc123",
            "body_html": "our comment",
            "children": [
                {"id_code": "def456", "user": {"username": "replier1"},
                 "body_html": "Good article!", "created_at": "2026-03-13T10:00:00Z"},
            ],
        }
        result = parse_devto_comment_replies(mock_comment)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["author"], "replier1")

    def test_parse_devto_no_replies(self):
        mock_comment = {"id_code": "abc123", "body_html": "our comment", "children": []}
        result = parse_devto_comment_replies(mock_comment)
        self.assertEqual(len(result), 0)


class TestRevisitOrchestrator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)
        from gtm.db import create_session, log_action
        self.session_id = create_session(self.db_path, "twitter")
        self.action_id = log_action(
            self.db_path, self.session_id, "twitter", "comment",
            "https://x.com/post/1", content="test comment",
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_due_revisits_returns_due_entries(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE reply_tracking SET next_check_at = datetime('now', '-1 minute') WHERE id = ?",
            (tid,),
        )
        conn.commit()
        conn.close()
        due = get_due_revisits(self.db_path)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["platform"], "twitter")

    def test_get_due_revisits_excludes_old(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        conn = get_connection(self.db_path)
        conn.execute(
            """UPDATE reply_tracking
               SET next_check_at = datetime('now', '-1 minute'),
                   created_at = datetime('now', '-3 days')
               WHERE id = ?""",
            (tid,),
        )
        conn.commit()
        conn.close()
        due = get_due_revisits(self.db_path)
        self.assertEqual(len(due), 0)

    def test_schedule_next_check_escalates(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE reply_tracking SET checks_done = 2 WHERE id = ?", (tid,)
        )
        conn.commit()
        conn.close()
        schedule_next_check(self.db_path, tid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        next_check = datetime.fromisoformat(row["next_check_at"])
        now = datetime.utcnow()
        diff = (next_check - now).total_seconds() / 60
        self.assertGreater(diff, 28)
        self.assertLess(diff, 32)

    def test_run_revisits_returns_summary(self):
        result = run_revisits(self.db_path)
        self.assertIn("checked", result)
        self.assertIn("replies_found", result)
        self.assertIn("no_reply", result)
        self.assertIn("exhausted", result)
        self.assertIn("needs_reply", result)

    def test_run_revisits_empty_when_nothing_due(self):
        result = run_revisits(self.db_path)
        self.assertEqual(result["checked"], 0)


from gtm.runner import InterleavedRunner


class TestRunnerRevisitIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.state_path = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finish_returns_revisit_results(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.finish()
        self.assertIsNotNone(runner.revisit_results)
        self.assertIn("checked", runner.revisit_results)
        self.assertIn("needs_reply", runner.revisit_results)

    def test_finish_includes_due_revisits(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.record_action("twitter", "comment", "https://x.com/post/1",
                             content="great post", comment_url="https://x.com/reply/1")
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE reply_tracking SET next_check_at = datetime('now', '-1 minute')"
        )
        conn.commit()
        conn.close()
        runner.finish()
        self.assertGreater(len(runner.revisit_results["pending"]), 0)

    def test_summary_includes_revisit_count(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.finish()
        s = runner.summary()
        self.assertIn("revisits", s)
