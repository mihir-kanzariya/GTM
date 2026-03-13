import os
import tempfile
import unittest

from gtm.db import init_db, create_session, log_action, end_session
from gtm.stats import weekly_report, get_alerts


class TestWeeklyReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)
        sid = create_session(self.db_path, "reddit")
        log_action(self.db_path, sid, "reddit", "like", "https://reddit.com/1")
        log_action(self.db_path, sid, "reddit", "comment", "https://reddit.com/2",
                   content="great post", promoted_product="blocpad")
        log_action(self.db_path, sid, "reddit", "like", "https://reddit.com/3")
        end_session(self.db_path, sid)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_report_returns_string(self):
        report = weekly_report(self.db_path)
        self.assertIsInstance(report, str)

    def test_report_contains_platform(self):
        report = weekly_report(self.db_path)
        self.assertIn("reddit", report.lower())

    def test_report_contains_totals(self):
        report = weekly_report(self.db_path)
        self.assertIn("TOTAL", report)


class TestAlerts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.state_path = os.path.join(self.tmp, "state.json")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_alerts_returns_list(self):
        from gtm.state import create_default_state, save_state
        state = create_default_state()
        save_state(self.state_path, state)
        alerts = get_alerts(self.db_path, self.state_path)
        self.assertIsInstance(alerts, list)


if __name__ == "__main__":
    unittest.main()
