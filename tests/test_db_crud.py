import os
import tempfile
import unittest
from datetime import datetime, timedelta

from gtm.db import (
    init_db,
    get_connection,
    create_session,
    end_session,
    log_action,
    is_duplicate_url,
    get_promotion_ratio,
)


class TestDbCrud(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_session(self):
        sid = create_session(self.db_path, "reddit")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
        conn.close()
        self.assertEqual(row["platform"], "reddit")
        self.assertIsNotNone(row["started_at"])
        self.assertIsNone(row["ended_at"])

    def test_end_session(self):
        sid = create_session(self.db_path, "twitter")
        log_action(self.db_path, sid, "twitter", "like", "https://x.com/post/1")
        log_action(self.db_path, sid, "twitter", "comment", "https://x.com/post/2",
                   content="nice post", promoted_product="acme")
        end_session(self.db_path, sid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
        conn.close()
        self.assertIsNotNone(row["ended_at"])
        self.assertEqual(row["total_actions"], 2)
        self.assertEqual(row["promoted_count"], 1)

    def test_log_action(self):
        sid = create_session(self.db_path, "reddit")
        aid = log_action(self.db_path, sid, "reddit", "comment",
                         "https://reddit.com/r/saas/post1",
                         target_title="My SaaS journey",
                         content="great post tbh",
                         keywords_matched="saas,startup")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM actions WHERE id = ?", (aid,)).fetchone()
        conn.close()
        self.assertEqual(row["action_type"], "comment")
        self.assertEqual(row["content_written"], "great post tbh")

    def test_is_duplicate_url_true(self):
        sid = create_session(self.db_path, "reddit")
        log_action(self.db_path, sid, "reddit", "like", "https://reddit.com/r/saas/dup")
        self.assertTrue(is_duplicate_url(self.db_path, "https://reddit.com/r/saas/dup"))

    def test_is_duplicate_url_false(self):
        self.assertFalse(is_duplicate_url(self.db_path, "https://reddit.com/r/saas/new"))

    def test_promotion_ratio(self):
        sid = create_session(self.db_path, "reddit")
        for i in range(9):
            log_action(self.db_path, sid, "reddit", "like", f"https://reddit.com/{i}")
        log_action(self.db_path, sid, "reddit", "comment", "https://reddit.com/promo",
                   content="check this", promoted_product="acme")
        ratio = get_promotion_ratio(self.db_path, "reddit", days=7)
        self.assertAlmostEqual(ratio, 0.1, places=2)


if __name__ == "__main__":
    unittest.main()
