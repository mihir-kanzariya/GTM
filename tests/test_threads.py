import json
import os
import tempfile
import unittest

from gtm.db import init_db, get_connection, create_session
from gtm.threads import log_thread, get_recent_threads, format_thread


class TestThreads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)
        self.sid = create_session(self.db_path, "twitter")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_log_thread(self):
        tweets = [
            "This week I shipped auth for Blocpad. Here's how it went (thread)",
            "First, I tried Supabase Auth. Setup took 10 minutes.",
            "Switched to custom JWT + Supabase RLS. More control.",
            "Lesson: don't pick the easy path if your users are mostly on mobile.",
        ]
        tid = log_thread(self.db_path, self.sid, "building_in_public",
                         "Shipping auth for Blocpad", tweets, "https://x.com/mihir/status/123")
        self.assertIsNotNone(tid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM threads WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["thread_type"], "building_in_public")
        self.assertEqual(row["tweet_count"], 4)
        stored_tweets = json.loads(row["content"])
        self.assertEqual(len(stored_tweets), 4)

    def test_get_recent_threads_returns_recent(self):
        tweets = ["tweet1", "tweet2", "tweet3"]
        log_thread(self.db_path, self.sid, "general_founder", "Topic A", tweets, "https://x.com/1")
        log_thread(self.db_path, self.sid, "building_in_public", "Topic B", tweets, "https://x.com/2")
        recent = get_recent_threads(self.db_path, days=7)
        self.assertEqual(len(recent), 2)

    def test_get_recent_threads_returns_topics(self):
        tweets = ["tweet1", "tweet2"]
        log_thread(self.db_path, self.sid, "general_founder", "Hot take on tools", tweets, "https://x.com/1")
        recent = get_recent_threads(self.db_path, days=7)
        self.assertEqual(recent[0]["topic"], "Hot take on tools")

    def test_format_thread_enforces_280_limit(self):
        tweets = ["Short tweet", "A" * 300, "Another short one"]
        formatted = format_thread(tweets)
        for tweet in formatted:
            self.assertLessEqual(len(tweet), 280)

    def test_format_thread_preserves_short_tweets(self):
        tweets = ["Short tweet", "Another one"]
        formatted = format_thread(tweets)
        self.assertEqual(formatted[0], "Short tweet")
        self.assertEqual(formatted[1], "Another one")

if __name__ == "__main__":
    unittest.main()
