import unittest

from gtm.cron import build_reply_checker_prompt, REPLY_CHECK_INTERVAL_MIN


class TestCron(unittest.TestCase):
    def test_reply_check_interval(self):
        self.assertEqual(REPLY_CHECK_INTERVAL_MIN, 15)

    def test_build_reply_checker_prompt_contains_key_instructions(self):
        prompt = build_reply_checker_prompt("/path/to/gtm.db")
        self.assertIn("reply_tracking", prompt)
        self.assertIn("get_due_checks", prompt)
        self.assertIn("/path/to/gtm.db", prompt)

    def test_build_reply_checker_prompt_mentions_70_30(self):
        prompt = build_reply_checker_prompt("/path/to/db")
        self.assertIn("70", prompt)

if __name__ == "__main__":
    unittest.main()
