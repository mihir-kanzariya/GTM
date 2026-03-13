# Topic Intelligence Engine — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a topic intelligence pipeline that collects signals, detects trends, scores opportunities, and feeds structured context to the AI agent before and during GTM sessions.

**Architecture:** New module `gtm/intelligence.py` with 6 layers — signal collection (WebSearch/WebFetch), topic clustering (Claude semantic grouping), trend scoring (velocity + authority + cross-platform), opportunity detection (goal-weighted), content angle generation, and feedback learning. Niche profile filters ensure the system stays within the user's industry. Goals are user-configurable globally or per-platform.

**Tech Stack:** Python 3, SQLite, existing gtm package. No external dependencies beyond what's already used.

**Design doc:** `docs/plans/2026-03-13-topic-intelligence-engine-design.md`

---

## Task 1: Add new DB tables (schema)

Add 3 new tables to `gtm/db.py`: `niche_profile`, `content_signals`, `topic_clusters`. Keep existing `keyword_performance` table for backwards compat but add new tables alongside.

**Files:**
- Modify: `gtm/db.py` (add tables to `init_db()`)
- Test: `tests/test_intelligence.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_intelligence.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_intelligence.py -v`
Expected: FAIL — tables don't exist yet

**Step 3: Add tables to `gtm/db.py` init_db()**

Add these CREATE TABLE statements inside the existing `conn.executescript("""...""")` block in `init_db()`, after the `decision_log` table:

```sql
CREATE TABLE IF NOT EXISTS niche_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    source_url TEXT,
    title TEXT,
    text_snippet TEXT,
    author TEXT,
    author_followers INTEGER DEFAULT 0,
    engagement INTEGER DEFAULT 0,
    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,
    topic_id INTEGER REFERENCES topic_clusters(id)
);

CREATE TABLE IF NOT EXISTS topic_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    key_phrases TEXT,
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME,
    status TEXT DEFAULT 'weak',
    total_mentions INTEGER DEFAULT 0,
    platforms_seen TEXT,
    platform_count INTEGER DEFAULT 0,
    velocity REAL DEFAULT 0,
    authority_score REAL DEFAULT 0,
    trend_score REAL DEFAULT 0,
    relevance TEXT DEFAULT 'unknown',
    saturation REAL DEFAULT 0,
    engagement_potential REAL DEFAULT 0,
    opportunity_score REAL DEFAULT 0,
    times_we_posted INTEGER DEFAULT 0,
    avg_engagement REAL DEFAULT 0,
    best_angle TEXT,
    expires_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_content_signals_platform ON content_signals(platform, discovered_at);
CREATE INDEX IF NOT EXISTS idx_content_signals_topic ON content_signals(topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_clusters_status ON topic_clusters(status, trend_score);
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_intelligence.py -v`
Expected: All 4 tests PASS

**Step 5: Run full test suite**

Run: `pytest tests/ -q`
Expected: All existing tests still pass (schema is additive)

**Step 6: Commit**

```bash
git add gtm/db.py tests/test_intelligence.py
git commit -m "feat: add niche_profile, content_signals, topic_clusters tables"
```

---

## Task 2: Niche profile CRUD (`gtm/niche.py`)

Create functions to read/write niche profile (industries, audiences, exclusions, products).

**Files:**
- Create: `gtm/niche.py`
- Test: `tests/test_intelligence.py` (extend)

**Step 1: Write the failing tests**

Add to `tests/test_intelligence.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_intelligence.py::TestNicheProfile -v`
Expected: FAIL — module doesn't exist

**Step 3: Create `gtm/niche.py`**

```python
import json
from gtm.db import get_connection


def get_niche(db_path):
    """Return full niche profile as dict."""
    conn = get_connection(db_path)
    rows = conn.execute("SELECT key, value FROM niche_profile").fetchall()
    conn.close()
    result = {"industries": [], "audiences": [], "exclude": [], "products": []}
    for row in rows:
        result[row["key"]] = json.loads(row["value"])
    return result


def set_niche_field(db_path, key, values):
    """Set a niche field (industries, audiences, exclude)."""
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO niche_profile (key, value, updated_at)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (key, json.dumps(values)),
    )
    conn.commit()
    conn.close()


def add_product(db_path, url, description):
    """Add a product to the niche profile."""
    products = get_products(db_path)
    # Don't add duplicates
    if any(p["url"] == url for p in products):
        return
    products.append({"url": url, "desc": description})
    set_niche_field(db_path, "products", products)


def get_products(db_path):
    """Return list of products from niche profile."""
    niche = get_niche(db_path)
    return niche.get("products", [])


def is_excluded_topic(db_path, topic_text):
    """Check if a topic matches any exclusion terms."""
    niche = get_niche(db_path)
    excluded = niche.get("exclude", [])
    topic_lower = topic_text.lower()
    return any(term.lower() in topic_lower for term in excluded)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_intelligence.py::TestNicheProfile -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add gtm/niche.py tests/test_intelligence.py
git commit -m "feat: add niche profile CRUD (industries, audiences, exclude, products)"
```

---

## Task 3: Goal system (`gtm/goals.py`)

User-configurable goals stored in state.json. Global default + per-platform overrides.

**Files:**
- Create: `gtm/goals.py`
- Test: `tests/test_intelligence.py` (extend)

**Step 1: Write the failing tests**

Add to `tests/test_intelligence.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_intelligence.py::TestGoals -v`
Expected: FAIL — module doesn't exist

**Step 3: Create `gtm/goals.py`**

```python
import json
import os

VALID_GOALS = ["visibility", "conversions", "relationships", "balanced"]


def _load_state(state_path):
    if not os.path.exists(state_path):
        return {}
    with open(state_path, "r") as f:
        return json.load(f)


def _save_state(state_path, state):
    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def get_goals(state_path):
    """Return goals dict with 'default' and 'platforms' keys."""
    state = _load_state(state_path)
    goals = state.get("goals", {})
    return {
        "default": goals.get("default", "balanced"),
        "platforms": goals.get("platforms", {}),
    }


def set_goal(state_path, goal, platform=None):
    """Set a goal globally or for a specific platform."""
    if goal not in VALID_GOALS:
        raise ValueError(f"Invalid goal '{goal}'. Must be one of: {VALID_GOALS}")
    state = _load_state(state_path)
    if "goals" not in state:
        state["goals"] = {"default": "balanced", "platforms": {}}
    if platform:
        state["goals"]["platforms"][platform] = goal
    else:
        state["goals"]["default"] = goal
    _save_state(state_path, state)


def get_goal_for_platform(state_path, platform):
    """Get the effective goal for a platform (override or default)."""
    goals = get_goals(state_path)
    return goals["platforms"].get(platform, goals["default"])
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_intelligence.py::TestGoals -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add gtm/goals.py tests/test_intelligence.py
git commit -m "feat: add user-configurable goals (global + per-platform)"
```

---

## Task 4: Signal storage and topic cluster CRUD (`gtm/intelligence.py`)

Core intelligence module — functions to store signals, create/update/query topic clusters, and compute scores.

**Files:**
- Create: `gtm/intelligence.py`
- Test: `tests/test_intelligence.py` (extend)

**Step 1: Write the failing tests**

Add to `tests/test_intelligence.py`:

```python
from gtm.intelligence import (
    store_signal, store_signals,
    create_topic, get_topic, get_topics_by_status, update_topic_mentions,
    compute_trend_score, transition_statuses, expire_stale,
)


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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_intelligence.py::TestSignalStorage tests/test_intelligence.py::TestTopicClusters -v`
Expected: FAIL — module doesn't exist

**Step 3: Create `gtm/intelligence.py`**

```python
import json
from datetime import datetime, timedelta

from gtm.db import get_connection


# --- Signal Storage ---

def store_signal(db_path, signal, session_id=None):
    """Store a single content signal. Returns its ID."""
    conn = get_connection(db_path)
    cur = conn.execute(
        """INSERT INTO content_signals (platform, source_url, title, text_snippet, author, author_followers, engagement, session_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            signal.get("platform"),
            signal.get("source_url"),
            signal.get("title"),
            signal.get("text_snippet"),
            signal.get("author"),
            signal.get("author_followers", 0),
            signal.get("engagement", 0),
            session_id,
        ),
    )
    conn.commit()
    signal_id = cur.lastrowid
    conn.close()
    return signal_id


def store_signals(db_path, signals, session_id=None):
    """Store multiple signals. Returns list of IDs."""
    return [store_signal(db_path, s, session_id) for s in signals]


# --- Topic Cluster CRUD ---

def create_topic(db_path, data):
    """Create a new topic cluster. Returns its ID."""
    platforms = data.get("platforms_seen", [])
    conn = get_connection(db_path)
    cur = conn.execute(
        """INSERT INTO topic_clusters
           (name, description, key_phrases, platforms_seen, platform_count,
            total_mentions, relevance, authority_score, velocity, last_seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (
            data["name"],
            data.get("description"),
            json.dumps(data.get("key_phrases", [])),
            json.dumps(platforms),
            len(platforms),
            data.get("total_mentions", 0),
            data.get("relevance", "unknown"),
            data.get("authority_score", 0),
            data.get("velocity", 0),
        ),
    )
    conn.commit()
    topic_id = cur.lastrowid
    conn.close()
    return topic_id


def get_topic(db_path, topic_id):
    """Get a single topic by ID. Returns dict or None."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM topic_clusters WHERE id = ?", (topic_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def get_topics_by_status(db_path, status):
    """Get all topics with a given status, ordered by trend_score desc."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM topic_clusters WHERE status = ? ORDER BY trend_score DESC",
        (status,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_topics(db_path):
    """Get all non-expired topics ordered by opportunity_score."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM topic_clusters WHERE status != 'expired' ORDER BY opportunity_score DESC",
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_topic_mentions(db_path, topic_id, new_mentions, new_platforms=None):
    """Add new mentions to a topic and update platforms list."""
    conn = get_connection(db_path)
    topic = conn.execute("SELECT * FROM topic_clusters WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        conn.close()
        return

    current_mentions = topic["total_mentions"] or 0
    current_platforms = json.loads(topic["platforms_seen"] or "[]")

    if new_platforms:
        merged_platforms = list(set(current_platforms + new_platforms))
    else:
        merged_platforms = current_platforms

    conn.execute(
        """UPDATE topic_clusters
           SET total_mentions = ?, platforms_seen = ?, platform_count = ?, last_seen_at = datetime('now')
           WHERE id = ?""",
        (current_mentions + new_mentions, json.dumps(merged_platforms), len(merged_platforms), topic_id),
    )
    conn.commit()
    conn.close()


# --- Trend Scoring ---

def compute_trend_score(db_path, topic_id):
    """Compute and store trend_score for a topic."""
    conn = get_connection(db_path)
    topic = conn.execute("SELECT * FROM topic_clusters WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        conn.close()
        return

    frequency = min(topic["total_mentions"] or 0, 100) / 10  # normalize to 0-10
    velocity = min(max(topic["velocity"] or 0, -5), 5)       # clamp -5 to 5
    authority = min(topic["authority_score"] or 0, 50) / 5    # normalize to 0-10
    platform_div = min(topic["platform_count"] or 0, 6) / 0.6  # normalize to 0-10

    trend_score = (
        frequency * 0.3
        + velocity * 0.4
        + authority * 0.2
        + platform_div * 0.1
    )

    conn.execute("UPDATE topic_clusters SET trend_score = ? WHERE id = ?", (round(trend_score, 2), topic_id))
    conn.commit()
    conn.close()


def compute_opportunity_score(db_path, topic_id, goal="balanced"):
    """Compute and store opportunity_score for a topic."""
    conn = get_connection(db_path)
    topic = conn.execute("SELECT * FROM topic_clusters WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        conn.close()
        return

    trend = topic["trend_score"] or 0

    relevance_map = {"high": 3.0, "medium": 1.5, "low": 0.5, "none": -10, "unknown": 0}
    relevance = relevance_map.get(topic["relevance"], 0)

    engagement = min(topic["engagement_potential"] or 0, 10)
    saturation_penalty = (topic["saturation"] or 0) * 5

    goal_bonus = {
        "visibility": 2 if topic["status"] == "emerging" else 0,
        "conversions": 3 if topic["relevance"] == "high" else 0,
        "relationships": 2,  # always some bonus for relationship building
        "balanced": 1,
    }.get(goal, 1)

    score = trend + relevance + engagement + goal_bonus - saturation_penalty
    conn.execute("UPDATE topic_clusters SET opportunity_score = ? WHERE id = ?", (round(score, 2), topic_id))
    conn.commit()
    conn.close()


# --- Lifecycle ---

def transition_statuses(db_path):
    """Transition topics between status levels based on mentions and velocity."""
    conn = get_connection(db_path)
    # weak → emerging (8+ mentions AND velocity > 0)
    conn.execute(
        """UPDATE topic_clusters SET status = 'emerging'
           WHERE status = 'weak' AND total_mentions >= 8 AND velocity > 0"""
    )
    # emerging → confirmed (20+ mentions)
    conn.execute(
        """UPDATE topic_clusters SET status = 'confirmed'
           WHERE status = 'emerging' AND total_mentions >= 20"""
    )
    # any → cooling (velocity negative, not already cooling/expired)
    conn.execute(
        """UPDATE topic_clusters SET status = 'cooling'
           WHERE status NOT IN ('cooling', 'expired', 'proven') AND velocity < -1"""
    )
    conn.commit()
    conn.close()


def expire_stale(db_path):
    """Expire topics not seen recently."""
    conn = get_connection(db_path)
    now = datetime.utcnow()
    # Weak topics: expire after 3 days without being seen
    cutoff_weak = (now - timedelta(days=3)).isoformat()
    conn.execute(
        """UPDATE topic_clusters SET status = 'expired'
           WHERE status IN ('weak', 'cooling') AND last_seen_at < ?""",
        (cutoff_weak,),
    )
    # Other topics: expire after 5 days without being seen
    cutoff_other = (now - timedelta(days=5)).isoformat()
    conn.execute(
        """UPDATE topic_clusters SET status = 'expired'
           WHERE status NOT IN ('expired', 'proven') AND last_seen_at < ?""",
        (cutoff_other,),
    )
    conn.commit()
    conn.close()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_intelligence.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add gtm/intelligence.py tests/test_intelligence.py
git commit -m "feat: add intelligence module — signals, topics, trend scoring, lifecycle"
```

---

## Task 5: Briefing system (`gtm/intelligence.py` extension)

The pre-session briefing that reads all tables and returns structured context.

**Files:**
- Modify: `gtm/intelligence.py`
- Test: `tests/test_intelligence.py` (extend)

**Step 1: Write the failing tests**

Add to `tests/test_intelligence.py`:

```python
from gtm.intelligence import get_briefing, get_weak_signals, get_content_opportunities
from gtm.goals import set_goal
from gtm.niche import set_niche_field


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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_intelligence.py::TestBriefing -v`
Expected: FAIL — functions not defined

**Step 3: Add briefing functions to `gtm/intelligence.py`**

Append to the end of `gtm/intelligence.py`:

```python
from gtm.niche import get_niche, is_excluded_topic
from gtm.goals import get_goals, get_goal_for_platform


def get_weak_signals(db_path):
    """Get weak topics with strong structural signals (multi-platform, rising, authoritative)."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM topic_clusters
           WHERE status = 'weak'
             AND platform_count >= 2
             AND velocity > 0
             AND authority_score >= 3
           ORDER BY velocity DESC
           LIMIT 10""",
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_content_opportunities(db_path, goal="balanced", limit=5):
    """Get top content opportunities sorted by opportunity_score."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM topic_clusters
           WHERE status != 'expired' AND relevance IN ('high', 'medium')
           ORDER BY opportunity_score DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_briefing(db_path, state_path, platforms=None):
    """Build a full pre-session briefing from all tables."""
    from gtm.db import get_connection as gc
    from gtm.state import PLATFORMS as ALL_PLATFORMS

    target_platforms = platforms or ALL_PLATFORMS
    goals = get_goals(state_path)
    niche = get_niche(db_path)
    goal = goals["default"]

    # Active topics
    topics = get_active_topics(db_path)

    # Weak signals
    weak = get_weak_signals(db_path)

    # Opportunities (score with current goal)
    for t in topics:
        compute_opportunity_score(db_path, t["id"], goal)
    opportunities = get_content_opportunities(db_path, goal)

    # Promo safety per platform
    conn = gc(db_path)
    promo_status = {}
    three_days_ago = (datetime.utcnow() - timedelta(days=3)).isoformat()
    for p in target_platforms:
        row = conn.execute(
            """SELECT COUNT(*) as total,
                      COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
               FROM actions WHERE platform = ? AND created_at > ?""",
            (p, three_days_ago),
        ).fetchone()
        if row["total"] > 0:
            ratio = row["promos"] / row["total"]
            promo_status[p] = "blocked" if ratio > 0.08 else "safe"
        else:
            promo_status[p] = "safe"

    # Pending replies
    pending = conn.execute(
        "SELECT * FROM reply_tracking WHERE status = 'active' ORDER BY next_check_at LIMIT 10"
    ).fetchall()

    # High-value relationships
    relationships = {}
    for p in target_platforms:
        users = conn.execute(
            """SELECT username, interaction_count, relationship_score
               FROM relationships WHERE platform = ? AND interaction_count >= 2
               ORDER BY relationship_score DESC LIMIT 5""",
            (p,),
        ).fetchall()
        if users:
            relationships[p] = [dict(u) for u in users]

    conn.close()

    return {
        "goal": goal,
        "goals_by_platform": goals["platforms"],
        "niche": niche,
        "topics": [dict(t) for t in topics[:20]],
        "weak_signals": [dict(s) for s in weak],
        "opportunities": [dict(o) for o in opportunities],
        "promo_status": promo_status,
        "pending_replies": [dict(r) for r in pending],
        "relationships": relationships,
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_intelligence.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add gtm/intelligence.py tests/test_intelligence.py
git commit -m "feat: add briefing system — weak signals, opportunities, full pre-session context"
```

---

## Task 6: CLI commands — niche, goal, briefing, trends, signals

Wire everything into the CLI.

**Files:**
- Modify: `gtm/cli.py`

**Step 1: Add `cmd_niche` to `gtm/cli.py`**

```python
def cmd_niche(args):
    from gtm.niche import get_niche, set_niche_field, add_product

    if args.action == "set-industries":
        set_niche_field(DB_PATH, "industries", args.values)
        print(f"Industries set: {args.values}")
    elif args.action == "set-audiences":
        set_niche_field(DB_PATH, "audiences", args.values)
        print(f"Audiences set: {args.values}")
    elif args.action == "exclude":
        set_niche_field(DB_PATH, "exclude", args.values)
        print(f"Excluded: {args.values}")
    elif args.action == "add-product":
        if len(args.values) < 2:
            print("Usage: gtm niche add-product <url> <description>")
            return
        add_product(DB_PATH, args.values[0], " ".join(args.values[1:]))
        print(f"Product added: {args.values[0]}")
    else:
        niche = get_niche(DB_PATH)
        print("=== Niche Profile ===")
        print(f"  Industries:  {', '.join(niche['industries']) or '(not set)'}")
        print(f"  Audiences:   {', '.join(niche['audiences']) or '(not set)'}")
        print(f"  Exclude:     {', '.join(niche['exclude']) or '(not set)'}")
        if niche["products"]:
            print(f"  Products:")
            for p in niche["products"]:
                print(f"    {p['url']} — {p['desc']}")
        else:
            print(f"  Products:    (none)")
```

**Step 2: Add `cmd_goal` to `gtm/cli.py`**

```python
def cmd_goal(args):
    from gtm.goals import get_goals, set_goal, VALID_GOALS

    if args.action == "set":
        if not args.values:
            print(f"Usage: gtm goal set <{'|'.join(VALID_GOALS)}> [platform]")
            return
        goal = args.values[0]
        platform = args.values[1] if len(args.values) > 1 else None
        try:
            set_goal(STATE_PATH, goal, platform)
            if platform:
                print(f"Goal for {platform}: {goal}")
            else:
                print(f"Default goal: {goal}")
        except ValueError as e:
            print(f"Error: {e}")
    else:
        goals = get_goals(STATE_PATH)
        print("=== Goals ===")
        print(f"  Default: {goals['default']}")
        if goals["platforms"]:
            for p, g in goals["platforms"].items():
                print(f"  {p}: {g}")
        print(f"\nValid goals: {', '.join(VALID_GOALS)}")
```

**Step 3: Add `cmd_briefing`, `cmd_trends`, `cmd_signals` to `gtm/cli.py`**

```python
def cmd_briefing(args):
    import json
    from gtm.intelligence import get_briefing

    briefing = get_briefing(DB_PATH, STATE_PATH)
    print(f"=== Pre-Session Briefing (goal: {briefing['goal']}) ===\n")

    if briefing["niche"]["industries"]:
        print(f"Niche: {', '.join(briefing['niche']['industries'])}")
    print()

    if briefing["opportunities"]:
        print("Top Opportunities:")
        for t in briefing["opportunities"][:5]:
            phrases = json.loads(t["key_phrases"]) if t["key_phrases"] else []
            print(f"  [{t['status']}] {t['name']} (score: {t['opportunity_score']:.1f})")
            if phrases:
                print(f"    Search: {', '.join(phrases[:3])}")
        print()

    if briefing["weak_signals"]:
        print("Weak Signals (post early):")
        for s in briefing["weak_signals"][:5]:
            print(f"  {s['name']} — {s['total_mentions']} mentions, {s['platform_count']} platforms, velocity: {s['velocity']:.1f}")
        print()

    if briefing["promo_status"]:
        blocked = [p for p, s in briefing["promo_status"].items() if s == "blocked"]
        if blocked:
            print(f"Promo blocked on: {', '.join(blocked)}")
        else:
            print("Promo: safe on all platforms")
        print()

    if briefing["pending_replies"]:
        print(f"Pending replies: {len(briefing['pending_replies'])}")
        print()

    if briefing["relationships"]:
        print("High-value users:")
        for p, users in briefing["relationships"].items():
            names = [f"@{u['username']} ({u['interaction_count']}x)" for u in users[:3]]
            print(f"  {p}: {', '.join(names)}")


def cmd_trends(args):
    from gtm.intelligence import get_active_topics
    import json

    topics = get_active_topics(DB_PATH)
    if not topics:
        print("No active topics. Run a discovery scan first.")
        return

    print("=== Active Trends ===\n")
    header = f"  {'Topic':<30} {'Status':<12} {'Mentions':>8} {'Plat':>4} {'Vel':>6} {'Trend':>6} {'Opp':>6}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for t in topics[:20]:
        print(f"  {t['name'][:30]:<30} {t['status']:<12} {t['total_mentions']:>8} {t['platform_count']:>4} {(t['velocity'] or 0):>6.1f} {(t['trend_score'] or 0):>6.1f} {(t['opportunity_score'] or 0):>6.1f}")


def cmd_signals(args):
    from gtm.intelligence import get_weak_signals

    signals = get_weak_signals(DB_PATH)
    if not signals:
        print("No weak signals detected. Run a discovery scan to collect data.")
        return

    print("=== Weak Signals (Early Trends) ===\n")
    for s in signals:
        platforms = json.loads(s["platforms_seen"]) if s["platforms_seen"] else []
        print(f"  {s['name']}")
        print(f"    Mentions: {s['total_mentions']} | Platforms: {', '.join(platforms)} | Velocity: {s['velocity']:.1f}")
        print(f"    Authority: {s['authority_score']:.0f} | Relevance: {s['relevance']}")
        print()
```

**Step 4: Register all new subcommands in `main()`**

Add to the parser section in `main()`:

```python
niche_parser = sub.add_parser("niche", help="Manage niche profile")
niche_parser.add_argument("action", nargs="?", default=None,
                          choices=["set-industries", "set-audiences", "exclude", "add-product"])
niche_parser.add_argument("values", nargs="*", default=[])

goal_parser = sub.add_parser("goal", help="Manage session goals")
goal_parser.add_argument("action", nargs="?", default=None, choices=["set"])
goal_parser.add_argument("values", nargs="*", default=[])

sub.add_parser("briefing", help="Show pre-session briefing")
sub.add_parser("trends", help="Show active trends")
sub.add_parser("signals", help="Show weak signals")
```

Add to the `commands` dict:

```python
"niche": cmd_niche, "goal": cmd_goal,
"briefing": cmd_briefing, "trends": cmd_trends, "signals": cmd_signals,
```

**Step 5: Test manually**

```bash
python3 -m gtm niche set-industries ai saas developer-tools productivity
python3 -m gtm niche set-audiences developers indie-hackers founders
python3 -m gtm niche exclude politics crypto celebrity sports gaming
python3 -m gtm niche add-product site.com "description"
python3 -m gtm niche add-product site2.com "description"
python3 -m gtm niche
python3 -m gtm goal set balanced
python3 -m gtm goal set twitter visibility
python3 -m gtm goal
python3 -m gtm briefing
python3 -m gtm trends
python3 -m gtm signals
```

**Step 6: Commit**

```bash
git add gtm/cli.py
git commit -m "feat: add CLI commands — niche, goal, briefing, trends, signals"
```

---

## Task 7: Signal collectors — platform-specific fetch functions

Functions that call WebFetch/WebSearch APIs and return structured signals. These are called by the AI agent (not by cron) — the AI invokes them at session start.

**Files:**
- Create: `gtm/collectors.py`
- Test: `tests/test_intelligence.py` (extend)

**Step 1: Write the failing tests**

Add to `tests/test_intelligence.py`:

```python
from gtm.collectors import (
    parse_reddit_response, parse_hn_stories, parse_devto_response,
    build_search_queries,
)


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
        set_niche_field(self.db_path, "industries", ["ai", "saas", "developer-tools"])
        queries = build_search_queries(self.db_path)
        self.assertGreater(len(queries), 0)
        # Should include industry-specific terms
        combined = " ".join(queries)
        self.assertTrue("ai" in combined.lower() or "saas" in combined.lower())
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_intelligence.py::TestCollectors -v`
Expected: FAIL — module doesn't exist

**Step 3: Create `gtm/collectors.py`**

```python
"""Signal collectors — parse platform API responses into structured signals.

These parsers convert raw JSON from Reddit, HN, Dev.to APIs into the standard
signal format for storage in content_signals table. The actual API calls are
made by the AI agent using WebFetch/WebSearch tools — these functions just
parse the responses.
"""

from gtm.niche import get_niche


def parse_reddit_response(data, platform="reddit"):
    """Parse Reddit JSON API response into signals."""
    signals = []
    children = data.get("data", {}).get("children", [])
    for child in children:
        post = child.get("data", {})
        signals.append({
            "platform": platform,
            "title": post.get("title", ""),
            "text_snippet": (post.get("selftext", "") or "")[:500],
            "author": post.get("author", ""),
            "engagement": post.get("score", 0),
            "source_url": "https://reddit.com" + post.get("permalink", ""),
        })
    return signals


def parse_hn_stories(stories):
    """Parse Hacker News story objects into signals."""
    signals = []
    for story in stories:
        signals.append({
            "platform": "hackernews",
            "title": story.get("title", ""),
            "text_snippet": story.get("title", ""),
            "author": story.get("by", ""),
            "engagement": story.get("score", 0),
            "source_url": story.get("url") or f"https://news.ycombinator.com/item?id={story.get('id', '')}",
            "author_followers": 0,
        })
    return signals


def parse_devto_response(articles):
    """Parse Dev.to API response into signals."""
    signals = []
    for article in articles:
        user = article.get("user", {})
        tags = article.get("tag_list", [])
        signals.append({
            "platform": "devto",
            "title": article.get("title", ""),
            "text_snippet": (article.get("description", "") or "")[:500],
            "author": user.get("username", ""),
            "engagement": article.get("positive_reactions_count", 0),
            "source_url": article.get("url", ""),
        })
    return signals


def parse_github_trending(html_text):
    """Extract basic repo info from GitHub trending page HTML.

    This is a simple parser — GitHub trending doesn't have a JSON API.
    Returns signals with repo name as title and URL.
    """
    signals = []
    # Simple line-by-line extraction of repo links
    # GitHub trending repos appear as /<owner>/<repo> links
    lines = html_text.split("\n")
    for line in lines:
        if '/trending"' in line or 'class="h3' in line:
            continue
        if 'href="/' in line and '" class=' in line:
            # Try to extract repo path
            start = line.find('href="/') + 7
            end = line.find('"', start)
            if start > 7 and end > start:
                repo_path = line[start:end]
                if "/" in repo_path and not repo_path.startswith("trending"):
                    signals.append({
                        "platform": "github",
                        "title": repo_path,
                        "text_snippet": "",
                        "author": repo_path.split("/")[0] if "/" in repo_path else "",
                        "engagement": 0,
                        "source_url": f"https://github.com/{repo_path}",
                        "author_followers": 5,  # GitHub trending = authority signal
                    })
    return signals


def build_search_queries(db_path):
    """Build WebSearch queries based on niche profile."""
    niche = get_niche(db_path)
    industries = niche.get("industries", [])
    audiences = niche.get("audiences", [])

    queries = []

    # Industry-based queries
    if industries:
        terms = " OR ".join(f'"{ind}"' for ind in industries[:3])
        queries.append(f"site:x.com ({terms}) developer tools trending today")
        queries.append(f"({terms}) new tools launches this week")

    # Audience-based queries
    if audiences:
        for aud in audiences[:2]:
            queries.append(f'"{aud}" what are people talking about this week')

    # Fallback
    if not queries:
        queries.append("developer tools trending this week")
        queries.append("saas tools new launch 2026")

    return queries


# Subreddit suggestions based on niche
NICHE_SUBREDDITS = {
    "ai": ["artificial", "MachineLearning", "LocalLLaMA", "ChatGPT"],
    "saas": ["SaaS", "microsaas", "EntrepreneurRideAlong"],
    "developer-tools": ["webdev", "programming", "devtools", "selfhosted"],
    "productivity": ["productivity", "Notion", "ObsidianMD"],
    "devops": ["devops", "kubernetes", "docker"],
    "open-source": ["opensource", "github", "linux"],
    "startups": ["startups", "Entrepreneur", "smallbusiness"],
}


def get_niche_subreddits(db_path, max_subs=8):
    """Return list of subreddits matching the niche profile."""
    niche = get_niche(db_path)
    industries = niche.get("industries", [])
    subs = set()
    for ind in industries:
        subs.update(NICHE_SUBREDDITS.get(ind, []))
    # Always include these general dev/startup subs
    subs.update(["webdev", "SaaS", "indiehackers", "startups"])
    return list(subs)[:max_subs]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_intelligence.py::TestCollectors -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add gtm/collectors.py tests/test_intelligence.py
git commit -m "feat: add signal collectors — Reddit, HN, Dev.to, GitHub parsers + search query builder"
```

---

## Task 8: Feedback learning — post-session updates

Update topic scores based on engagement outcomes after sessions.

**Files:**
- Modify: `gtm/intelligence.py`
- Modify: `gtm/runner.py` (call feedback on finish)
- Test: `tests/test_intelligence.py` (extend)

**Step 1: Write the failing test**

Add to `tests/test_intelligence.py`:

```python
from gtm.intelligence import update_feedback


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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_intelligence.py::TestFeedback -v`
Expected: FAIL — function not defined

**Step 3: Add `update_feedback` to `gtm/intelligence.py`**

```python
def update_feedback(db_path):
    """Post-session learning: promote topics with good engagement to 'proven'."""
    conn = get_connection(db_path)
    # Topics we've posted about with good engagement → proven
    conn.execute(
        """UPDATE topic_clusters SET status = 'proven'
           WHERE status IN ('emerging', 'confirmed')
             AND times_we_posted > 0
             AND avg_engagement > 5.0"""
    )
    conn.commit()
    conn.close()


def record_topic_engagement(db_path, topic_id, engagement_score):
    """Record that we posted about a topic and how it performed."""
    conn = get_connection(db_path)
    topic = conn.execute("SELECT * FROM topic_clusters WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        conn.close()
        return
    posted = (topic["times_we_posted"] or 0) + 1
    prev_avg = topic["avg_engagement"] or 0
    new_avg = ((prev_avg * (posted - 1)) + engagement_score) / posted
    conn.execute(
        "UPDATE topic_clusters SET times_we_posted = ?, avg_engagement = ? WHERE id = ?",
        (posted, round(new_avg, 2), topic_id),
    )
    conn.commit()
    conn.close()
```

**Step 4: Add feedback call to `InterleavedRunner.finish()` in `gtm/runner.py`**

Add at the end of the `finish()` method, before `save_state`:

```python
from gtm.intelligence import update_feedback, transition_statuses, expire_stale
transition_statuses(self.db_path)
expire_stale(self.db_path)
update_feedback(self.db_path)
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_intelligence.py::TestFeedback -v`
Expected: PASS

Run: `pytest tests/test_runner.py -q`
Expected: All runner tests still pass

**Step 6: Commit**

```bash
git add gtm/intelligence.py gtm/runner.py tests/test_intelligence.py
git commit -m "feat: add feedback learning — post-session topic scoring + proven status"
```

---

## Task 9: Integration — runner loads briefing at session start

Connect the intelligence engine to the runner so briefings are loaded automatically.

**Files:**
- Modify: `gtm/runner.py`

**Step 1: Update `InterleavedRunner.__init__` to accept a goal**

In `gtm/runner.py`, update the constructor:

```python
def __init__(self, db_path, state_path, goal=None):
    # ... existing init code ...
    # Load goal
    if goal:
        self.goal = goal
    else:
        from gtm.goals import get_goals
        goals = get_goals(self.state_path)
        self.goal = goals["default"]
    self.briefing = None  # populated by load_briefing()
```

**Step 2: Add `load_briefing` method**

```python
def load_briefing(self):
    """Load pre-session intelligence briefing."""
    from gtm.intelligence import get_briefing
    self.briefing = get_briefing(self.db_path, self.state_path)
    return self.briefing
```

**Step 3: Add `discover_keyword` method for mid-session topic logging**

```python
def discover_topic(self, platform, topic_name, key_phrases=None, mentions=1):
    """Log a discovered topic during the session."""
    from gtm.intelligence import create_topic, get_active_topics
    # Check if topic already exists
    existing = get_active_topics(self.db_path)
    for t in existing:
        if t["name"].lower() == topic_name.lower():
            from gtm.intelligence import update_topic_mentions
            update_topic_mentions(self.db_path, t["id"], mentions, [platform])
            return t["id"]
    # Create new topic
    return create_topic(self.db_path, {
        "name": topic_name,
        "key_phrases": key_phrases or [],
        "platforms_seen": [platform],
        "total_mentions": mentions,
        "relevance": "unknown",
    })
```

**Step 4: Run full test suite**

Run: `pytest tests/ -q`
Expected: All tests pass (no breaking changes)

**Step 5: Commit**

```bash
git add gtm/runner.py
git commit -m "feat: integrate intelligence engine into runner — briefing, goal, topic discovery"
```

---

## Task 10: Update CLAUDE.md with new session flow

Document the new intelligence-powered session flow so future Claude sessions know how to use it.

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add new section to CLAUDE.md after "How to Run a Session"**

Add a section documenting:

1. New pre-flight: `python3 -m gtm niche` (verify niche is set)
2. New pre-flight: `python3 -m gtm goal` (verify goal is set)
3. Phase 1: Discovery scan using WebFetch/WebSearch (no Owl)
   - Fetch Reddit hot posts: `WebFetch https://www.reddit.com/r/{sub}/hot.json?limit=25`
   - Fetch HN top stories: `WebFetch https://hacker-news.firebaseio.com/v0/topstories.json`
   - Fetch Dev.to trending: `WebFetch https://dev.to/api/articles?top=1&per_page=30`
   - WebSearch for Twitter/X trends
   - Parse responses using `gtm.collectors` parsers
   - Store signals: `intelligence.store_signals(db_path, signals, session_id)`
4. Claude clusters signals into topics (semantic grouping)
5. Store topics: `intelligence.create_topic()` or `update_topic_mentions()`
6. Score trends: `intelligence.compute_trend_score()`
7. Score opportunities: `intelligence.compute_opportunity_score()`
8. Load briefing: `runner.load_briefing()`
9. Phase 2: Engagement (Owl) — use briefing to guide actions
10. Phase 3: Post-session — `runner.finish()` auto-runs feedback learning

Add new CLI commands reference:
```bash
python3 -m gtm niche           # show/manage niche profile
python3 -m gtm goal            # show/manage goals
python3 -m gtm briefing        # pre-session briefing
python3 -m gtm trends          # active trends
python3 -m gtm signals         # weak signals (early trends)
python3 -m gtm actions         # per-platform action types
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add intelligence engine session flow to CLAUDE.md"
```

---

## Summary

| Task | What it builds | New files |
|---|---|---|
| 1 | DB schema (3 new tables) | — |
| 2 | Niche profile CRUD | `gtm/niche.py` |
| 3 | Goal system | `gtm/goals.py` |
| 4 | Signal storage + topic clusters + scoring | `gtm/intelligence.py` |
| 5 | Briefing system | extends `gtm/intelligence.py` |
| 6 | CLI commands | extends `gtm/cli.py` |
| 7 | Signal collectors/parsers | `gtm/collectors.py` |
| 8 | Feedback learning | extends `gtm/intelligence.py` + `gtm/runner.py` |
| 9 | Runner integration | extends `gtm/runner.py` |
| 10 | Documentation | extends `CLAUDE.md` |

Total: 4 new files, 3 modified files, 10 commits.
