import os
import tempfile
import unittest

from gtm.db import init_db, get_connection


class TestIntelligenceSchema(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)
        self.conn = get_connection(self.db_path)

    def tearDown(self):
        self.conn.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_niche_profile_table_exists(self):
        self.conn.execute("INSERT INTO niche_profile (key, value) VALUES ('industries', '[\"ai\"]')")
        row = self.conn.execute("SELECT value FROM niche_profile WHERE key = 'industries'").fetchone()
        self.assertEqual(row["value"], '["ai"]')

    def test_content_signals_table_exists(self):
        self.conn.execute(
            "INSERT INTO content_signals (platform, title, text_snippet) VALUES ('twitter', 'Test', 'snippet')"
        )
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM content_signals").fetchone()
        self.assertEqual(row["cnt"], 1)

    def test_topic_clusters_table_exists(self):
        self.conn.execute(
            "INSERT INTO topic_clusters (name, description, key_phrases) VALUES ('AI agents', 'test', '[\"ai agents\"]')"
        )
        row = self.conn.execute("SELECT name FROM topic_clusters WHERE name = 'AI agents'").fetchone()
        self.assertEqual(row["name"], "AI agents")

    def test_niche_profile_unique_key(self):
        self.conn.execute("INSERT INTO niche_profile (key, value) VALUES ('industries', '[\"ai\"]')")
        self.conn.commit()
        with self.assertRaises(Exception):
            self.conn.execute("INSERT INTO niche_profile (key, value) VALUES ('industries', '[\"saas\"]')")


from gtm.niche import get_niche, set_niche_field, add_product, get_products, is_excluded_topic


class TestNicheProfile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_set_and_get_industries(self):
        set_niche_field(self.db_path, "industries", ["ai", "saas", "developer-tools"])
        niche = get_niche(self.db_path)
        self.assertEqual(niche["industries"], ["ai", "saas", "developer-tools"])

    def test_set_and_get_audiences(self):
        set_niche_field(self.db_path, "audiences", ["developers", "founders"])
        niche = get_niche(self.db_path)
        self.assertEqual(niche["audiences"], ["developers", "founders"])

    def test_set_and_get_exclude(self):
        set_niche_field(self.db_path, "exclude", ["politics", "crypto"])
        niche = get_niche(self.db_path)
        self.assertEqual(niche["exclude"], ["politics", "crypto"])

    def test_add_product(self):
        add_product(self.db_path, "acme.com", "bug reporting tool")
        products = get_products(self.db_path)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["url"], "acme.com")

    def test_add_multiple_products(self):
        add_product(self.db_path, "acme.com", "bug reporting")
        add_product(self.db_path, "acme.com", "workspace")
        products = get_products(self.db_path)
        self.assertEqual(len(products), 2)

    def test_is_excluded_topic(self):
        set_niche_field(self.db_path, "exclude", ["politics", "crypto", "gaming"])
        self.assertTrue(is_excluded_topic(self.db_path, "Bitcoin crypto price"))
        self.assertTrue(is_excluded_topic(self.db_path, "Political debate 2026"))
        self.assertFalse(is_excluded_topic(self.db_path, "AI agents for developer tools"))

    def test_empty_niche_returns_defaults(self):
        niche = get_niche(self.db_path)
        self.assertEqual(niche["industries"], [])
        self.assertEqual(niche["audiences"], [])
        self.assertEqual(niche["exclude"], [])


from gtm.goals import get_goals, set_goal, get_goal_for_platform, VALID_GOALS


class TestGoals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_goal_is_balanced(self):
        goals = get_goals(self.state_path)
        self.assertEqual(goals["default"], "balanced")

    def test_set_global_goal(self):
        set_goal(self.state_path, "visibility")
        goals = get_goals(self.state_path)
        self.assertEqual(goals["default"], "visibility")

    def test_set_platform_goal(self):
        set_goal(self.state_path, "conversions", platform="twitter")
        goals = get_goals(self.state_path)
        self.assertEqual(goals["platforms"]["twitter"], "conversions")

    def test_get_goal_for_platform_uses_override(self):
        set_goal(self.state_path, "visibility")
        set_goal(self.state_path, "relationships", platform="reddit")
        self.assertEqual(get_goal_for_platform(self.state_path, "reddit"), "relationships")
        self.assertEqual(get_goal_for_platform(self.state_path, "twitter"), "visibility")

    def test_invalid_goal_raises(self):
        with self.assertRaises(ValueError):
            set_goal(self.state_path, "invalid_goal")

    def test_valid_goals_list(self):
        self.assertIn("visibility", VALID_GOALS)
        self.assertIn("conversions", VALID_GOALS)
        self.assertIn("relationships", VALID_GOALS)
        self.assertIn("balanced", VALID_GOALS)


from gtm.intelligence import (
    store_signal, store_signals,
    create_topic, get_topic, get_topics_by_status, update_topic_mentions,
    compute_trend_score, compute_opportunity_score, transition_statuses, expire_stale,
    get_briefing, get_weak_signals, get_content_opportunities,
    update_feedback,
)
from gtm.goals import set_goal
from gtm.niche import set_niche_field


class TestSignalStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_store_single_signal(self):
        sid = store_signal(self.db_path, {
            "platform": "twitter",
            "title": "AI agents are changing everything",
            "text_snippet": "Long text about AI agents...",
            "author": "@dev_user",
            "engagement": 42,
            "source_url": "https://x.com/dev_user/123",
        })
        self.assertIsNotNone(sid)

    def test_store_multiple_signals(self):
        signals = [
            {"platform": "twitter", "title": "Post 1", "text_snippet": "text1"},
            {"platform": "reddit", "title": "Post 2", "text_snippet": "text2"},
            {"platform": "hackernews", "title": "Post 3", "text_snippet": "text3"},
        ]
        ids = store_signals(self.db_path, signals)
        self.assertEqual(len(ids), 3)


class TestTopicClusters(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_topic(self):
        tid = create_topic(self.db_path, {
            "name": "AI agents",
            "description": "Discussion about AI agent frameworks",
            "key_phrases": ["ai agents", "agent framework", "autonomous agents"],
            "platforms_seen": ["twitter", "hackernews"],
            "total_mentions": 5,
            "relevance": "high",
        })
        topic = get_topic(self.db_path, tid)
        self.assertEqual(topic["name"], "AI agents")
        self.assertEqual(topic["status"], "weak")
        self.assertEqual(topic["platform_count"], 2)

    def test_get_topics_by_status(self):
        create_topic(self.db_path, {"name": "Topic A", "key_phrases": [], "platforms_seen": [], "total_mentions": 3, "relevance": "high"})
        create_topic(self.db_path, {"name": "Topic B", "key_phrases": [], "platforms_seen": [], "total_mentions": 10, "relevance": "high"})
        weak = get_topics_by_status(self.db_path, "weak")
        self.assertEqual(len(weak), 2)

    def test_update_topic_mentions(self):
        tid = create_topic(self.db_path, {"name": "Test", "key_phrases": [], "platforms_seen": ["twitter"], "total_mentions": 3, "relevance": "high"})
        update_topic_mentions(self.db_path, tid, new_mentions=5, new_platforms=["twitter", "reddit"])
        topic = get_topic(self.db_path, tid)
        self.assertEqual(topic["total_mentions"], 8)
        self.assertEqual(topic["platform_count"], 2)

    def test_compute_trend_score(self):
        tid = create_topic(self.db_path, {
            "name": "Trending",
            "key_phrases": [],
            "platforms_seen": ["twitter", "reddit", "hackernews"],
            "total_mentions": 25,
            "relevance": "high",
            "authority_score": 10,
            "velocity": 2.0,
        })
        compute_trend_score(self.db_path, tid)
        topic = get_topic(self.db_path, tid)
        self.assertGreater(topic["trend_score"], 0)

    def test_transition_weak_to_emerging(self):
        tid = create_topic(self.db_path, {
            "name": "Rising",
            "key_phrases": [],
            "platforms_seen": ["twitter"],
            "total_mentions": 10,
            "relevance": "high",
            "velocity": 1.5,
        })
        compute_trend_score(self.db_path, tid)
        transition_statuses(self.db_path)
        topic = get_topic(self.db_path, tid)
        self.assertEqual(topic["status"], "emerging")

    def test_expire_stale_topics(self):
        conn = get_connection(self.db_path)
        conn.execute(
            """INSERT INTO topic_clusters (name, key_phrases, platforms_seen, status, total_mentions, relevance, last_seen_at)
               VALUES ('Old topic', '[]', '[]', 'weak', 3, 'medium', datetime('now', '-6 days'))"""
        )
        conn.commit()
        conn.close()
        expire_stale(self.db_path)
        topics = get_topics_by_status(self.db_path, "expired")
        self.assertEqual(len(topics), 1)


class TestBriefing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.state_path = os.path.join(self.tmp, "state.json")
        init_db(self.db_path)
        set_niche_field(self.db_path, "industries", ["ai", "saas"])
        set_niche_field(self.db_path, "exclude", ["politics", "crypto"])

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_briefing_returns_required_keys(self):
        briefing = get_briefing(self.db_path, self.state_path)
        required_keys = ["topics", "weak_signals", "opportunities", "niche", "goal", "promo_status"]
        for key in required_keys:
            self.assertIn(key, briefing, f"Missing key: {key}")

    def test_briefing_includes_active_topics(self):
        create_topic(self.db_path, {
            "name": "AI agents", "key_phrases": ["ai agents"],
            "platforms_seen": ["twitter"], "total_mentions": 10,
            "relevance": "high", "velocity": 1.0,
        })
        compute_trend_score(self.db_path, 1)
        briefing = get_briefing(self.db_path, self.state_path)
        self.assertGreater(len(briefing["topics"]), 0)

    def test_weak_signals_returns_filtered(self):
        create_topic(self.db_path, {
            "name": "MCP servers", "key_phrases": ["mcp"],
            "platforms_seen": ["twitter", "hackernews"],
            "total_mentions": 4, "relevance": "high",
            "velocity": 1.0, "authority_score": 6,
        })
        compute_trend_score(self.db_path, 1)
        signals = get_weak_signals(self.db_path)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["name"], "MCP servers")

    def test_opportunities_respect_goal(self):
        for i, name in enumerate(["Topic A", "Topic B"]):
            create_topic(self.db_path, {
                "name": name, "key_phrases": [],
                "platforms_seen": ["twitter"], "total_mentions": 15,
                "relevance": "high", "velocity": 1.0,
            })
            compute_trend_score(self.db_path, i + 1)
            compute_opportunity_score(self.db_path, i + 1, goal="visibility")
        opps = get_content_opportunities(self.db_path, goal="visibility", limit=5)
        self.assertGreater(len(opps), 0)


class TestFeedback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_update_feedback_marks_proven(self):
        # Create a topic
        tid = create_topic(self.db_path, {
            "name": "Hot topic", "key_phrases": ["hot"],
            "platforms_seen": ["twitter"], "total_mentions": 25,
            "relevance": "high", "velocity": 1.0,
        })
        # Simulate: we posted about it (times_we_posted > 0) and got engagement
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE topic_clusters SET times_we_posted = 2, avg_engagement = 15.0, status = 'confirmed' WHERE id = ?",
            (tid,),
        )
        conn.commit()
        conn.close()

        update_feedback(self.db_path)
        topic = get_topic(self.db_path, tid)
        self.assertEqual(topic["status"], "proven")


try:
    from gtm.collectors import (
        parse_reddit_response, parse_hn_stories, parse_devto_response,
        build_search_queries,
    )
    _has_collectors = True
except ImportError:
    _has_collectors = False


@unittest.skipUnless(_has_collectors, "gtm.collectors not yet implemented")
class TestCollectors(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parse_reddit_response(self):
        mock_data = {
            "data": {
                "children": [
                    {"data": {"title": "AI agents discussion", "selftext": "text here",
                              "author": "user1", "score": 42, "url": "https://reddit.com/1",
                              "permalink": "/r/webdev/comments/1"}},
                    {"data": {"title": "Best dev tools 2026", "selftext": "list",
                              "author": "user2", "score": 18, "url": "https://reddit.com/2",
                              "permalink": "/r/webdev/comments/2"}},
                ]
            }
        }
        signals = parse_reddit_response(mock_data, "reddit")
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0]["platform"], "reddit")
        self.assertEqual(signals[0]["engagement"], 42)
        self.assertEqual(signals[0]["author"], "user1")

    def test_parse_hn_stories(self):
        mock_stories = [
            {"title": "Show HN: AI coding tool", "by": "hacker1", "score": 200,
             "url": "https://example.com", "id": 123},
            {"title": "MCP servers explained", "by": "hacker2", "score": 85,
             "url": "https://example2.com", "id": 456},
        ]
        signals = parse_hn_stories(mock_stories)
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0]["platform"], "hackernews")
        self.assertGreater(signals[0]["engagement"], 0)

    def test_parse_devto_response(self):
        mock_articles = [
            {"title": "Building with AI", "description": "How to...", "user": {"username": "dev1"},
             "positive_reactions_count": 30, "url": "https://dev.to/article1", "tag_list": ["ai", "tutorial"]},
        ]
        signals = parse_devto_response(mock_articles)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["platform"], "devto")

    def test_build_search_queries(self):
        from gtm.niche import set_niche_field
        set_niche_field(self.db_path, "industries", ["ai", "saas", "developer-tools"])
        queries = build_search_queries(self.db_path)
        self.assertGreater(len(queries), 0)
        combined = " ".join(queries)
        self.assertTrue("ai" in combined.lower() or "saas" in combined.lower())
