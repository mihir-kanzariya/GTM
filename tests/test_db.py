import os
import sqlite3
import tempfile
import unittest

from gtm.db import init_db, get_connection


class TestInitDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_creates_all_tables(self):
        init_db(self.db_path)
        conn = get_connection(self.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        self.assertIn("sessions", tables)
        self.assertIn("actions", tables)
        self.assertIn("outcomes", tables)
        self.assertIn("daily_metrics", tables)
        self.assertIn("reply_tracking", tables)
        self.assertIn("threads", tables)
        self.assertIn("keyword_performance", tables)
        self.assertIn("relationships", tables)
        self.assertIn("content_calendar", tables)
        self.assertIn("peak_times", tables)
        self.assertIn("decision_log", tables)

    def test_idempotent(self):
        init_db(self.db_path)
        init_db(self.db_path)  # should not raise
        conn = get_connection(self.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        self.assertEqual(len([t for t in tables if t == "sessions"]), 1)


if __name__ == "__main__":
    unittest.main()
