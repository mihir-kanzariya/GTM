# GTM v2 Scaling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Scale GTM from basic like/comment to a full engagement system with reply tracking, Twitter threads, smart keywords, engagement scoring, relationships, content calendar, peak times, and decision logging.

**Architecture:** Modular services — each feature in its own Python module, shared SQLite DB, InterleavedRunner orchestrates by delegating to modules. Cron-based reply checker runs every 15min during sessions.

**Tech Stack:** Python 3, SQLite (WAL mode), unittest, CronCreate/CronDelete for scheduling.

**Design doc:** `docs/plans/2026-03-09-gtm-v2-scaling-design.md`

---

### Task 1: Extend DB Schema — New Tables

**Files:**
- Modify: `gtm/db.py` (add new tables to `init_db`)
- Modify: `tests/test_db.py` (verify all tables created)

**Step 1: Write the failing test**

In `tests/test_db.py`, update `test_creates_all_tables` to expect all new tables:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_db.py::TestInitDb::test_creates_all_tables -v`
Expected: FAIL — new tables don't exist yet.

**Step 3: Write minimal implementation**

In `gtm/db.py`, add the following tables inside the `init_db` function's `executescript`, after the `daily_metrics` table and before the CREATE INDEX statements:

```sql
CREATE TABLE IF NOT EXISTS reply_tracking (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id       INTEGER REFERENCES actions(id) UNIQUE,
    platform        TEXT NOT NULL,
    target_url      TEXT,
    comment_url     TEXT,
    status          TEXT DEFAULT 'active',
    checks_done     INTEGER DEFAULT 0,
    max_checks      INTEGER DEFAULT 3,
    check_interval_min INTEGER DEFAULT 15,
    next_check_at   DATETIME,
    last_checked_at DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS threads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT DEFAULT 'twitter',
    thread_type     TEXT,
    topic           TEXT,
    tweet_count     INTEGER,
    first_tweet_url TEXT,
    content         TEXT,
    posted_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_id      TEXT REFERENCES sessions(id),
    engagement      TEXT
);

CREATE TABLE IF NOT EXISTS keyword_performance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         TEXT NOT NULL,
    platform        TEXT NOT NULL,
    times_used      INTEGER DEFAULT 0,
    posts_found     INTEGER DEFAULT 0,
    comments_made   INTEGER DEFAULT 0,
    replies_received INTEGER DEFAULT 0,
    avg_upvotes     REAL DEFAULT 0,
    last_used_at    DATETIME,
    score           REAL DEFAULT 0,
    UNIQUE(keyword, platform)
);

CREATE TABLE IF NOT EXISTS relationships (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,
    username        TEXT NOT NULL,
    display_name    TEXT,
    first_seen_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_interacted DATETIME,
    interaction_count INTEGER DEFAULT 1,
    interactions    TEXT,
    notes           TEXT,
    relationship_score REAL DEFAULT 0,
    UNIQUE(platform, username)
);

CREATE TABLE IF NOT EXISTS content_calendar (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,
    content_type    TEXT NOT NULL,
    topic           TEXT,
    outline         TEXT,
    scheduled_for   DATE,
    status          TEXT DEFAULT 'planned',
    action_id       INTEGER REFERENCES actions(id),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS peak_times (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,
    day_of_week     INTEGER NOT NULL,
    hour            INTEGER NOT NULL,
    actions_taken   INTEGER DEFAULT 0,
    avg_replies     REAL DEFAULT 0,
    avg_upvotes     REAL DEFAULT 0,
    engagement_score REAL DEFAULT 0,
    sample_count    INTEGER DEFAULT 0,
    UNIQUE(platform, day_of_week, hour)
);

CREATE TABLE IF NOT EXISTS decision_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
    category        TEXT NOT NULL,
    platform        TEXT,
    decision        TEXT NOT NULL,
    reasoning       TEXT,
    context         TEXT,
    session_id      TEXT REFERENCES sessions(id),
    outcome         TEXT
);
```

Also modify the existing `outcomes` table to add new columns:

```sql
CREATE TABLE IF NOT EXISTS outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id       INTEGER NOT NULL REFERENCES actions(id),
    check_number    INTEGER,
    checked_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    upvotes         INTEGER DEFAULT 0,
    replies         INTEGER DEFAULT 0,
    reply_content   TEXT,
    reply_author    TEXT,
    views           INTEGER,
    our_reply_id    INTEGER REFERENCES actions(id)
);
```

Add new indexes after existing ones:

```sql
CREATE INDEX IF NOT EXISTS idx_reply_tracking_status ON reply_tracking(status, next_check_at);
CREATE INDEX IF NOT EXISTS idx_keyword_platform ON keyword_performance(platform, score);
CREATE INDEX IF NOT EXISTS idx_relationships_platform ON relationships(platform, username);
CREATE INDEX IF NOT EXISTS idx_decision_log_category ON decision_log(category, timestamp);
CREATE INDEX IF NOT EXISTS idx_threads_posted ON threads(posted_at);
CREATE INDEX IF NOT EXISTS idx_content_calendar_date ON content_calendar(scheduled_for, status);
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_db.py -v`
Expected: ALL PASS

**Step 5: Run all existing tests to check nothing broke**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/ -v`
Expected: ALL PASS (the outcomes table change is backwards-compatible since new columns have defaults)

**Step 6: Commit**

```bash
git add gtm/db.py tests/test_db.py
git commit -m "feat: add v2 schema — reply_tracking, threads, keywords, relationships, calendar, peak_times, decision_log"
```

---

### Task 2: Decision Logging Module

**Files:**
- Create: `gtm/decisions.py`
- Create: `tests/test_decisions.py`

**Step 1: Write the failing tests**

Create `tests/test_decisions.py`:

```python
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
        did = log_decision(
            self.db_path,
            category="keyword",
            decision="Used 'bug reporting tool' on reddit",
            reasoning="Score 8.2, top performer",
            platform="reddit",
        )
        self.assertIsNotNone(did)
        self.assertIsInstance(did, int)

    def test_log_decision_with_context(self):
        did = log_decision(
            self.db_path,
            category="promotion",
            decision="Promoted acme-product",
            reasoning="Ratio at 6%, post about bug tracking",
            context='{"action_id": 42, "ratio": 0.06}',
            platform="reddit",
        )
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM decision_log WHERE id = ?", (did,)).fetchone()
        conn.close()
        self.assertEqual(row["category"], "promotion")
        self.assertIn("42", row["context"])

    def test_log_decision_with_session(self):
        sid = create_session(self.db_path, "twitter")
        did = log_decision(
            self.db_path,
            category="engagement",
            decision="Enrolled comment for tracking",
            reasoning="Standard enrollment",
            session_id=sid,
        )
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
        # Most recent first
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
        log_decision(self.db_path, "keyword", "D3", "r")  # no session
        results = get_session_decisions(self.db_path, sid)
        self.assertEqual(len(results), 2)

    def test_get_decision_summary(self):
        sid = create_session(self.db_path, "reddit")
        log_action(self.db_path, sid, "reddit", "like", "https://reddit.com/1")
        log_action(self.db_path, sid, "reddit", "comment", "https://reddit.com/2",
                   content="test comment")
        log_decision(self.db_path, "keyword", "Used 'saas tools'", "top scorer",
                     platform="reddit", session_id=sid)
        summary = get_decision_summary(self.db_path, days=7)
        self.assertIn("total_actions", summary)
        self.assertIn("recent_decisions", summary)
        self.assertIsInstance(summary["recent_decisions"], list)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_decisions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gtm.decisions'`

**Step 3: Write minimal implementation**

Create `gtm/decisions.py`:

```python
import json
from datetime import datetime, timedelta

from gtm.db import get_connection


def log_decision(db_path, category, decision, reasoning, context=None,
                 platform=None, session_id=None):
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO decision_log
               (category, platform, decision, reasoning, context, session_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (category, platform, decision, reasoning, context, session_id),
        )
        did = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return did


def get_recent_decisions(db_path, category=None, platform=None, limit=20):
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM decision_log WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if platform:
            query += " AND platform = ?"
            params.append(platform)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_session_decisions(db_path, session_id):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM decision_log WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_decision_summary(db_path, days=7):
    conn = get_connection(db_path)
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    try:
        # Total actions
        row = conn.execute(
            "SELECT COUNT(*) as total FROM actions WHERE created_at > ?",
            (cutoff,),
        ).fetchone()
        total_actions = row["total"]

        # Comments
        row = conn.execute(
            """SELECT COUNT(*) as total FROM actions
               WHERE created_at > ? AND action_type IN ('comment', 'reply', 'like_and_comment')""",
            (cutoff,),
        ).fetchone()
        total_comments = row["total"]

        # Promotions
        row = conn.execute(
            """SELECT COUNT(*) as total FROM actions
               WHERE created_at > ? AND promoted_product IS NOT NULL""",
            (cutoff,),
        ).fetchone()
        total_promotions = row["total"]

        # Active reply trackers
        trackers = conn.execute(
            "SELECT platform, COUNT(*) as cnt FROM reply_tracking WHERE status = 'active' GROUP BY platform"
        ).fetchall()
        active_trackers = {r["platform"]: r["cnt"] for r in trackers}

        # Promo ratios per platform
        from gtm.state import PLATFORMS
        promo_ratios = {}
        for p in PLATFORMS:
            r = conn.execute(
                """SELECT COUNT(*) as total,
                          COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
                   FROM actions WHERE platform = ? AND created_at > ?""",
                (p, cutoff),
            ).fetchone()
            promo_ratios[p] = round(r["promos"] / r["total"], 3) if r["total"] > 0 else 0.0

        # Top keywords per platform
        top_keywords = {}
        for p in PLATFORMS:
            kws = conn.execute(
                "SELECT keyword, score FROM keyword_performance WHERE platform = ? ORDER BY score DESC LIMIT 5",
                (p,),
            ).fetchall()
            top_keywords[p] = [(r["keyword"], r["score"]) for r in kws]

        # High-value relationships
        high_value = conn.execute(
            "SELECT platform, username, interaction_count FROM relationships WHERE interaction_count >= 3 ORDER BY interaction_count DESC LIMIT 10"
        ).fetchall()

        # Today's calendar
        today = datetime.utcnow().strftime("%Y-%m-%d")
        calendar_today = conn.execute(
            "SELECT platform, content_type, topic FROM content_calendar WHERE scheduled_for = ? AND status = 'planned'",
            (today,),
        ).fetchall()

        # Recent decisions
        recent = conn.execute(
            "SELECT category, platform, decision, reasoning FROM decision_log ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()

    finally:
        conn.close()

    return {
        "total_actions": total_actions,
        "total_comments": total_comments,
        "total_promotions": total_promotions,
        "active_trackers": active_trackers,
        "promo_ratios": promo_ratios,
        "top_keywords": top_keywords,
        "high_value_relationships": [dict(r) for r in high_value],
        "calendar_today": [dict(r) for r in calendar_today],
        "recent_decisions": [dict(r) for r in recent],
    }
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_decisions.py -v`
Expected: ALL PASS

**Step 5: Run all tests**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add gtm/decisions.py tests/test_decisions.py
git commit -m "feat: add decisions module — log, query, and summarize all GTM decisions"
```

---

### Task 3: Engagement Module — Reply Tracking

**Files:**
- Create: `gtm/engagement.py`
- Create: `tests/test_engagement.py`

**Step 1: Write the failing tests**

Create `tests/test_engagement.py`:

```python
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from gtm.db import init_db, get_connection, create_session, log_action
from gtm.engagement import (
    enroll_for_tracking,
    get_due_checks,
    record_check,
    should_reply,
    mark_replied,
    mark_exhausted,
    get_active_tracking_count,
)


class TestEngagement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)
        self.sid = create_session(self.db_path, "reddit")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_enroll_for_tracking(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/r/saas/post1", content="great post")
        tid = enroll_for_tracking(self.db_path, aid, "reddit",
                                  "https://reddit.com/r/saas/post1",
                                  "https://reddit.com/r/saas/post1#comment123")
        self.assertIsNotNone(tid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["checks_done"], 0)
        self.assertEqual(row["max_checks"], 3)
        self.assertIsNotNone(row["next_check_at"])

    def test_enroll_sets_next_check_15min(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        next_check = datetime.fromisoformat(row["next_check_at"])
        now = datetime.utcnow()
        diff = (next_check - now).total_seconds()
        self.assertGreater(diff, 800)   # ~14 min
        self.assertLess(diff, 1000)     # ~16 min

    def test_enroll_duplicate_action_ignored(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid1 = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        tid2 = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        self.assertEqual(tid1, tid2)

    def test_get_due_checks_returns_due_entries(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        # Force next_check_at to past
        conn = get_connection(self.db_path)
        conn.execute("UPDATE reply_tracking SET next_check_at = datetime('now', '-1 minute')")
        conn.commit()
        conn.close()
        due = get_due_checks(self.db_path)
        self.assertEqual(len(due), 1)

    def test_get_due_checks_skips_future(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        # next_check_at is 15min in future by default
        due = get_due_checks(self.db_path)
        self.assertEqual(len(due), 0)

    def test_get_due_checks_skips_exhausted(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        mark_exhausted(self.db_path, tid)
        conn = get_connection(self.db_path)
        conn.execute("UPDATE reply_tracking SET next_check_at = datetime('now', '-1 minute')")
        conn.commit()
        conn.close()
        due = get_due_checks(self.db_path)
        self.assertEqual(len(due), 0)

    def test_record_check_increments_count(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        record_check(self.db_path, tid, upvotes=5, replies=1,
                     reply_content="nice!", reply_author="devguy")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["checks_done"], 1)
        self.assertIsNotNone(row["last_checked_at"])

    def test_record_check_creates_outcome(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        record_check(self.db_path, tid, upvotes=5, replies=1,
                     reply_content="nice!", reply_author="devguy")
        conn = get_connection(self.db_path)
        outcome = conn.execute("SELECT * FROM outcomes WHERE action_id = ?", (aid,)).fetchone()
        conn.close()
        self.assertEqual(outcome["upvotes"], 5)
        self.assertEqual(outcome["replies"], 1)
        self.assertEqual(outcome["reply_content"], "nice!")
        self.assertEqual(outcome["check_number"], 1)

    def test_record_check_updates_next_check(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        record_check(self.db_path, tid, upvotes=0, replies=0)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        next_check = datetime.fromisoformat(row["next_check_at"])
        now = datetime.utcnow()
        diff = (next_check - now).total_seconds()
        self.assertGreater(diff, 800)
        self.assertLess(diff, 1000)

    def test_record_check_auto_exhausts_at_max(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        record_check(self.db_path, tid, upvotes=0, replies=0)
        record_check(self.db_path, tid, upvotes=0, replies=0)
        record_check(self.db_path, tid, upvotes=0, replies=0)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "exhausted")
        self.assertEqual(row["checks_done"], 3)

    def test_should_reply_returns_bool(self):
        result = should_reply("Great point!")
        self.assertIsInstance(result, bool)

    def test_should_reply_probability(self):
        true_count = sum(1 for _ in range(1000) if should_reply("test"))
        # Should be around 700 (70%) with some variance
        self.assertGreater(true_count, 600)
        self.assertLess(true_count, 800)

    def test_mark_replied(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        reply_aid = log_action(self.db_path, self.sid, "reddit", "comment",
                               "https://reddit.com/1", content="thanks for the reply!")
        mark_replied(self.db_path, tid, reply_aid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "replied")

    def test_mark_exhausted(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        mark_exhausted(self.db_path, tid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "exhausted")

    def test_get_active_tracking_count(self):
        for i in range(3):
            aid = log_action(self.db_path, self.sid, "reddit", "comment",
                             f"https://reddit.com/{i}", content="test")
            enroll_for_tracking(self.db_path, aid, "reddit", f"https://reddit.com/{i}")
        count = get_active_tracking_count(self.db_path)
        self.assertEqual(count, 3)

    def test_get_active_tracking_count_excludes_exhausted(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        tid = enroll_for_tracking(self.db_path, aid, "reddit", "https://reddit.com/1")
        mark_exhausted(self.db_path, tid)
        count = get_active_tracking_count(self.db_path)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_engagement.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gtm.engagement'`

**Step 3: Write minimal implementation**

Create `gtm/engagement.py`:

```python
import random
from datetime import datetime, timedelta

from gtm.db import get_connection

REPLY_PROBABILITY = 0.7


def enroll_for_tracking(db_path, action_id, platform, target_url, comment_url=None):
    next_check = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
    conn = get_connection(db_path)
    try:
        # Check if already enrolled
        existing = conn.execute(
            "SELECT id FROM reply_tracking WHERE action_id = ?", (action_id,)
        ).fetchone()
        if existing:
            return existing["id"]
        cursor = conn.execute(
            """INSERT INTO reply_tracking
               (action_id, platform, target_url, comment_url, next_check_at)
               VALUES (?, ?, ?, ?, ?)""",
            (action_id, platform, target_url, comment_url, next_check),
        )
        tid = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return tid


def get_due_checks(db_path):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM reply_tracking
               WHERE status = 'active'
               AND next_check_at <= datetime('now')
               AND checks_done < max_checks
               ORDER BY next_check_at"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def record_check(db_path, tracking_id, upvotes=0, replies=0,
                 reply_content=None, reply_author=None):
    now = datetime.utcnow().isoformat()
    next_check = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM reply_tracking WHERE id = ?", (tracking_id,)
        ).fetchone()
        new_checks = row["checks_done"] + 1
        check_number = new_checks

        # Insert outcome
        conn.execute(
            """INSERT INTO outcomes
               (action_id, check_number, upvotes, replies, reply_content, reply_author)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (row["action_id"], check_number, upvotes, replies, reply_content, reply_author),
        )

        # Update tracking
        new_status = "exhausted" if new_checks >= row["max_checks"] else "active"
        conn.execute(
            """UPDATE reply_tracking
               SET checks_done = ?, last_checked_at = ?, next_check_at = ?, status = ?
               WHERE id = ?""",
            (new_checks, now, next_check, new_status, tracking_id),
        )
        conn.commit()
    finally:
        conn.close()


def should_reply(reply_content):
    return random.random() < REPLY_PROBABILITY


def mark_replied(db_path, tracking_id, reply_action_id):
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE reply_tracking SET status = 'replied' WHERE id = ?",
            (tracking_id,),
        )
        # Link the reply in the latest outcome
        conn.execute(
            """UPDATE outcomes SET our_reply_id = ?
               WHERE action_id = (SELECT action_id FROM reply_tracking WHERE id = ?)
               ORDER BY checked_at DESC LIMIT 1""",
            (reply_action_id, tracking_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_exhausted(db_path, tracking_id):
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE reply_tracking SET status = 'exhausted' WHERE id = ?",
            (tracking_id,),
        )
        conn.commit()
    finally:
        conn.close()


def get_active_tracking_count(db_path):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM reply_tracking WHERE status = 'active'"
        ).fetchone()
    finally:
        conn.close()
    return row["cnt"]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_engagement.py -v`
Expected: ALL PASS

**Step 5: Run all tests**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add gtm/engagement.py tests/test_engagement.py
git commit -m "feat: add engagement module — reply tracking with 15min checks, auto-follow-up"
```

---

### Task 4: Analytics Module — Keywords, Peak Times, Scoring

**Files:**
- Create: `gtm/analytics.py`
- Create: `tests/test_analytics.py`

**Step 1: Write the failing tests**

Create `tests/test_analytics.py`:

```python
import os
import tempfile
import unittest
from datetime import datetime

from gtm.db import init_db, get_connection
from gtm.analytics import (
    update_keyword_score,
    get_weighted_keywords,
    update_peak_times,
    get_best_hours,
    calculate_engagement_score,
    seed_keywords,
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
        update_keyword_score(self.db_path, "bug reporting tool", "reddit",
                             replies=2, upvotes=5)
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM keyword_performance WHERE keyword = ? AND platform = ?",
            ("bug reporting tool", "reddit"),
        ).fetchone()
        conn.close()
        self.assertEqual(row["times_used"], 1)
        self.assertEqual(row["replies_received"], 2)
        self.assertGreater(row["score"], 0)

    def test_update_keyword_score_accumulates(self):
        update_keyword_score(self.db_path, "saas tools", "twitter", replies=1, upvotes=3)
        update_keyword_score(self.db_path, "saas tools", "twitter", replies=2, upvotes=4)
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM keyword_performance WHERE keyword = ? AND platform = ?",
            ("saas tools", "twitter"),
        ).fetchone()
        conn.close()
        self.assertEqual(row["times_used"], 2)
        self.assertEqual(row["replies_received"], 3)

    def test_get_weighted_keywords_returns_list(self):
        update_keyword_score(self.db_path, "kw1", "reddit", replies=10, upvotes=20)
        update_keyword_score(self.db_path, "kw2", "reddit", replies=1, upvotes=2)
        update_keyword_score(self.db_path, "kw3", "reddit", replies=5, upvotes=10)
        result = get_weighted_keywords(self.db_path, "reddit", n=3)
        self.assertEqual(len(result), 3)
        # Result should be a list of (keyword, score) tuples
        self.assertIsInstance(result[0], tuple)
        self.assertEqual(len(result[0]), 2)

    def test_get_weighted_keywords_empty_platform(self):
        result = get_weighted_keywords(self.db_path, "twitter", n=5)
        self.assertEqual(len(result), 0)

    def test_seed_keywords(self):
        keywords = ["bug reporting", "saas tools", "project management"]
        seed_keywords(self.db_path, "reddit", keywords)
        conn = get_connection(self.db_path)
        rows = conn.execute(
            "SELECT * FROM keyword_performance WHERE platform = ?", ("reddit",)
        ).fetchall()
        conn.close()
        self.assertEqual(len(rows), 3)

    def test_seed_keywords_idempotent(self):
        keywords = ["bug reporting"]
        seed_keywords(self.db_path, "reddit", keywords)
        seed_keywords(self.db_path, "reddit", keywords)
        conn = get_connection(self.db_path)
        rows = conn.execute(
            "SELECT * FROM keyword_performance WHERE platform = ? AND keyword = ?",
            ("reddit", "bug reporting"),
        ).fetchall()
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
        row = conn.execute(
            "SELECT * FROM peak_times WHERE platform = ? AND day_of_week = ? AND hour = ?",
            ("twitter", 2, 14),
        ).fetchone()
        conn.close()
        self.assertEqual(row["sample_count"], 1)
        self.assertGreater(row["engagement_score"], 0)

    def test_update_peak_times_accumulates(self):
        update_peak_times(self.db_path, "twitter", day=2, hour=14, replies=2, upvotes=6)
        update_peak_times(self.db_path, "twitter", day=2, hour=14, replies=4, upvotes=10)
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM peak_times WHERE platform = ? AND day_of_week = ? AND hour = ?",
            ("twitter", 2, 14),
        ).fetchone()
        conn.close()
        self.assertEqual(row["sample_count"], 2)
        # avg_replies should be average of 2 and 4 = 3
        self.assertAlmostEqual(row["avg_replies"], 3.0, places=1)

    def test_get_best_hours(self):
        update_peak_times(self.db_path, "twitter", day=0, hour=10, replies=1, upvotes=2)
        update_peak_times(self.db_path, "twitter", day=2, hour=14, replies=5, upvotes=15)
        update_peak_times(self.db_path, "twitter", day=4, hour=16, replies=3, upvotes=8)
        result = get_best_hours(self.db_path, "twitter", top_n=2)
        self.assertEqual(len(result), 2)
        # Best hour should be day=2, hour=14
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
        aid = log_action(self.db_path, sid, "reddit", "comment", "https://reddit.com/1",
                         content="test")
        conn = get_connection(self.db_path)
        conn.execute(
            "INSERT INTO outcomes (action_id, check_number, upvotes, replies) VALUES (?, 1, 10, 2)",
            (aid,),
        )
        conn.commit()
        conn.close()
        score = calculate_engagement_score(self.db_path, aid)
        # (10 * 1) + (2 * 5) = 20
        self.assertEqual(score, 20)

    def test_calculate_engagement_score_no_outcomes(self):
        from gtm.db import create_session, log_action
        sid = create_session(self.db_path, "reddit")
        aid = log_action(self.db_path, sid, "reddit", "comment", "https://reddit.com/1",
                         content="test")
        score = calculate_engagement_score(self.db_path, aid)
        self.assertEqual(score, 0)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_analytics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gtm.analytics'`

**Step 3: Write minimal implementation**

Create `gtm/analytics.py`:

```python
from datetime import datetime, timedelta

from gtm.db import get_connection


def update_keyword_score(db_path, keyword, platform, replies=0, upvotes=0,
                         comments_made=1, posts_found=0):
    now = datetime.utcnow().isoformat()
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT * FROM keyword_performance WHERE keyword = ? AND platform = ?",
            (keyword, platform),
        ).fetchone()

        if existing:
            new_times = existing["times_used"] + 1
            new_replies = existing["replies_received"] + replies
            new_comments = existing["comments_made"] + comments_made
            new_posts = existing["posts_found"] + posts_found
            total_upvotes = existing["avg_upvotes"] * existing["times_used"] + upvotes
            new_avg_upvotes = total_upvotes / new_times

            # Recency bonus: +2 if used in last 3 days
            recency_bonus = 2.0
            score = (new_replies * 3) + (new_avg_upvotes * 1) + (new_comments * 0.5) + recency_bonus

            conn.execute(
                """UPDATE keyword_performance
                   SET times_used = ?, posts_found = ?, comments_made = ?,
                       replies_received = ?, avg_upvotes = ?, last_used_at = ?, score = ?
                   WHERE keyword = ? AND platform = ?""",
                (new_times, new_posts, new_comments, new_replies, new_avg_upvotes,
                 now, score, keyword, platform),
            )
        else:
            score = (replies * 3) + (upvotes * 1) + (comments_made * 0.5) + 2.0
            conn.execute(
                """INSERT INTO keyword_performance
                   (keyword, platform, times_used, posts_found, comments_made,
                    replies_received, avg_upvotes, last_used_at, score)
                   VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)""",
                (keyword, platform, posts_found, comments_made, replies,
                 upvotes, now, score),
            )
        conn.commit()
    finally:
        conn.close()


def get_weighted_keywords(db_path, platform, n=5):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT keyword, score FROM keyword_performance WHERE platform = ? ORDER BY score DESC",
            (platform,),
        ).fetchall()
    finally:
        conn.close()
    return [(r["keyword"], r["score"]) for r in rows[:n]]


def seed_keywords(db_path, platform, keywords):
    conn = get_connection(db_path)
    try:
        for kw in keywords:
            conn.execute(
                """INSERT OR IGNORE INTO keyword_performance
                   (keyword, platform, times_used, score)
                   VALUES (?, ?, 0, 0)""",
                (kw, platform),
            )
        conn.commit()
    finally:
        conn.close()


def update_peak_times(db_path, platform, day, hour, replies=0, upvotes=0):
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT * FROM peak_times WHERE platform = ? AND day_of_week = ? AND hour = ?",
            (platform, day, hour),
        ).fetchone()

        engagement = (upvotes * 1) + (replies * 5)

        if existing:
            n = existing["sample_count"]
            new_n = n + 1
            new_avg_replies = (existing["avg_replies"] * n + replies) / new_n
            new_avg_upvotes = (existing["avg_upvotes"] * n + upvotes) / new_n
            new_score = (existing["engagement_score"] * n + engagement) / new_n

            conn.execute(
                """UPDATE peak_times
                   SET actions_taken = actions_taken + 1,
                       avg_replies = ?, avg_upvotes = ?,
                       engagement_score = ?, sample_count = ?
                   WHERE platform = ? AND day_of_week = ? AND hour = ?""",
                (new_avg_replies, new_avg_upvotes, new_score, new_n,
                 platform, day, hour),
            )
        else:
            conn.execute(
                """INSERT INTO peak_times
                   (platform, day_of_week, hour, actions_taken,
                    avg_replies, avg_upvotes, engagement_score, sample_count)
                   VALUES (?, ?, ?, 1, ?, ?, ?, 1)""",
                (platform, day, hour, replies, upvotes, engagement),
            )
        conn.commit()
    finally:
        conn.close()


def get_best_hours(db_path, platform, top_n=3):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT day_of_week, hour, engagement_score, sample_count
               FROM peak_times
               WHERE platform = ?
               ORDER BY engagement_score DESC
               LIMIT ?""",
            (platform, top_n),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def calculate_engagement_score(db_path, action_id):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """SELECT COALESCE(MAX(upvotes), 0) as upvotes,
                      COALESCE(MAX(replies), 0) as replies
               FROM outcomes WHERE action_id = ?""",
            (action_id,),
        ).fetchone()
    finally:
        conn.close()
    if row["upvotes"] == 0 and row["replies"] == 0:
        return 0
    return (row["upvotes"] * 1) + (row["replies"] * 5)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_analytics.py -v`
Expected: ALL PASS

**Step 5: Run all tests**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add gtm/analytics.py tests/test_analytics.py
git commit -m "feat: add analytics module — keyword scoring, peak times, engagement scoring"
```

---

### Task 5: Relationships Module

**Files:**
- Create: `gtm/relationships.py`
- Create: `tests/test_relationships.py`

**Step 1: Write the failing tests**

Create `tests/test_relationships.py`:

```python
import json
import os
import tempfile
import unittest

from gtm.db import init_db, get_connection, create_session, log_action
from gtm.relationships import (
    track_interaction,
    get_known_users,
    get_high_value_users,
    is_known_user,
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
        track_interaction(self.db_path, "reddit", "devguy42", "Dev Guy",
                          aid, "comment")
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM relationships WHERE platform = ? AND username = ?",
            ("reddit", "devguy42"),
        ).fetchone()
        conn.close()
        self.assertEqual(row["interaction_count"], 1)
        self.assertEqual(row["display_name"], "Dev Guy")

    def test_track_interaction_increments_count(self):
        aid1 = log_action(self.db_path, self.sid, "reddit", "comment",
                          "https://reddit.com/1", content="test")
        aid2 = log_action(self.db_path, self.sid, "reddit", "like",
                          "https://reddit.com/2")
        track_interaction(self.db_path, "reddit", "devguy42", "Dev Guy",
                          aid1, "comment")
        track_interaction(self.db_path, "reddit", "devguy42", "Dev Guy",
                          aid2, "like")
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM relationships WHERE platform = ? AND username = ?",
            ("reddit", "devguy42"),
        ).fetchone()
        conn.close()
        self.assertEqual(row["interaction_count"], 2)

    def test_track_interaction_stores_interactions_json(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        track_interaction(self.db_path, "reddit", "devguy42", "Dev Guy",
                          aid, "comment")
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT interactions FROM relationships WHERE username = ?",
            ("devguy42",),
        ).fetchone()
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
        # User with 3 interactions
        for _ in range(3):
            track_interaction(self.db_path, "reddit", "frequent_user", "Freq",
                              aid, "comment")
        # User with 1 interaction
        track_interaction(self.db_path, "reddit", "onetime_user", "Once",
                          aid, "like")
        high = get_high_value_users(self.db_path, "reddit", min_interactions=3)
        self.assertEqual(len(high), 1)
        self.assertEqual(high[0]["username"], "frequent_user")

    def test_is_known_user_true(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        track_interaction(self.db_path, "reddit", "known_user", "Known",
                          aid, "comment")
        self.assertTrue(is_known_user(self.db_path, "reddit", "known_user"))

    def test_is_known_user_false(self):
        self.assertFalse(is_known_user(self.db_path, "reddit", "stranger"))

    def test_is_known_user_wrong_platform(self):
        aid = log_action(self.db_path, self.sid, "reddit", "comment",
                         "https://reddit.com/1", content="test")
        track_interaction(self.db_path, "reddit", "reddit_user", "RU",
                          aid, "comment")
        self.assertFalse(is_known_user(self.db_path, "twitter", "reddit_user"))


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_relationships.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create `gtm/relationships.py`:

```python
import json
from datetime import datetime

from gtm.db import get_connection


def track_interaction(db_path, platform, username, display_name, action_id,
                      interaction_type):
    now = datetime.utcnow().isoformat()
    interaction_entry = {
        "action_id": action_id,
        "type": interaction_type,
        "date": now,
    }
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT * FROM relationships WHERE platform = ? AND username = ?",
            (platform, username),
        ).fetchone()

        if existing:
            interactions = json.loads(existing["interactions"] or "[]")
            interactions.append(interaction_entry)
            new_count = existing["interaction_count"] + 1
            score = new_count * 2
            conn.execute(
                """UPDATE relationships
                   SET interaction_count = ?, last_interacted = ?,
                       interactions = ?, relationship_score = ?,
                       display_name = ?
                   WHERE platform = ? AND username = ?""",
                (new_count, now, json.dumps(interactions), score,
                 display_name, platform, username),
            )
        else:
            interactions = json.dumps([interaction_entry])
            conn.execute(
                """INSERT INTO relationships
                   (platform, username, display_name, last_interacted,
                    interaction_count, interactions, relationship_score)
                   VALUES (?, ?, ?, ?, 1, ?, 2)""",
                (platform, username, display_name, now, interactions),
            )
        conn.commit()
    finally:
        conn.close()


def get_known_users(db_path, platform):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT username, display_name, interaction_count, relationship_score
               FROM relationships WHERE platform = ?
               ORDER BY relationship_score DESC""",
            (platform,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_high_value_users(db_path, platform, min_interactions=3):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT username, display_name, interaction_count, relationship_score
               FROM relationships
               WHERE platform = ? AND interaction_count >= ?
               ORDER BY relationship_score DESC""",
            (platform, min_interactions),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def is_known_user(db_path, platform, username):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM relationships WHERE platform = ? AND username = ?",
            (platform, username),
        ).fetchone()
    finally:
        conn.close()
    return row is not None
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_relationships.py -v`
Expected: ALL PASS

**Step 5: Run all tests**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add gtm/relationships.py tests/test_relationships.py
git commit -m "feat: add relationships module — track users across sessions"
```

---

### Task 6: Threads Module

**Files:**
- Create: `gtm/threads.py`
- Create: `tests/test_threads.py`

**Step 1: Write the failing tests**

Create `tests/test_threads.py`:

```python
import json
import os
import tempfile
import unittest

from gtm.db import init_db, get_connection, create_session
from gtm.threads import (
    log_thread,
    get_recent_threads,
    format_thread,
)


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
            "This week I shipped auth for Acme. Here's how it went (thread)",
            "First, I tried Supabase Auth. Setup took 10 minutes. But the redirect flow broke on mobile.",
            "Switched to custom JWT + Supabase RLS. More work upfront but way more control.",
            "Lesson: don't pick the easy path if your users are mostly on mobile.",
        ]
        tid = log_thread(
            self.db_path, self.sid, "building_in_public",
            "Shipping auth for Acme",
            tweets, "https://x.com/mihir/status/123",
        )
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
        log_thread(self.db_path, self.sid, "general_founder",
                   "Topic A", tweets, "https://x.com/1")
        log_thread(self.db_path, self.sid, "building_in_public",
                   "Topic B", tweets, "https://x.com/2")
        recent = get_recent_threads(self.db_path, days=7)
        self.assertEqual(len(recent), 2)

    def test_get_recent_threads_returns_topics(self):
        tweets = ["tweet1", "tweet2"]
        log_thread(self.db_path, self.sid, "general_founder",
                   "Hot take on tools", tweets, "https://x.com/1")
        recent = get_recent_threads(self.db_path, days=7)
        self.assertEqual(recent[0]["topic"], "Hot take on tools")

    def test_format_thread_enforces_280_limit(self):
        tweets = [
            "Short tweet",
            "A" * 300,  # Too long
            "Another short one",
        ]
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_threads.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Create `gtm/threads.py`:

```python
import json
from datetime import datetime, timedelta

from gtm.db import get_connection

THREAD_TYPES = ["building_in_public", "general_founder"]
MAX_TWEET_LENGTH = 280


def log_thread(db_path, session_id, thread_type, topic, tweets, first_tweet_url):
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO threads
               (session_id, thread_type, topic, tweet_count,
                first_tweet_url, content)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, thread_type, topic, len(tweets),
             first_tweet_url, json.dumps(tweets)),
        )
        tid = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return tid


def get_recent_threads(db_path, days=14):
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT topic, thread_type, tweet_count, first_tweet_url, posted_at
               FROM threads
               WHERE posted_at > ?
               ORDER BY posted_at DESC""",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def format_thread(tweets):
    formatted = []
    for tweet in tweets:
        if len(tweet) > MAX_TWEET_LENGTH:
            # Truncate and add ellipsis
            formatted.append(tweet[:277] + "...")
        else:
            formatted.append(tweet)
    return formatted
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_threads.py -v`
Expected: ALL PASS

**Step 5: Run all tests**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add gtm/threads.py tests/test_threads.py
git commit -m "feat: add threads module — Twitter thread logging and formatting"
```

---

### Task 7: Content Calendar Module

**Files:**
- Create: `gtm/calendar.py`
- Create: `tests/test_calendar.py`

**Step 1: Write the failing tests**

Create `tests/test_calendar.py`:

```python
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from gtm.db import init_db, get_connection, create_session, log_action
from gtm.calendar import (
    add_content,
    get_today_content,
    mark_posted,
    get_upcoming,
)


class TestCalendar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_content(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cid = add_content(
            self.db_path, "twitter", "thread",
            "Shipping auth update", "Talk about Supabase auth flow",
            today,
        )
        self.assertIsNotNone(cid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM content_calendar WHERE id = ?", (cid,)).fetchone()
        conn.close()
        self.assertEqual(row["platform"], "twitter")
        self.assertEqual(row["content_type"], "thread")
        self.assertEqual(row["status"], "planned")

    def test_get_today_content(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        add_content(self.db_path, "twitter", "thread", "Topic A", "Outline A", today)
        add_content(self.db_path, "devto", "article", "Topic B", "Outline B", today)
        # Tomorrow's content should not show
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        add_content(self.db_path, "twitter", "thread", "Topic C", "Outline C", tomorrow)

        result = get_today_content(self.db_path, "twitter")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["topic"], "Topic A")

    def test_get_today_content_excludes_posted(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cid = add_content(self.db_path, "twitter", "thread", "Done topic", "Done", today)
        sid = create_session(self.db_path, "twitter")
        aid = log_action(self.db_path, sid, "twitter", "comment", "https://x.com/1")
        mark_posted(self.db_path, cid, aid)
        result = get_today_content(self.db_path, "twitter")
        self.assertEqual(len(result), 0)

    def test_mark_posted(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cid = add_content(self.db_path, "twitter", "thread", "Topic", "Outline", today)
        sid = create_session(self.db_path, "twitter")
        aid = log_action(self.db_path, sid, "twitter", "comment", "https://x.com/1")
        mark_posted(self.db_path, cid, aid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM content_calendar WHERE id = ?", (cid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "posted")
        self.assertEqual(row["action_id"], aid)

    def test_get_upcoming(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        day_after = (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%d")
        far_future = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")

        add_content(self.db_path, "twitter", "thread", "Today", "O", today)
        add_content(self.db_path, "devto", "article", "Tomorrow", "O", tomorrow)
        add_content(self.db_path, "reddit", "post", "Day after", "O", day_after)
        add_content(self.db_path, "twitter", "thread", "Far future", "O", far_future)

        result = get_upcoming(self.db_path, days=3)
        self.assertEqual(len(result), 3)  # today, tomorrow, day_after

    def test_get_upcoming_excludes_posted(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cid = add_content(self.db_path, "twitter", "thread", "Done", "O", today)
        sid = create_session(self.db_path, "twitter")
        aid = log_action(self.db_path, sid, "twitter", "comment", "https://x.com/1")
        mark_posted(self.db_path, cid, aid)
        add_content(self.db_path, "devto", "article", "Pending", "O", today)
        result = get_upcoming(self.db_path, days=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["topic"], "Pending")


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_calendar.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Create `gtm/calendar.py`:

```python
from datetime import datetime, timedelta

from gtm.db import get_connection


def add_content(db_path, platform, content_type, topic, outline, scheduled_for):
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO content_calendar
               (platform, content_type, topic, outline, scheduled_for)
               VALUES (?, ?, ?, ?, ?)""",
            (platform, content_type, topic, outline, scheduled_for),
        )
        cid = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return cid


def get_today_content(db_path, platform):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT id, content_type, topic, outline
               FROM content_calendar
               WHERE platform = ? AND scheduled_for = ? AND status = 'planned'""",
            (platform, today),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def mark_posted(db_path, calendar_id, action_id):
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE content_calendar SET status = 'posted', action_id = ? WHERE id = ?",
            (action_id, calendar_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_upcoming(db_path, days=3):
    cutoff = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT id, platform, content_type, topic, outline, scheduled_for
               FROM content_calendar
               WHERE scheduled_for >= ? AND scheduled_for <= ? AND status = 'planned'
               ORDER BY scheduled_for""",
            (today, cutoff),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_calendar.py -v`
Expected: ALL PASS

**Step 5: Run all tests**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add gtm/calendar.py tests/test_calendar.py
git commit -m "feat: add calendar module — content planning and scheduling"
```

---

### Task 8: Cron Module — Reply Checker Scheduling

**Files:**
- Create: `gtm/cron.py`
- Create: `tests/test_cron.py`

**Step 1: Write the failing tests**

Create `tests/test_cron.py`:

```python
import unittest

from gtm.cron import (
    build_reply_checker_prompt,
    REPLY_CHECK_INTERVAL_MIN,
)


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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_cron.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Create `gtm/cron.py`:

```python
"""Cron job management for GTM reply checking.

This module builds prompts for CronCreate/CronDelete. The actual cron tools
are Claude Code built-ins — this module just provides the prompt text and
interval configuration.

Usage during a session:
    # Start: use CronCreate with the prompt from build_reply_checker_prompt()
    # Stop:  use CronDelete with the job ID returned by CronCreate
"""

REPLY_CHECK_INTERVAL_MIN = 15


def build_reply_checker_prompt(db_path):
    return f"""Check for replies to tracked comments and respond if needed.

1. Run this Python to get due checks:
```python
from gtm.engagement import get_due_checks
due = get_due_checks("{db_path}")
print(f"{{len(due)}} comments due for checking")
for entry in due:
    print(f"  - [{{entry['platform']}}] {{entry['target_url']}} (check #{{entry['checks_done'] + 1}})")
```

2. For each due entry:
   - Open the target_url in the browser via Owl
   - Find our comment (look for our username)
   - Check if anyone replied to our comment
   - Take a screenshot to verify

3. Record the check:
```python
from gtm.engagement import record_check, should_reply, mark_replied
record_check("{db_path}", tracking_id, upvotes=X, replies=Y,
             reply_content="their reply text", reply_author="username")
```

4. If someone replied, use 70/30 probability to decide whether to reply back:
```python
if should_reply(reply_content):
    # Write a contextual, human-sounding response
    # Post it via Owl
    # Log it: mark_replied("{db_path}", tracking_id, reply_action_id)
```

5. Log decisions:
```python
from gtm.decisions import log_decision
log_decision("{db_path}", "reply", "Replied to @user about X", "relevant question")
```

6. Update analytics:
```python
from gtm.analytics import update_keyword_score, update_peak_times
```

Remember: multiply Owl screenshot coordinates by 1.5 for click targets (screen is 1920x1080, screenshots are 1280x720).
"""


def get_cron_expression():
    """Returns the cron expression for every 15 minutes."""
    return f"*/{REPLY_CHECK_INTERVAL_MIN} * * * *"
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_cron.py -v`
Expected: ALL PASS

**Step 5: Run all tests**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add gtm/cron.py tests/test_cron.py
git commit -m "feat: add cron module — reply checker prompt and scheduling config"
```

---

### Task 9: Integrate Modules into InterleavedRunner

**Files:**
- Modify: `gtm/runner.py` (add module integration after record_action)
- Modify: `tests/test_runner.py` (add integration tests)

**Step 1: Write the failing tests**

Add to `tests/test_runner.py`, inside the `TestInterleavedRunner` class:

```python
def test_record_action_enrolls_comment_for_tracking(self):
    runner = InterleavedRunner(self.db_path, self.state_path)
    runner.start_all()
    aid = runner.record_action("twitter", "comment", "https://x.com/post/1",
                               content="great thread tbh")
    from gtm.engagement import get_active_tracking_count
    count = get_active_tracking_count(self.db_path)
    self.assertEqual(count, 1)

def test_record_action_skips_tracking_for_likes(self):
    runner = InterleavedRunner(self.db_path, self.state_path)
    runner.start_all()
    runner.record_action("twitter", "like", "https://x.com/post/1")
    from gtm.engagement import get_active_tracking_count
    count = get_active_tracking_count(self.db_path)
    self.assertEqual(count, 0)

def test_record_action_enrolls_like_and_comment(self):
    runner = InterleavedRunner(self.db_path, self.state_path)
    runner.start_all()
    runner.record_action("reddit", "like_and_comment", "https://reddit.com/1",
                         content="so true lol")
    from gtm.engagement import get_active_tracking_count
    count = get_active_tracking_count(self.db_path)
    self.assertEqual(count, 1)

def test_record_action_logs_decision(self):
    runner = InterleavedRunner(self.db_path, self.state_path)
    runner.start_all()
    runner.record_action("twitter", "comment", "https://x.com/1",
                         content="nice")
    from gtm.decisions import get_recent_decisions
    decisions = get_recent_decisions(self.db_path, category="engagement")
    self.assertGreaterEqual(len(decisions), 1)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_runner.py::TestInterleavedRunner::test_record_action_enrolls_comment_for_tracking -v`
Expected: FAIL

**Step 3: Modify InterleavedRunner.record_action**

In `gtm/runner.py`, add imports at the top:

```python
from gtm.engagement import enroll_for_tracking
from gtm.decisions import log_decision
```

Modify the `record_action` method in `InterleavedRunner`:

```python
def record_action(self, platform, action_type, target_url, target_title=None,
                  content=None, promoted_product=None, keywords_matched=None,
                  comment_url=None, author_username=None):
    """Log an action for a specific platform."""
    if platform not in self.session_ids:
        return None
    aid = log_action(
        self.db_path, self.session_ids[platform], platform, action_type,
        target_url, target_title, content, promoted_product, keywords_matched,
    )
    self.platform_actions[platform] += 1
    self.total_actions += 1

    # Auto-enroll comments for reply tracking
    if action_type in ('comment', 'like_and_comment', 'reply'):
        enroll_for_tracking(self.db_path, aid, platform, target_url, comment_url)
        log_decision(
            self.db_path, "engagement",
            f"Enrolled {action_type} for reply tracking",
            f"Posted on {platform}: {target_url}",
            session_id=self.session_ids[platform],
            platform=platform,
        )

    # Track relationships if author known
    if author_username:
        from gtm.relationships import track_interaction
        track_interaction(
            self.db_path, platform, author_username, None,
            aid, action_type,
        )

    return aid
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/test_runner.py -v`
Expected: ALL PASS

**Step 5: Run all tests**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add gtm/runner.py tests/test_runner.py
git commit -m "feat: integrate engagement, decisions, relationships into InterleavedRunner"
```

---

### Task 10: Extend CLI with New Commands

**Files:**
- Modify: `gtm/cli.py` (add calendar, keywords, relationships commands)
- No separate tests needed — these are thin wrappers

**Step 1: Add new CLI commands**

In `gtm/cli.py`, add new command functions and register them:

```python
def cmd_calendar(args):
    from gtm.calendar import get_upcoming
    upcoming = get_upcoming(DB_PATH, days=7)
    if upcoming:
        print("=== Content Calendar ===")
        for item in upcoming:
            print(f"  [{item['scheduled_for']}] {item['platform']}/{item['content_type']}: {item['topic']}")
    else:
        print("No upcoming content planned. Use 'plan-week' to generate.")


def cmd_keywords(args):
    from gtm.analytics import get_weighted_keywords
    from gtm.state import PLATFORMS
    print("=== Keyword Performance ===")
    for p in PLATFORMS:
        kws = get_weighted_keywords(DB_PATH, p, n=5)
        if kws:
            print(f"\n  {p}:")
            for kw, score in kws:
                print(f"    {kw}: {score:.1f}")
    if not any(get_weighted_keywords(DB_PATH, p, n=1) for p in PLATFORMS):
        print("  (no keyword data yet)")


def cmd_relationships(args):
    from gtm.relationships import get_high_value_users
    from gtm.state import PLATFORMS
    print("=== High-Value Relationships ===")
    found = False
    for p in PLATFORMS:
        users = get_high_value_users(DB_PATH, p, min_interactions=2)
        if users:
            found = True
            print(f"\n  {p}:")
            for u in users:
                print(f"    @{u['username']} ({u['interaction_count']} interactions, score {u['relationship_score']:.0f})")
    if not found:
        print("  (no high-value relationships yet)")


def cmd_tracking(args):
    from gtm.engagement import get_active_tracking_count
    from gtm.db import get_connection
    count = get_active_tracking_count(DB_PATH)
    print(f"=== Reply Tracking ===")
    print(f"  Active trackers: {count}")
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        "SELECT platform, COUNT(*) as cnt FROM reply_tracking WHERE status = 'active' GROUP BY platform"
    ).fetchall()
    conn.close()
    for r in rows:
        print(f"    {r['platform']}: {r['cnt']}")


def cmd_decisions(args):
    from gtm.decisions import get_recent_decisions
    decisions = get_recent_decisions(DB_PATH, limit=10)
    if decisions:
        print("=== Recent Decisions ===")
        for d in decisions:
            platform = d.get('platform') or 'global'
            print(f"  [{d['category']}] ({platform}) {d['decision']}")
            if d.get('reasoning'):
                print(f"    Why: {d['reasoning']}")
    else:
        print("No decisions logged yet.")
```

Register them in `main()`:

```python
sub.add_parser("calendar", help="Show upcoming content calendar")
sub.add_parser("keywords", help="Show keyword performance")
sub.add_parser("relationships", help="Show high-value relationships")
sub.add_parser("tracking", help="Show active reply tracking")
sub.add_parser("decisions", help="Show recent decisions")
```

Update the dispatch dict:

```python
commands = {
    "init": cmd_init, "status": cmd_status, "stats": cmd_stats,
    "alerts": cmd_alerts, "calendar": cmd_calendar,
    "keywords": cmd_keywords, "relationships": cmd_relationships,
    "tracking": cmd_tracking, "decisions": cmd_decisions,
}
commands[args.command](args)
```

**Step 2: Test manually**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m gtm calendar`
Expected: "No upcoming content planned."

Run: `cd /Users/mihirkanzariya/GTM && python3 -m gtm keywords`
Expected: "(no keyword data yet)"

Run: `cd /Users/mihirkanzariya/GTM && python3 -m gtm tracking`
Expected: "Active trackers: 0" (or current count)

**Step 3: Run all tests**

Run: `cd /Users/mihirkanzariya/GTM && python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add gtm/cli.py
git commit -m "feat: add CLI commands — calendar, keywords, relationships, tracking, decisions"
```

---

### Task 11: Update CLAUDE.md with v2 Session Workflow

**Files:**
- Modify: `CLAUDE.md` (update session workflow to use new modules)

**Step 1: Add v2 session workflow section**

Add a new section to `CLAUDE.md` after the existing "How to Run a Session" section:

```markdown
## v2 Enhanced Session Flow

### Before Session
```python
# Bootstrap context from decision log
from gtm.decisions import get_decision_summary
summary = get_decision_summary('/Users/mihirkanzariya/GTM/gtm.db', days=7)
# Review: active trackers, promo ratios, keyword scores, today's calendar
```

### During Session — After Each Comment
The InterleavedRunner now auto-enrolls comments for reply tracking. When calling record_action, pass additional context:
```python
runner.record_action(
    platform, action_type, target_url,
    content="comment text",
    comment_url="direct link to our comment",  # if available
    author_username="post_author",              # for relationship tracking
    keywords_matched="keyword used",            # for keyword scoring
)
```

### Thread Creation (Twitter, 1 per session max)
```python
from gtm.calendar import get_today_content
from gtm.threads import log_thread, format_thread, get_recent_threads

# Check calendar first
planned = get_today_content(db_path, 'twitter')
# Check recent threads to avoid repeats
recent = get_recent_threads(db_path, days=14)
# Post via Owl on https://x.com
# Log: log_thread(db_path, session_id, thread_type, topic, tweets, url)
```

### Reply Checker (Cron-based)
```python
from gtm.cron import build_reply_checker_prompt, get_cron_expression
# At session start: CronCreate with get_cron_expression() and build_reply_checker_prompt()
# At session end: CronDelete the job
```

### New CLI Commands
- `python3 -m gtm calendar` — View upcoming content
- `python3 -m gtm keywords` — Keyword performance per platform
- `python3 -m gtm relationships` — High-value user connections
- `python3 -m gtm tracking` — Active reply trackers
- `python3 -m gtm decisions` — Recent decision log
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add v2 session workflow with reply tracking, threads, analytics to CLAUDE.md"
```

---

## Summary

| Task | Module | Tests | Description |
|------|--------|-------|-------------|
| 1 | db.py | test_db.py | 7 new tables + modified outcomes + indexes |
| 2 | decisions.py | test_decisions.py | Decision logging + session bootstrap |
| 3 | engagement.py | test_engagement.py | Reply tracking, 15min checks, 70/30 auto-reply |
| 4 | analytics.py | test_analytics.py | Keyword scoring, peak times, engagement scores |
| 5 | relationships.py | test_relationships.py | User tracking across sessions |
| 6 | threads.py | test_threads.py | Twitter thread logging + formatting |
| 7 | calendar.py | test_calendar.py | Content planning + scheduling |
| 8 | cron.py | test_cron.py | Reply checker prompt + cron config |
| 9 | runner.py | test_runner.py | Integrate all modules into InterleavedRunner |
| 10 | cli.py | manual | 5 new CLI commands |
| 11 | CLAUDE.md | — | Updated session workflow docs |

**Total: 11 tasks, ~8 new files, ~6 new test files, 7 new DB tables**

Dependencies: Task 1 must go first (schema). Tasks 2-8 can be done in any order after Task 1. Task 9 depends on 2, 3, 5. Task 10 depends on 2-8. Task 11 is last.
