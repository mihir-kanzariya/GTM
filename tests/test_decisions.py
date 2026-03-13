import os
import tempfile
import unittest
from datetime import datetime, timedelta

from gtm.db import init_db, get_connection, create_session, log_action
from gtm.decisions import (
    log_decision,
    get_recent_decisions,
    get_session_decisions,
    get_decision_summary,
)


class TestDecisions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.state_path = os.path.join(self.tmp, "state.json")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_log_decision(self):
        did = log_decision(self.db_path, category="keyword",
                           decision="Used 'bug reporting tool' on reddit",
                           reasoning="Score 8.2, top performer", platform="reddit")
        self.assertIsNotNone(did)
        self.assertIsInstance(did, int)

    def test_log_decision_with_context(self):
        did = log_decision(self.db_path, category="promotion",
                           decision="Promoted acme",
                           reasoning="Ratio at 6%, post about bug tracking",
                           context='{"action_id": 42, "ratio": 0.06}', platform="reddit")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM decision_log WHERE id = ?", (did,)).fetchone()
        conn.close()
        self.assertEqual(row["category"], "promotion")
        self.assertIn("42", row["context"])

    def test_log_decision_with_session(self):
        sid = create_session(self.db_path, "twitter")
        did = log_decision(self.db_path, category="engagement",
                           decision="Enrolled comment for tracking",
                           reasoning="Standard enrollment", session_id=sid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM decision_log WHERE id = ?", (did,)).fetchone()
        conn.close()
        self.assertEqual(row["session_id"], sid)

    def test_get_recent_decisions(self):
        for i in range(5):
            log_decision(self.db_path, "keyword", f"Decision {i}", "reason")
        log_decision(self.db_path, "promotion", "Promo decision", "reason")
        results = get_recent_decisions(self.db_path, category="keyword", limit=3)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["decision"], "Decision 4")

    def test_get_recent_decisions_all_categories(self):
        log_decision(self.db_path, "keyword", "K1", "r")
        log_decision(self.db_path, "promotion", "P1", "r")
        results = get_recent_decisions(self.db_path, limit=10)
        self.assertEqual(len(results), 2)

    def test_get_recent_decisions_by_platform(self):
        log_decision(self.db_path, "keyword", "Reddit keyword", "r", platform="reddit")
        log_decision(self.db_path, "keyword", "Twitter keyword", "r", platform="twitter")
        results = get_recent_decisions(self.db_path, platform="reddit")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["decision"], "Reddit keyword")

    def test_get_session_decisions(self):
        sid = create_session(self.db_path, "twitter")
        log_decision(self.db_path, "engagement", "D1", "r", session_id=sid)
        log_decision(self.db_path, "reply", "D2", "r", session_id=sid)
        log_decision(self.db_path, "keyword", "D3", "r")
        results = get_session_decisions(self.db_path, sid)
        self.assertEqual(len(results), 2)

    def test_get_decision_summary(self):
        sid = create_session(self.db_path, "reddit")
        log_action(self.db_path, sid, "reddit", "like", "https://reddit.com/1")
        log_action(self.db_path, sid, "reddit", "comment", "https://reddit.com/2", content="test comment")
        log_decision(self.db_path, "keyword", "Used 'saas tools'", "top scorer", platform="reddit", session_id=sid)
        summary = get_decision_summary(self.db_path, days=7)
        self.assertIn("total_actions", summary)
        self.assertIn("recent_decisions", summary)
        self.assertIsInstance(summary["recent_decisions"], list)

if __name__ == "__main__":
    unittest.main()
