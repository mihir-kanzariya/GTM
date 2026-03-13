import json
import os
import tempfile
import unittest

from gtm.db import init_db, get_connection, create_session, log_action
from gtm.relationships import (
    track_interaction, get_known_users, get_high_value_users, is_known_user,
)


class TestRelationships(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)
        self.sid = create_session(self.db_path, "reddit")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_track_interaction_creates_relationship(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        track_interaction(self.db_path, "reddit", "devguy42", "Dev Guy", aid, "comment")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM relationships WHERE platform = ? AND username = ?",
                           ("reddit", "devguy42")).fetchone()
        conn.close()
        self.assertEqual(row["interaction_count"], 1)
        self.assertEqual(row["display_name"], "Dev Guy")

    def test_track_interaction_increments_count(self):
        aid1 = log_action(self.db_path, self.sid, "reddit", "comment",
                          "https://reddit.com/1", content="test")
        aid2 = log_action(self.db_path, self.sid, "reddit", "like", "https://reddit.com/2")
        track_interaction(self.db_path, "reddit", "devguy42", "Dev Guy", aid1, "comment")
        track_interaction(self.db_path, "reddit", "devguy42", "Dev Guy", aid2, "like")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM relationships WHERE platform = ? AND username = ?",
                           ("reddit", "devguy42")).fetchone()
        conn.close()
        self.assertEqual(row["interaction_count"], 2)

    def test_track_interaction_stores_interactions_json(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        track_interaction(self.db_path, "reddit", "devguy42", "Dev Guy", aid, "comment")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT interactions FROM relationships WHERE username = ?",
                           ("devguy42",)).fetchone()
        conn.close()
        interactions = json.loads(row["interactions"])
        self.assertEqual(len(interactions), 1)
        self.assertEqual(interactions[0]["type"], "comment")
        self.assertEqual(interactions[0]["action_id"], aid)

    def test_get_known_users(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        track_interaction(self.db_path, "reddit", "user1", "User 1", aid, "comment")
        track_interaction(self.db_path, "reddit", "user2", "User 2", aid, "like")
        track_interaction(self.db_path, "twitter", "user3", "User 3", aid, "follow")
        users = get_known_users(self.db_path, "reddit")
        self.assertEqual(len(users), 2)

    def test_get_high_value_users(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        for _ in range(3):
            track_interaction(self.db_path, "reddit", "frequent_user", "Freq", aid, "comment")
        track_interaction(self.db_path, "reddit", "onetime_user", "Once", aid, "like")
        high = get_high_value_users(self.db_path, "reddit", min_interactions=3)
        self.assertEqual(len(high), 1)
        self.assertEqual(high[0]["username"], "frequent_user")

    def test_is_known_user_true(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        track_interaction(self.db_path, "reddit", "known_user", "Known", aid, "comment")
        self.assertTrue(is_known_user(self.db_path, "reddit", "known_user"))

    def test_is_known_user_false(self):
        self.assertFalse(is_known_user(self.db_path, "reddit", "stranger"))

    def test_is_known_user_wrong_platform(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        track_interaction(self.db_path, "reddit", "reddit_user", "RU", aid, "comment")
        self.assertFalse(is_known_user(self.db_path, "twitter", "reddit_user"))

if __name__ == "__main__":
    unittest.main()
