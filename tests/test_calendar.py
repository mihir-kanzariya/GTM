import os
import tempfile
import unittest
from datetime import datetime, timedelta

from gtm.db import init_db, get_connection, create_session, log_action
from gtm.calendar import add_content, get_today_content, mark_posted, get_upcoming


class TestCalendar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_content(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cid = add_content(self.db_path, "twitter", "thread",
                          "Shipping auth update", "Talk about Supabase auth flow", today)
        self.assertIsNotNone(cid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM content_calendar WHERE id = ?", (cid,)).fetchone()
        conn.close()
        self.assertEqual(row["platform"], "twitter")
        self.assertEqual(row["content_type"], "thread")
        self.assertEqual(row["status"], "planned")

    def test_get_today_content(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        add_content(self.db_path, "twitter", "thread", "Topic A", "Outline A", today)
        add_content(self.db_path, "devto", "article", "Topic B", "Outline B", today)
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        add_content(self.db_path, "twitter", "thread", "Topic C", "Outline C", tomorrow)
        result = get_today_content(self.db_path, "twitter")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["topic"], "Topic A")

    def test_get_today_content_excludes_posted(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cid = add_content(self.db_path, "twitter", "thread", "Done topic", "Done", today)
        sid = create_session(self.db_path, "twitter")
        aid = log_action(self.db_path, sid, "twitter", "comment", "https://x.com/1")
        mark_posted(self.db_path, cid, aid)
        result = get_today_content(self.db_path, "twitter")
        self.assertEqual(len(result), 0)

    def test_mark_posted(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cid = add_content(self.db_path, "twitter", "thread", "Topic", "Outline", today)
        sid = create_session(self.db_path, "twitter")
        aid = log_action(self.db_path, sid, "twitter", "comment", "https://x.com/1")
        mark_posted(self.db_path, cid, aid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM content_calendar WHERE id = ?", (cid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "posted")
        self.assertEqual(row["action_id"], aid)

    def test_get_upcoming(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        day_after = (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%d")
        far_future = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")
        add_content(self.db_path, "twitter", "thread", "Today", "O", today)
        add_content(self.db_path, "devto", "article", "Tomorrow", "O", tomorrow)
        add_content(self.db_path, "reddit", "post", "Day after", "O", day_after)
        add_content(self.db_path, "twitter", "thread", "Far future", "O", far_future)
        result = get_upcoming(self.db_path, days=3)
        self.assertEqual(len(result), 3)

    def test_get_upcoming_excludes_posted(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cid = add_content(self.db_path, "twitter", "thread", "Done", "O", today)
        sid = create_session(self.db_path, "twitter")
        aid = log_action(self.db_path, sid, "twitter", "comment", "https://x.com/1")
        mark_posted(self.db_path, cid, aid)
        add_content(self.db_path, "devto", "article", "Pending", "O", today)
        result = get_upcoming(self.db_path, days=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["topic"], "Pending")

if __name__ == "__main__":
    unittest.main()
