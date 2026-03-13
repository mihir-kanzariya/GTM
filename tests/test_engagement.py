import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from gtm.db import init_db, get_connection, create_session, log_action
from gtm.engagement import (
    enroll_for_tracking,
    get_due_checks,
    record_check,
    should_reply,
    mark_replied,
    mark_exhausted,
    get_active_tracking_count,
)


class TestEngagement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)
        self.sid = create_session(self.db_path, "reddit")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_enroll_for_tracking(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/r/saas/post1", content="great post")
        tid = enroll_for_tracking(self.db_path, aid, "reddit",
                                  "https://reddit.com/r/saas/post1",
                                  "https://reddit.com/r/saas/post1#comment123")
        self.assertIsNotNone(tid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["checks_done"], 0)
        self.assertEqual(row["max_checks"], 3)
        self.assertIsNotNone(row["next_check_at"])

    def test_enroll_sets_next_check_15min(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        next_check = datetime.fromisoformat(row["next_check_at"])
        now = datetime.utcnow()
        diff = (next_check - now).total_seconds()
        self.assertGreater(diff, 800)
        self.assertLess(diff, 1000)

    def test_enroll_duplicate_action_ignored(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid1 = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        tid2 = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        self.assertEqual(tid1, tid2)

    def test_get_due_checks_returns_due_entries(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        conn = get_connection(self.db_path)
        conn.execute("UPDATE reply_tracking SET next_check_at = datetime('now', '-1 minute')")
        conn.commit()
        conn.close()
        due = get_due_checks(self.db_path)
        self.assertEqual(len(due), 1)

    def test_get_due_checks_skips_future(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        due = get_due_checks(self.db_path)
        self.assertEqual(len(due), 0)

    def test_get_due_checks_skips_exhausted(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        mark_exhausted(self.db_path, tid)
        conn = get_connection(self.db_path)
        conn.execute("UPDATE reply_tracking SET next_check_at = datetime('now', '-1 minute')")
        conn.commit()
        conn.close()
        due = get_due_checks(self.db_path)
        self.assertEqual(len(due), 0)

    def test_record_check_increments_count(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        record_check(self.db_path, tid, upvotes=5, replies=1,
                     reply_content="nice!", reply_author="devguy")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["checks_done"], 1)
        self.assertIsNotNone(row["last_checked_at"])

    def test_record_check_creates_outcome(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        record_check(self.db_path, tid, upvotes=5, replies=1,
                     reply_content="nice!", reply_author="devguy")
        conn = get_connection(self.db_path)
        outcome = conn.execute("SELECT * FROM outcomes WHERE action_id = ?", (aid,)).fetchone()
        conn.close()
        self.assertEqual(outcome["upvotes"], 5)
        self.assertEqual(outcome["replies"], 1)
        self.assertEqual(outcome["reply_content"], "nice!")
        self.assertEqual(outcome["check_number"], 1)

    def test_record_check_auto_exhausts_at_max(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        record_check(self.db_path, tid, upvotes=0, replies=0)
        record_check(self.db_path, tid, upvotes=0, replies=0)
        record_check(self.db_path, tid, upvotes=0, replies=0)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "exhausted")
        self.assertEqual(row["checks_done"], 3)

    def test_should_reply_returns_bool(self):
        result = should_reply("Great point!")
        self.assertIsInstance(result, bool)

    def test_should_reply_probability(self):
        true_count = sum(1 for _ in range(1000) if should_reply("test"))
        self.assertGreater(true_count, 600)
        self.assertLess(true_count, 800)

    def test_mark_replied(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        reply_aid = log_action(self.db_path, self.sid, "reddit", "comment",
                               "https://reddit.com/1", content="thanks!")
        mark_replied(self.db_path, tid, reply_aid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "replied")

    def test_mark_exhausted(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        mark_exhausted(self.db_path, tid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "exhausted")

    def test_get_active_tracking_count(self):
        for i in range(3):
            aid = log_action(self.db_path, self.sid, "reddit", "comment",
                             f"https://reddit.com/{i}", content="test")
            enroll_for_tracking(self.db_path, aid, "reddit", f"https://reddit.com/{i}")
        count = get_active_tracking_count(self.db_path)
        self.assertEqual(count, 3)

    def test_get_active_tracking_count_excludes_exhausted(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        mark_exhausted(self.db_path, tid)
        count = get_active_tracking_count(self.db_path)
        self.assertEqual(count, 0)

if __name__ == "__main__":
    unittest.main()
