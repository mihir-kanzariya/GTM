# GTM Session Workflow & Logging — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python-based session runner with SQLite logging, state management, and CLI stats reporting for the GTM social media automation system.

**Architecture:** A single Python package (`~/GTM/gtm/`) with modules for database, state management, session runner, and stats CLI. The session runner reads `state.json` and `CLAUDE.md` to pick a platform, then provides the workflow logic. Actual browser actions are delegated to the owl plugin (not implemented here — we build the orchestration layer). All data flows through a SQLite database at `~/GTM/gtm.db`.

**Tech Stack:** Python 3.9+, sqlite3 (stdlib), json (stdlib), argparse (stdlib). No external dependencies.

---

### Task 1: Initialize SQLite Database Module

**Files:**
- Create: `~/GTM/gtm/__init__.py`
- Create: `~/GTM/gtm/db.py`
- Create: `~/GTM/tests/__init__.py`
- Create: `~/GTM/tests/test_db.py`

**Step 1: Create package structure**

```bash
mkdir -p ~/GTM/gtm ~/GTM/tests
touch ~/GTM/gtm/__init__.py ~/GTM/tests/__init__.py
```

**Step 2: Write the failing test**

Create `~/GTM/tests/test_db.py`:

```python
import os
import sqlite3
import tempfile
import unittest

from gtm.db import init_db, get_connection


class TestInitDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")

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
```

**Step 3: Run test to verify it fails**

```bash
cd ~/GTM && python3 -m pytest tests/test_db.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'gtm.db'`

**Step 4: Write minimal implementation**

Create `~/GTM/gtm/db.py`:

```python
import sqlite3
import os


def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            started_at DATETIME NOT NULL,
            ended_at DATETIME,
            total_actions INTEGER DEFAULT 0,
            promoted_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            platform TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_url TEXT,
            target_title TEXT,
            content_written TEXT,
            promoted_product TEXT,
            created_at DATETIME NOT NULL DEFAULT (datetime('now')),
            keywords_matched TEXT
        );

        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id INTEGER NOT NULL REFERENCES actions(id),
            checked_at DATETIME NOT NULL DEFAULT (datetime('now')),
            upvotes INTEGER DEFAULT 0,
            replies INTEGER DEFAULT 0,
            views INTEGER
        );

        CREATE TABLE IF NOT EXISTS daily_metrics (
            date DATE NOT NULL,
            platform TEXT NOT NULL,
            total_actions INTEGER DEFAULT 0,
            comments_written INTEGER DEFAULT 0,
            promotions INTEGER DEFAULT 0,
            promotion_ratio REAL DEFAULT 0.0,
            PRIMARY KEY (date, platform)
        );

        CREATE INDEX IF NOT EXISTS idx_actions_target_url ON actions(target_url);
        CREATE INDEX IF NOT EXISTS idx_actions_session ON actions(session_id);
        CREATE INDEX IF NOT EXISTS idx_actions_platform_date ON actions(platform, created_at);
        CREATE INDEX IF NOT EXISTS idx_outcomes_action ON outcomes(action_id);
    """)
    conn.close()
```

**Step 5: Run test to verify it passes**

```bash
cd ~/GTM && python3 -m pytest tests/test_db.py -v
```
Expected: 2 tests PASS

**Step 6: Commit**

```bash
cd ~/GTM && git init && git add gtm/ tests/ && git commit -m "feat: add SQLite database module with schema init"
```

---

### Task 2: Database CRUD Operations

**Files:**
- Modify: `~/GTM/gtm/db.py`
- Create: `~/GTM/tests/test_db_crud.py`

**Step 1: Write the failing tests**

Create `~/GTM/tests/test_db_crud.py`:

```python
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
                   content="nice post", promoted_product="blocpad")
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
                   content="check this", promoted_product="blocfeed")
        ratio = get_promotion_ratio(self.db_path, "reddit", days=7)
        self.assertAlmostEqual(ratio, 0.1, places=2)  # 1 promo / 10 total


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

```bash
cd ~/GTM && python3 -m pytest tests/test_db_crud.py -v
```
Expected: FAIL — `ImportError: cannot import name 'create_session'`

**Step 3: Write minimal implementation**

Add to `~/GTM/gtm/db.py`:

```python
import uuid
from datetime import datetime


def create_session(db_path, platform):
    sid = str(uuid.uuid4())
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO sessions (id, platform, started_at) VALUES (?, ?, ?)",
        (sid, platform, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return sid


def end_session(db_path, session_id):
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT COUNT(*) as total, COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos FROM actions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    conn.execute(
        "UPDATE sessions SET ended_at = ?, total_actions = ?, promoted_count = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), row["total"], row["promos"], session_id),
    )
    conn.commit()
    conn.close()


def log_action(db_path, session_id, platform, action_type, target_url,
               target_title=None, content=None, promoted_product=None,
               keywords_matched=None):
    conn = get_connection(db_path)
    cursor = conn.execute(
        """INSERT INTO actions
           (session_id, platform, action_type, target_url, target_title,
            content_written, promoted_product, keywords_matched)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, platform, action_type, target_url, target_title,
         content, promoted_product, keywords_matched),
    )
    action_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return action_id


def is_duplicate_url(db_path, url, days=7):
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT id FROM actions WHERE target_url = ? AND created_at > datetime('now', ?)",
        (url, f"-{days} days"),
    ).fetchone()
    conn.close()
    return row is not None


def get_promotion_ratio(db_path, platform, days=7):
    conn = get_connection(db_path)
    row = conn.execute(
        """SELECT
             COUNT(*) as total,
             COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
           FROM actions
           WHERE platform = ? AND created_at > datetime('now', ?)""",
        (platform, f"-{days} days"),
    ).fetchone()
    conn.close()
    if row["total"] == 0:
        return 0.0
    return row["promos"] / row["total"]
```

**Step 4: Run test to verify it passes**

```bash
cd ~/GTM && python3 -m pytest tests/test_db_crud.py -v
```
Expected: 6 tests PASS

**Step 5: Commit**

```bash
cd ~/GTM && git add gtm/db.py tests/test_db_crud.py && git commit -m "feat: add database CRUD operations for sessions, actions, duplicates, promo ratio"
```

---

### Task 3: State Management Module

**Files:**
- Create: `~/GTM/gtm/state.py`
- Create: `~/GTM/tests/test_state.py`

**Step 1: Write the failing tests**

Create `~/GTM/tests/test_state.py`:

```python
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from gtm.state import load_state, save_state, pick_platform, create_default_state


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, "state.json")

    def test_create_default_state(self):
        state = create_default_state()
        self.assertIn("platforms", state)
        self.assertIn("reddit", state["platforms"])
        self.assertIn("twitter", state["platforms"])
        self.assertIn("producthunt", state["platforms"])
        self.assertIn("indiehackers", state["platforms"])

    def test_load_creates_if_missing(self):
        state = load_state(self.state_path)
        self.assertIn("platforms", state)
        self.assertTrue(os.path.exists(self.state_path))

    def test_save_and_load_roundtrip(self):
        state = create_default_state()
        state["platforms"]["reddit"]["session_count_today"] = 2
        save_state(self.state_path, state)
        loaded = load_state(self.state_path)
        self.assertEqual(loaded["platforms"]["reddit"]["session_count_today"], 2)

    def test_pick_platform_returns_longest_gap(self):
        state = create_default_state()
        old = (datetime.utcnow() - timedelta(hours=10)).isoformat() + "Z"
        recent = (datetime.utcnow() - timedelta(minutes=30)).isoformat() + "Z"
        state["platforms"]["reddit"]["last_session"] = recent
        state["platforms"]["twitter"]["last_session"] = recent
        state["platforms"]["producthunt"]["last_session"] = old
        state["platforms"]["indiehackers"]["last_session"] = recent
        platform = pick_platform(state)
        self.assertEqual(platform, "producthunt")

    def test_pick_platform_respects_session_limit(self):
        state = create_default_state()
        old = (datetime.utcnow() - timedelta(hours=10)).isoformat() + "Z"
        for p in state["platforms"]:
            state["platforms"][p]["last_session"] = old
            state["platforms"][p]["session_count_today"] = 0
        state["platforms"]["producthunt"]["session_count_today"] = 3  # maxed out
        platform = pick_platform(state)
        self.assertNotEqual(platform, "producthunt")

    def test_pick_platform_none_available(self):
        state = create_default_state()
        recent = (datetime.utcnow() - timedelta(minutes=5)).isoformat() + "Z"
        for p in state["platforms"]:
            state["platforms"][p]["last_session"] = recent
            state["platforms"][p]["cooldown_min"] = 180
        platform = pick_platform(state)
        self.assertIsNone(platform)

    def test_daily_reset(self):
        state = create_default_state()
        state["daily_reset"] = "2026-03-01"  # old date
        state["platforms"]["reddit"]["session_count_today"] = 3
        loaded = load_state(self.state_path)
        # Simulate by saving old state then loading
        save_state(self.state_path, state)
        loaded = load_state(self.state_path)
        # load_state should reset counts if daily_reset is not today
        self.assertEqual(loaded["platforms"]["reddit"]["session_count_today"], 0)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

```bash
cd ~/GTM && python3 -m pytest tests/test_state.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'gtm.state'`

**Step 3: Write minimal implementation**

Create `~/GTM/gtm/state.py`:

```python
import json
import os
from datetime import datetime, timedelta


PLATFORMS = ["reddit", "twitter", "producthunt", "indiehackers"]
DEFAULT_COOLDOWNS = {
    "reddit": 180,
    "twitter": 120,
    "producthunt": 240,
    "indiehackers": 180,
}
MAX_SESSIONS_PER_DAY = 3


def create_default_state():
    now = (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z"
    return {
        "platforms": {
            p: {
                "last_session": now,
                "cooldown_min": DEFAULT_COOLDOWNS[p],
                "session_count_today": 0,
            }
            for p in PLATFORMS
        },
        "daily_reset": datetime.utcnow().strftime("%Y-%m-%d"),
    }


def load_state(path):
    if not os.path.exists(path):
        state = create_default_state()
        save_state(path, state)
        return state

    with open(path, "r") as f:
        state = json.load(f)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    if state.get("daily_reset") != today:
        for p in state.get("platforms", {}):
            state["platforms"][p]["session_count_today"] = 0
        state["daily_reset"] = today
        save_state(path, state)

    return state


def save_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def pick_platform(state):
    now = datetime.utcnow()
    candidates = []

    for name, info in state.get("platforms", {}).items():
        if info.get("session_count_today", 0) >= MAX_SESSIONS_PER_DAY:
            continue

        last = datetime.fromisoformat(info["last_session"].replace("Z", "+00:00")).replace(tzinfo=None)
        gap_minutes = (now - last).total_seconds() / 60

        if gap_minutes < info.get("cooldown_min", 180):
            continue

        candidates.append((name, gap_minutes))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]
```

**Step 4: Run test to verify it passes**

```bash
cd ~/GTM && python3 -m pytest tests/test_state.py -v
```
Expected: 7 tests PASS

**Step 5: Commit**

```bash
cd ~/GTM && git add gtm/state.py tests/test_state.py && git commit -m "feat: add state management with platform rotation and cooldown logic"
```

---

### Task 4: Session Runner Module

**Files:**
- Create: `~/GTM/gtm/runner.py`
- Create: `~/GTM/tests/test_runner.py`

**Step 1: Write the failing tests**

Create `~/GTM/tests/test_runner.py`:

```python
import os
import tempfile
import unittest
from unittest.mock import patch
import random

from gtm.runner import SessionRunner, roll_action


class TestRollAction(unittest.TestCase):
    def test_returns_valid_action(self):
        valid = {"like", "comment", "like_and_comment", "skip", "share", "save"}
        for _ in range(100):
            action = roll_action()
            self.assertIn(action, valid)

    def test_distribution_roughly_correct(self):
        counts = {"like": 0, "comment": 0, "like_and_comment": 0, "skip": 0, "share": 0, "save": 0}
        n = 10000
        for _ in range(n):
            counts[roll_action()] += 1
        # likes should be ~25% (allow 18-32%)
        self.assertGreater(counts["like"] / n, 0.18)
        self.assertLess(counts["like"] / n, 0.32)


class TestSessionRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.state_path = os.path.join(self.tmp, "state.json")

    def test_init_picks_platform(self):
        runner = SessionRunner(self.db_path, self.state_path)
        self.assertIn(runner.platform, ["reddit", "twitter", "producthunt", "indiehackers", None])

    def test_session_limits_randomized(self):
        runner = SessionRunner(self.db_path, self.state_path)
        self.assertGreaterEqual(runner.max_actions, 15)
        self.assertLessEqual(runner.max_actions, 30)
        self.assertGreaterEqual(runner.max_duration_min, 10)
        self.assertLessEqual(runner.max_duration_min, 40)

    def test_should_promote_respects_ratio(self):
        runner = SessionRunner(self.db_path, self.state_path)
        if runner.platform is None:
            self.skipTest("No platform available")
        # With no prior actions, promotion should be allowed
        self.assertTrue(runner.should_promote())


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

```bash
cd ~/GTM && python3 -m pytest tests/test_runner.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'gtm.runner'`

**Step 3: Write minimal implementation**

Create `~/GTM/gtm/runner.py`:

```python
import random
from datetime import datetime

from gtm.db import init_db, create_session, end_session, log_action, is_duplicate_url, get_promotion_ratio
from gtm.state import load_state, save_state, pick_platform

# Action weights from master CLAUDE.md
ACTION_WEIGHTS = {
    "like": 25,
    "comment": 20,
    "like_and_comment": 25,
    "skip": 15,
    "share": 5,
    "save": 10,
}
ACTION_POOL = []
for action, weight in ACTION_WEIGHTS.items():
    ACTION_POOL.extend([action] * weight)

PROMO_RATIO_LIMIT = 0.1  # 1 in 10


def roll_action():
    return random.choice(ACTION_POOL)


class SessionRunner:
    def __init__(self, db_path, state_path):
        self.db_path = db_path
        self.state_path = state_path
        self.max_actions = random.randint(15, 30)
        self.max_duration_min = random.randint(10, 40)
        self.action_count = 0
        self.started_at = datetime.utcnow()
        self.session_id = None

        init_db(self.db_path)
        self.state = load_state(self.state_path)
        self.platform = pick_platform(self.state)

        if self.platform:
            self.session_id = create_session(self.db_path, self.platform)

    def should_promote(self):
        if not self.platform:
            return False
        ratio = get_promotion_ratio(self.db_path, self.platform, days=7)
        return ratio < PROMO_RATIO_LIMIT

    def is_duplicate(self, url):
        return is_duplicate_url(self.db_path, url)

    def record_action(self, action_type, target_url, target_title=None,
                      content=None, promoted_product=None, keywords_matched=None):
        if not self.session_id:
            return None
        aid = log_action(
            self.db_path, self.session_id, self.platform, action_type,
            target_url, target_title, content, promoted_product, keywords_matched,
        )
        self.action_count += 1
        return aid

    def is_session_over(self):
        if self.action_count >= self.max_actions:
            return True
        elapsed = (datetime.utcnow() - self.started_at).total_seconds() / 60
        return elapsed >= self.max_duration_min

    def finish(self):
        if self.session_id:
            end_session(self.db_path, self.session_id)
        if self.platform:
            self.state["platforms"][self.platform]["last_session"] = datetime.utcnow().isoformat() + "Z"
            self.state["platforms"][self.platform]["session_count_today"] = (
                self.state["platforms"][self.platform].get("session_count_today", 0) + 1
            )
            save_state(self.state_path, self.state)

    def get_random_delay(self):
        """Return a random delay in seconds, weighted toward 60-120s."""
        return random.triangular(30, 300, 90)
```

**Step 4: Run test to verify it passes**

```bash
cd ~/GTM && python3 -m pytest tests/test_runner.py -v
```
Expected: 4 tests PASS

**Step 5: Commit**

```bash
cd ~/GTM && git add gtm/runner.py tests/test_runner.py && git commit -m "feat: add session runner with action rolling, promo checks, and session lifecycle"
```

---

### Task 5: CLI Stats Reporter

**Files:**
- Create: `~/GTM/gtm/stats.py`
- Create: `~/GTM/tests/test_stats.py`

**Step 1: Write the failing tests**

Create `~/GTM/tests/test_stats.py`:

```python
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
        # Seed some data
        sid = create_session(self.db_path, "reddit")
        log_action(self.db_path, sid, "reddit", "like", "https://reddit.com/1")
        log_action(self.db_path, sid, "reddit", "comment", "https://reddit.com/2",
                   content="great post", promoted_product="blocpad")
        log_action(self.db_path, sid, "reddit", "like", "https://reddit.com/3")
        end_session(self.db_path, sid)

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

    def test_alerts_returns_list(self):
        from gtm.state import create_default_state, save_state
        state = create_default_state()
        save_state(self.state_path, state)
        alerts = get_alerts(self.db_path, self.state_path)
        self.assertIsInstance(alerts, list)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

```bash
cd ~/GTM && python3 -m pytest tests/test_stats.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'gtm.stats'`

**Step 3: Write minimal implementation**

Create `~/GTM/gtm/stats.py`:

```python
from datetime import datetime, timedelta

from gtm.db import get_connection
from gtm.state import load_state, PLATFORMS, MAX_SESSIONS_PER_DAY


def weekly_report(db_path):
    conn = get_connection(db_path)
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()

    lines = []
    today = datetime.utcnow().strftime("%b %d")
    week_ago_str = (datetime.utcnow() - timedelta(days=7)).strftime("%b %d")
    lines.append(f"=== GTM Weekly Report ({week_ago_str} - {today}) ===")
    lines.append("")
    header = f"{'Platform':<15} {'Actions':>7}  {'Comments':>8}  {'Promos':>6}  {'Ratio':>7}  {'Sessions':>8}"
    lines.append(header)
    lines.append("-" * len(header))

    total_actions = 0
    total_comments = 0
    total_promos = 0
    total_sessions = 0

    for platform in PLATFORMS:
        row = conn.execute(
            """SELECT
                 COUNT(*) as actions,
                 COALESCE(SUM(CASE WHEN action_type IN ('comment','reply') THEN 1 ELSE 0 END), 0) as comments,
                 COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
               FROM actions
               WHERE platform = ? AND created_at > ?""",
            (platform, week_ago),
        ).fetchone()

        sess = conn.execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE platform = ? AND started_at > ?",
            (platform, week_ago),
        ).fetchone()

        actions = row["actions"]
        comments = row["comments"]
        promos = row["promos"]
        sessions = sess["cnt"]

        ratio_str = f"1:{actions/promos:.1f}" if promos > 0 else "0:0"

        display_name = {
            "reddit": "Reddit",
            "twitter": "Twitter",
            "producthunt": "Product Hunt",
            "indiehackers": "Indie Hackers",
        }.get(platform, platform)

        lines.append(
            f"{display_name:<15} {actions:>7}  {comments:>8}  {promos:>6}  {ratio_str:>7}  {sessions:>8}"
        )

        total_actions += actions
        total_comments += comments
        total_promos += promos
        total_sessions += sessions

    lines.append("-" * len(header))
    total_ratio = f"1:{total_actions/total_promos:.1f}" if total_promos > 0 else "0:0"
    lines.append(
        f"{'TOTAL':<15} {total_actions:>7}  {total_comments:>8}  {total_promos:>6}  {total_ratio:>7}  {total_sessions:>8}"
    )

    # Safety check
    lines.append("")
    safe = all(
        conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) * 1.0 / MAX(COUNT(*), 1)
               FROM actions WHERE platform = ? AND created_at > ?""",
            (p, week_ago),
        ).fetchone()[0] <= 0.1
        for p in PLATFORMS
    )
    lines.append(f"Promotion Safety: {'OK' if safe else 'WARNING - ratio too high'}")

    # Top comments
    lines.append("")
    lines.append("=== Top Performing Comments ===")
    top = conn.execute(
        """SELECT a.platform, a.content_written, o.upvotes, o.replies
           FROM actions a
           JOIN outcomes o ON o.action_id = a.id
           WHERE a.created_at > ? AND a.content_written IS NOT NULL
           ORDER BY o.upvotes + o.replies DESC
           LIMIT 5""",
        (week_ago,),
    ).fetchall()

    if top:
        for i, row in enumerate(top, 1):
            snippet = row["content_written"][:40] + "..." if len(row["content_written"]) > 40 else row["content_written"]
            lines.append(f'{i}. [{row["platform"]}] "{snippet}" - {row["upvotes"]} upvotes, {row["replies"]} replies')
    else:
        lines.append("(no outcome data yet)")

    conn.close()
    return "\n".join(lines)


def get_alerts(db_path, state_path):
    alerts = []
    state = load_state(state_path)
    conn = get_connection(db_path)
    now = datetime.utcnow()

    for platform in PLATFORMS:
        info = state["platforms"].get(platform, {})

        # Session count at max
        if info.get("session_count_today", 0) >= MAX_SESSIONS_PER_DAY:
            display = platform.replace("producthunt", "Product Hunt").replace("indiehackers", "Indie Hackers").title()
            alerts.append(f"{display} session count at max ({MAX_SESSIONS_PER_DAY}/{MAX_SESSIONS_PER_DAY}) - next session tomorrow")

        # No activity in 3+ days
        last = info.get("last_session", "")
        if last:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00")).replace(tzinfo=None)
            gap_days = (now - last_dt).days
            if gap_days >= 3:
                display = platform.replace("producthunt", "Product Hunt").replace("indiehackers", "Indie Hackers").title()
                alerts.append(f"No {display} activity in {gap_days} days - consider a session")

        # Promo ratio warning
        three_days_ago = (now - timedelta(days=3)).isoformat()
        row = conn.execute(
            """SELECT COUNT(*) as total,
                      COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
               FROM actions WHERE platform = ? AND created_at > ?""",
            (platform, three_days_ago),
        ).fetchone()
        if row["total"] > 0:
            ratio = row["promos"] / row["total"]
            if ratio > 0.2:
                alerts.append(f"CRITICAL: {platform} promotion ratio at 1:{1/ratio:.0f} - stop promoting immediately")
            elif ratio > 0.125:
                alerts.append(f"WARNING: {platform} promotion ratio at 1:{1/ratio:.0f} - reduce promotions")

    conn.close()
    return alerts
```

**Step 4: Run test to verify it passes**

```bash
cd ~/GTM && python3 -m pytest tests/test_stats.py -v
```
Expected: 4 tests PASS

**Step 5: Commit**

```bash
cd ~/GTM && git add gtm/stats.py tests/test_stats.py && git commit -m "feat: add CLI stats reporter with weekly summary and alerts"
```

---

### Task 6: CLI Entry Point

**Files:**
- Create: `~/GTM/gtm/cli.py`

**Step 1: Write the CLI entry point**

Create `~/GTM/gtm/cli.py`:

```python
#!/usr/bin/env python3
"""GTM Automation CLI.

Usage:
    python3 -m gtm.cli init          Initialize database and state
    python3 -m gtm.cli status        Show current state (cooldowns, next platform)
    python3 -m gtm.cli stats         Show weekly stats report
    python3 -m gtm.cli alerts        Show active alerts
"""

import argparse
import os
import sys

GTM_DIR = os.path.expanduser("~/GTM")
DB_PATH = os.path.join(GTM_DIR, "gtm.db")
STATE_PATH = os.path.join(GTM_DIR, "state.json")


def cmd_init(args):
    from gtm.db import init_db
    from gtm.state import load_state
    init_db(DB_PATH)
    load_state(STATE_PATH)
    print("Database initialized at", DB_PATH)
    print("State initialized at", STATE_PATH)


def cmd_status(args):
    from gtm.state import load_state, pick_platform
    state = load_state(STATE_PATH)
    print("=== Platform Status ===")
    for name, info in state["platforms"].items():
        print(f"  {name:<15} last: {info['last_session'][:16]}  sessions today: {info['session_count_today']}/{3}  cooldown: {info['cooldown_min']}min")
    next_p = pick_platform(state)
    print()
    if next_p:
        print(f"Next platform: {next_p}")
    else:
        print("All platforms on cooldown. Try again later.")


def cmd_stats(args):
    from gtm.stats import weekly_report
    print(weekly_report(DB_PATH))


def cmd_alerts(args):
    from gtm.stats import get_alerts
    alerts = get_alerts(DB_PATH, STATE_PATH)
    if alerts:
        print("=== Alerts ===")
        for a in alerts:
            print(f"  - {a}")
    else:
        print("No alerts. All good.")


def main():
    parser = argparse.ArgumentParser(description="GTM Automation CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize database and state")
    sub.add_parser("status", help="Show platform status and next pick")
    sub.add_parser("stats", help="Show weekly report")
    sub.add_parser("alerts", help="Show active alerts")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {"init": cmd_init, "status": cmd_status, "stats": cmd_stats, "alerts": cmd_alerts}[args.command](args)


if __name__ == "__main__":
    main()
```

**Step 2: Create `__main__.py` for `python3 -m gtm` support**

Create `~/GTM/gtm/__main__.py`:

```python
from gtm.cli import main
main()
```

**Step 3: Test manually**

```bash
cd ~/GTM && python3 -m gtm init
cd ~/GTM && python3 -m gtm status
cd ~/GTM && python3 -m gtm stats
cd ~/GTM && python3 -m gtm alerts
```

Expected: Each command runs without errors and shows output.

**Step 4: Commit**

```bash
cd ~/GTM && git add gtm/cli.py gtm/__main__.py && git commit -m "feat: add CLI entry point with init, status, stats, alerts commands"
```

---

### Task 7: Update Master CLAUDE.md with Session Workflow Instructions

**Files:**
- Modify: `~/GTM/CLAUDE.md`

**Step 1: Add session workflow section to end of CLAUDE.md**

Append to `~/GTM/CLAUDE.md` (before the Per-Platform Config section):

```markdown
---

## Session Workflow

### How a Session Works
1. Run `python3 -m gtm status` to see which platform is next
2. The runner auto-picks the platform with the longest cooldown gap
3. Search that platform for keyword-matched content
4. For each post: check duplicates, roll action dice, execute via owl
5. Log every action to SQLite (`~/GTM/gtm.db`)
6. Session ends after 15-30 actions or 10-40 minutes (randomized)
7. State updates in `~/GTM/state.json` with cooldown timestamp

### CLI Commands
- `python3 -m gtm init` — Initialize database and state file
- `python3 -m gtm status` — See cooldowns and which platform is next
- `python3 -m gtm stats` — Weekly report with actions, promos, top comments
- `python3 -m gtm alerts` — Check for warnings (high promo ratio, inactivity, etc)

### Files
- `~/GTM/gtm.db` — SQLite database (actions, sessions, outcomes, metrics)
- `~/GTM/state.json` — Platform cooldowns and session counts
```

**Step 2: Commit**

```bash
cd ~/GTM && git add CLAUDE.md && git commit -m "docs: add session workflow and CLI commands to master CLAUDE.md"
```

---

### Task 8: Run Full Test Suite

**Step 1: Run all tests**

```bash
cd ~/GTM && python3 -m pytest tests/ -v
```
Expected: All tests pass (13+ tests across 4 test files)

**Step 2: Run CLI smoke test**

```bash
cd ~/GTM && python3 -m gtm init && python3 -m gtm status && python3 -m gtm stats && python3 -m gtm alerts
```
Expected: All commands produce output without errors.

**Step 3: Final commit if any fixes needed**

```bash
cd ~/GTM && git log --oneline
```
Expected: Clean history of 7 commits.
