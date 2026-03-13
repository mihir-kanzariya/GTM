import os
import tempfile
import unittest
from datetime import datetime

from gtm.db import init_db, get_connection
from gtm.analytics import (
    update_keyword_score, get_weighted_keywords, update_peak_times,
    get_best_hours, calculate_engagement_score, seed_keywords,
)


class TestKeywordPerformance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_update_keyword_score_creates_entry(self):
        update_keyword_score(self.db_path, "bug reporting tool", "reddit", replies=2, upvotes=5)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM keyword_performance WHERE keyword = ? AND platform = ?",
                           ("bug reporting tool", "reddit")).fetchone()
        conn.close()
        self.assertEqual(row["times_used"], 1)
        self.assertEqual(row["replies_received"], 2)
        self.assertGreater(row["score"], 0)

    def test_update_keyword_score_accumulates(self):
        update_keyword_score(self.db_path, "saas tools", "twitter", replies=1, upvotes=3)
        update_keyword_score(self.db_path, "saas tools", "twitter", replies=2, upvotes=4)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM keyword_performance WHERE keyword = ? AND platform = ?",
                           ("saas tools", "twitter")).fetchone()
        conn.close()
        self.assertEqual(row["times_used"], 2)
        self.assertEqual(row["replies_received"], 3)

    def test_get_weighted_keywords_returns_list(self):
        update_keyword_score(self.db_path, "kw1", "reddit", replies=10, upvotes=20)
        update_keyword_score(self.db_path, "kw2", "reddit", replies=1, upvotes=2)
        update_keyword_score(self.db_path, "kw3", "reddit", replies=5, upvotes=10)
        result = get_weighted_keywords(self.db_path, "reddit", n=3)
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[0], tuple)
        self.assertEqual(len(result[0]), 2)

    def test_get_weighted_keywords_empty_platform(self):
        result = get_weighted_keywords(self.db_path, "twitter", n=5)
        self.assertEqual(len(result), 0)

    def test_seed_keywords(self):
        seed_keywords(self.db_path, "reddit", ["bug reporting", "saas tools", "project management"])
        conn = get_connection(self.db_path)
        rows = conn.execute("SELECT * FROM keyword_performance WHERE platform = ?", ("reddit",)).fetchall()
        conn.close()
        self.assertEqual(len(rows), 3)

    def test_seed_keywords_idempotent(self):
        seed_keywords(self.db_path, "reddit", ["bug reporting"])
        seed_keywords(self.db_path, "reddit", ["bug reporting"])
        conn = get_connection(self.db_path)
        rows = conn.execute("SELECT * FROM keyword_performance WHERE platform = ? AND keyword = ?",
                           ("reddit", "bug reporting")).fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)


class TestPeakTimes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_update_peak_times_creates_entry(self):
        update_peak_times(self.db_path, "twitter", day=2, hour=14, replies=3, upvotes=10)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM peak_times WHERE platform = ? AND day_of_week = ? AND hour = ?",
                           ("twitter", 2, 14)).fetchone()
        conn.close()
        self.assertEqual(row["sample_count"], 1)
        self.assertGreater(row["engagement_score"], 0)

    def test_update_peak_times_accumulates(self):
        update_peak_times(self.db_path, "twitter", day=2, hour=14, replies=2, upvotes=6)
        update_peak_times(self.db_path, "twitter", day=2, hour=14, replies=4, upvotes=10)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM peak_times WHERE platform = ? AND day_of_week = ? AND hour = ?",
                           ("twitter", 2, 14)).fetchone()
        conn.close()
        self.assertEqual(row["sample_count"], 2)
        self.assertAlmostEqual(row["avg_replies"], 3.0, places=1)

    def test_get_best_hours(self):
        update_peak_times(self.db_path, "twitter", day=0, hour=10, replies=1, upvotes=2)
        update_peak_times(self.db_path, "twitter", day=2, hour=14, replies=5, upvotes=15)
        update_peak_times(self.db_path, "twitter", day=4, hour=16, replies=3, upvotes=8)
        result = get_best_hours(self.db_path, "twitter", top_n=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["hour"], 14)

    def test_get_best_hours_empty(self):
        result = get_best_hours(self.db_path, "reddit", top_n=3)
        self.assertEqual(len(result), 0)


class TestEngagementScoring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_calculate_engagement_score_with_outcomes(self):
        from gtm.db import create_session, log_action
        sid = create_session(self.db_path, "reddit")
        aid = log_action(self.db_path, sid, "reddit", "comment", "https://reddit.com/1", content="test")
        conn = get_connection(self.db_path)
        conn.execute("INSERT INTO outcomes (action_id, check_number, upvotes, replies) VALUES (?, 1, 10, 2)", (aid,))
        conn.commit()
        conn.close()
        score = calculate_engagement_score(self.db_path, aid)
        self.assertEqual(score, 20)

    def test_calculate_engagement_score_no_outcomes(self):
        from gtm.db import create_session, log_action
        sid = create_session(self.db_path, "reddit")
        aid = log_action(self.db_path, sid, "reddit", "comment", "https://reddit.com/1", content="test")
        score = calculate_engagement_score(self.db_path, aid)
        self.assertEqual(score, 0)

if __name__ == "__main__":
    unittest.main()
