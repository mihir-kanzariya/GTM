# Reply Revisit Queue — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** After each session, revisit recent comments via WebFetch to check for replies and respond. Original actions always complete first.

**Architecture:** New `gtm/revisits.py` module with per-platform reply detection parsers and an orchestrator function. Modifies `gtm/engagement.py` for escalating check intervals, `gtm/runner.py` to hook revisits into `finish()`, and `gtm/cli.py` for better tracking display.

**Tech Stack:** Python 3, SQLite, existing gtm package. Uses WebFetch for checking (not Owl).

**Design doc:** `docs/plans/2026-03-13-reply-revisit-queue-design.md`

---

## Task 1: Escalating check intervals in `gtm/engagement.py`

Change `enroll_for_tracking()` and `record_check()` to use escalating intervals (15→15→30 min) instead of flat 15 min.

**Files:**
- Modify: `gtm/engagement.py`
- Test: `tests/test_revisits.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_revisits.py`:

```python
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from gtm.db import init_db, get_connection
from gtm.engagement import enroll_for_tracking, record_check, get_due_checks


class TestEscalatingIntervals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)
        # Create a session and action to reference
        from gtm.db import create_session, log_action
        self.session_id = create_session(self.db_path, "twitter")
        self.action_id = log_action(
            self.db_path, self.session_id, "twitter", "comment",
            "https://x.com/post/1", content="test comment",
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_check_scheduled_15_min(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        next_check = datetime.fromisoformat(row["next_check_at"])
        now = datetime.utcnow()
        diff = (next_check - now).total_seconds() / 60
        self.assertGreater(diff, 13)  # ~15 min, allow 2 min tolerance
        self.assertLess(diff, 17)

    def test_second_check_scheduled_15_min(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        record_check(self.db_path, tid, replies=0)  # 1st check, no reply
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["checks_done"], 1)
        next_check = datetime.fromisoformat(row["next_check_at"])
        last_check = datetime.fromisoformat(row["last_checked_at"])
        diff = (next_check - last_check).total_seconds() / 60
        self.assertGreater(diff, 13)
        self.assertLess(diff, 17)

    def test_third_check_scheduled_30_min(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        record_check(self.db_path, tid, replies=0)  # 1st check
        record_check(self.db_path, tid, replies=0)  # 2nd check
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["checks_done"], 2)
        next_check = datetime.fromisoformat(row["next_check_at"])
        last_check = datetime.fromisoformat(row["last_checked_at"])
        diff = (next_check - last_check).total_seconds() / 60
        self.assertGreater(diff, 28)
        self.assertLess(diff, 32)

    def test_exhausted_after_3_checks(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        record_check(self.db_path, tid, replies=0)
        record_check(self.db_path, tid, replies=0)
        record_check(self.db_path, tid, replies=0)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        self.assertEqual(row["status"], "exhausted")
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_revisits.py -v`
Expected: FAIL — `test_third_check_scheduled_30_min` fails because `record_check` uses flat 15 min

**Step 3: Modify `gtm/engagement.py`**

Add escalating interval helper and update `record_check`:

```python
# Add at top of file, after REPLY_PROBABILITY
CHECK_INTERVALS = [15, 15, 30]  # minutes: 1st, 2nd, 3rd check


def _get_check_interval(checks_done):
    """Return interval in minutes for the next check based on how many checks done."""
    if checks_done < len(CHECK_INTERVALS):
        return CHECK_INTERVALS[checks_done]
    return CHECK_INTERVALS[-1]
```

In `record_check()`, change line 49 from:
```python
next_check = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
```
to:
```python
next_interval = _get_check_interval(new_checks)
next_check = (datetime.utcnow() + timedelta(minutes=next_interval)).isoformat()
```

Note: `new_checks` is computed on line 55 as `row["checks_done"] + 1`, so move the `next_check` computation AFTER `new_checks` is calculated. The updated `record_check` function:

```python
def record_check(db_path, tracking_id, upvotes=0, replies=0,
                 reply_content=None, reply_author=None):
    now = datetime.utcnow().isoformat()
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM reply_tracking WHERE id = ?", (tracking_id,)
        ).fetchone()
        new_checks = row["checks_done"] + 1
        check_number = new_checks

        # Escalating interval
        next_interval = _get_check_interval(new_checks)
        next_check = (datetime.utcnow() + timedelta(minutes=next_interval)).isoformat()

        conn.execute(
            """INSERT INTO outcomes
               (action_id, check_number, upvotes, replies, reply_content, reply_author)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (row["action_id"], check_number, upvotes, replies, reply_content, reply_author),
        )

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
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_revisits.py -v`
Expected: All 4 tests PASS

**Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add gtm/engagement.py tests/test_revisits.py
git commit -m "feat: add escalating check intervals (15→15→30 min) for reply tracking"
```

---

## Task 2: Per-platform reply parsers (`gtm/revisits.py`)

Create functions that parse WebFetch responses to detect replies to our comments.

**Files:**
- Create: `gtm/revisits.py`
- Test: `tests/test_revisits.py` (extend)

**Step 1: Write the failing tests**

Add to `tests/test_revisits.py`:

```python
from gtm.revisits import (
    parse_reddit_comment_replies, parse_hn_comment_replies, parse_devto_comment_replies,
)


class TestReplyParsers(unittest.TestCase):

    def test_parse_reddit_reply_found(self):
        # Reddit comment JSON: our comment has replies
        mock_data = [
            {"kind": "Listing", "data": {"children": [{"kind": "t3", "data": {"title": "Post"}}]}},
            {"kind": "Listing", "data": {"children": [
                {"kind": "t1", "data": {
                    "author": "us",
                    "body": "our comment",
                    "replies": {"kind": "Listing", "data": {"children": [
                        {"kind": "t1", "data": {
                            "author": "replier1",
                            "body": "I agree with this take",
                            "created_utc": 1710000000,
                        }},
                    ]}},
                }},
            ]}},
        ]
        result = parse_reddit_comment_replies(mock_data, "us")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["author"], "replier1")
        self.assertEqual(result[0]["content"], "I agree with this take")

    def test_parse_reddit_no_replies(self):
        mock_data = [
            {"kind": "Listing", "data": {"children": [{"kind": "t3", "data": {"title": "Post"}}]}},
            {"kind": "Listing", "data": {"children": [
                {"kind": "t1", "data": {
                    "author": "us",
                    "body": "our comment",
                    "replies": "",
                }},
            ]}},
        ]
        result = parse_reddit_comment_replies(mock_data, "us")
        self.assertEqual(len(result), 0)

    def test_parse_hn_reply_found(self):
        # HN item with kids (replies)
        mock_item = {"id": 123, "by": "us", "text": "our comment", "kids": [456, 789]}
        mock_kids = [
            {"id": 456, "by": "replier1", "text": "Nice point!", "time": 1710000000},
            {"id": 789, "by": "replier2", "text": "Disagree tbh", "time": 1710000100},
        ]
        result = parse_hn_comment_replies(mock_item, mock_kids)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["author"], "replier1")

    def test_parse_hn_no_replies(self):
        mock_item = {"id": 123, "by": "us", "text": "our comment"}
        result = parse_hn_comment_replies(mock_item, [])
        self.assertEqual(len(result), 0)

    def test_parse_devto_reply_found(self):
        mock_comment = {
            "id_code": "abc123",
            "body_html": "our comment",
            "children": [
                {"id_code": "def456", "user": {"username": "replier1"},
                 "body_html": "Good article!", "created_at": "2026-03-13T10:00:00Z"},
            ],
        }
        result = parse_devto_comment_replies(mock_comment)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["author"], "replier1")

    def test_parse_devto_no_replies(self):
        mock_comment = {"id_code": "abc123", "body_html": "our comment", "children": []}
        result = parse_devto_comment_replies(mock_comment)
        self.assertEqual(len(result), 0)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_revisits.py::TestReplyParsers -v`
Expected: FAIL — module doesn't exist

**Step 3: Create `gtm/revisits.py`**

```python
"""Reply revisit system — check if anyone replied to our comments via WebFetch.

Per-platform parsers detect replies in API/page responses.
The orchestrator (run_revisits) gathers due checks and processes them.
"""


def parse_reddit_comment_replies(json_data, our_username):
    """Parse Reddit comment JSON to find replies to our comment.

    Args:
        json_data: Response from WebFetch "{comment_permalink}.json"
                   This is a list of two Listings: [post, comments_tree]
        our_username: Our Reddit username to identify our comment

    Returns:
        List of reply dicts: [{"author": str, "content": str}]
    """
    replies = []
    if not json_data or len(json_data) < 2:
        return replies

    comments_listing = json_data[1]
    children = comments_listing.get("data", {}).get("children", [])

    for child in children:
        comment = child.get("data", {})
        if comment.get("author", "").lower() == our_username.lower():
            # Found our comment, check its replies
            reply_data = comment.get("replies")
            if not reply_data or isinstance(reply_data, str):
                continue
            reply_children = reply_data.get("data", {}).get("children", [])
            for rc in reply_children:
                rd = rc.get("data", {})
                if rd.get("author") and rd.get("body"):
                    replies.append({
                        "author": rd["author"],
                        "content": rd["body"],
                    })
    return replies


def parse_hn_comment_replies(our_comment, kid_items):
    """Parse HN comment replies.

    Args:
        our_comment: Our comment item from HN API (has "kids" list of IDs)
        kid_items: List of fetched kid item dicts (already resolved from IDs)

    Returns:
        List of reply dicts: [{"author": str, "content": str}]
    """
    replies = []
    for kid in kid_items:
        if kid.get("by") and kid.get("text"):
            replies.append({
                "author": kid["by"],
                "content": kid["text"],
            })
    return replies


def parse_devto_comment_replies(comment_data):
    """Parse Dev.to comment replies.

    Args:
        comment_data: Response from WebFetch "https://dev.to/api/comments/{id}"
                      Has "children" array with reply comments

    Returns:
        List of reply dicts: [{"author": str, "content": str}]
    """
    replies = []
    children = comment_data.get("children", [])
    for child in children:
        user = child.get("user", {})
        if user.get("username") and child.get("body_html"):
            replies.append({
                "author": user["username"],
                "content": child["body_html"],
            })
    return replies
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_revisits.py::TestReplyParsers -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add gtm/revisits.py tests/test_revisits.py
git commit -m "feat: add per-platform reply parsers (Reddit, HN, Dev.to)"
```

---

## Task 3: Revisit orchestrator (`gtm/revisits.py` extension)

Add `get_due_revisits()`, `schedule_next_check()`, and `run_revisits()` — the orchestrator that gathers due checks and returns results for Claude to act on.

**Files:**
- Modify: `gtm/revisits.py`
- Test: `tests/test_revisits.py` (extend)

**Step 1: Write the failing tests**

Add to `tests/test_revisits.py`:

```python
from gtm.revisits import get_due_revisits, schedule_next_check, run_revisits
from gtm.engagement import enroll_for_tracking


class TestRevisitOrchestrator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)
        from gtm.db import create_session, log_action
        self.session_id = create_session(self.db_path, "twitter")
        self.action_id = log_action(
            self.db_path, self.session_id, "twitter", "comment",
            "https://x.com/post/1", content="test comment",
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_due_revisits_returns_due_entries(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        # Force next_check_at to past so it's due
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE reply_tracking SET next_check_at = datetime('now', '-1 minute') WHERE id = ?",
            (tid,),
        )
        conn.commit()
        conn.close()
        due = get_due_revisits(self.db_path)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["platform"], "twitter")

    def test_get_due_revisits_excludes_old(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        # Set created_at to 3 days ago (outside 24h window)
        conn = get_connection(self.db_path)
        conn.execute(
            """UPDATE reply_tracking
               SET next_check_at = datetime('now', '-1 minute'),
                   created_at = datetime('now', '-3 days')
               WHERE id = ?""",
            (tid,),
        )
        conn.commit()
        conn.close()
        due = get_due_revisits(self.db_path)
        self.assertEqual(len(due), 0)

    def test_schedule_next_check_escalates(self):
        tid = enroll_for_tracking(self.db_path, self.action_id, "twitter",
                                  "https://x.com/post/1", "https://x.com/reply/1")
        # Simulate 2 checks done
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE reply_tracking SET checks_done = 2 WHERE id = ?", (tid,)
        )
        conn.commit()
        conn.close()
        schedule_next_check(self.db_path, tid)
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM reply_tracking WHERE id = ?", (tid,)).fetchone()
        conn.close()
        next_check = datetime.fromisoformat(row["next_check_at"])
        now = datetime.utcnow()
        diff = (next_check - now).total_seconds() / 60
        self.assertGreater(diff, 28)  # 30 min interval for 3rd check
        self.assertLess(diff, 32)

    def test_run_revisits_returns_summary(self):
        result = run_revisits(self.db_path)
        self.assertIn("checked", result)
        self.assertIn("replies_found", result)
        self.assertIn("no_reply", result)
        self.assertIn("exhausted", result)
        self.assertIn("needs_reply", result)

    def test_run_revisits_empty_when_nothing_due(self):
        result = run_revisits(self.db_path)
        self.assertEqual(result["checked"], 0)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_revisits.py::TestRevisitOrchestrator -v`
Expected: FAIL — functions not defined

**Step 3: Add orchestrator functions to `gtm/revisits.py`**

Append to the end of `gtm/revisits.py`:

```python
from datetime import datetime, timedelta

from gtm.db import get_connection
from gtm.engagement import record_check, mark_exhausted, _get_check_interval


def get_due_revisits(db_path, hours=24):
    """Get all reply tracking entries that are due for checking within the last N hours.

    Returns entries where:
    - status = 'active'
    - next_check_at <= now
    - created_at within last N hours (default 24h)
    """
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM reply_tracking
               WHERE status = 'active'
               AND next_check_at <= datetime('now')
               AND checks_done < max_checks
               AND created_at > ?
               ORDER BY next_check_at""",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def schedule_next_check(db_path, tracking_id):
    """Schedule the next check with escalating interval based on checks_done."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT checks_done FROM reply_tracking WHERE id = ?", (tracking_id,)
        ).fetchone()
        if not row:
            return
        next_interval = _get_check_interval(row["checks_done"])
        next_check = (datetime.utcnow() + timedelta(minutes=next_interval)).isoformat()
        conn.execute(
            "UPDATE reply_tracking SET next_check_at = ? WHERE id = ?",
            (next_check, tracking_id),
        )
        conn.commit()
    finally:
        conn.close()


def run_revisits(db_path, hours=24):
    """Orchestrate the revisit phase. Gather due checks and return results.

    This function does NOT perform WebFetch or Owl — it returns a structured
    result that tells Claude what needs checking and what was found.

    Returns:
        dict with keys:
        - checked: int (total entries processed)
        - replies_found: int
        - no_reply: int
        - exhausted: int
        - needs_reply: list of dicts with reply details for Claude to act on
        - pending: list of dicts scheduled for later
    """
    due = get_due_revisits(db_path, hours)

    result = {
        "checked": len(due),
        "replies_found": 0,
        "no_reply": 0,
        "exhausted": 0,
        "needs_reply": [],
        "pending": [],
    }

    # Return the due entries for Claude to process via WebFetch
    # Claude will call check_for_replies() for each, then update accordingly
    for entry in due:
        result["pending"].append({
            "tracking_id": entry["id"],
            "platform": entry["platform"],
            "target_url": entry["target_url"],
            "comment_url": entry["comment_url"],
            "checks_done": entry["checks_done"],
        })

    return result
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_revisits.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add gtm/revisits.py tests/test_revisits.py
git commit -m "feat: add revisit orchestrator — due checks, scheduling, run_revisits"
```

---

## Task 4: Hook revisits into `InterleavedRunner.finish()`

Wire the revisit phase into the session end flow.

**Files:**
- Modify: `gtm/runner.py`
- Test: `tests/test_revisits.py` (extend)

**Step 1: Write the failing test**

Add to `tests/test_revisits.py`:

```python
from gtm.runner import InterleavedRunner


class TestRunnerRevisitIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.state_path = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finish_returns_revisit_results(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.finish()
        self.assertIsNotNone(runner.revisit_results)
        self.assertIn("checked", runner.revisit_results)
        self.assertIn("needs_reply", runner.revisit_results)

    def test_finish_includes_due_revisits(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        # Post a comment
        runner.record_action("twitter", "comment", "https://x.com/post/1",
                             content="great post", comment_url="https://x.com/reply/1")
        # Force the tracking entry to be due now
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE reply_tracking SET next_check_at = datetime('now', '-1 minute')"
        )
        conn.commit()
        conn.close()
        runner.finish()
        self.assertGreater(len(runner.revisit_results["pending"]), 0)

    def test_summary_includes_revisit_count(self):
        runner = InterleavedRunner(self.db_path, self.state_path)
        runner.start_all()
        runner.finish()
        s = runner.summary()
        self.assertIn("revisits", s)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_revisits.py::TestRunnerRevisitIntegration -v`
Expected: FAIL — `revisit_results` attribute doesn't exist

**Step 3: Modify `gtm/runner.py`**

In `InterleavedRunner.__init__()`, add after `self.briefing = None`:
```python
self.revisit_results = None
```

In `InterleavedRunner.finish()`, add AFTER the intelligence updates block and BEFORE `save_state`:
```python
# Post-session revisit check
try:
    from gtm.revisits import run_revisits
    self.revisit_results = run_revisits(self.db_path)
except Exception:
    self.revisit_results = {"checked": 0, "replies_found": 0, "no_reply": 0,
                            "exhausted": 0, "needs_reply": [], "pending": []}
```

In `InterleavedRunner.summary()`, add to the returned dict:
```python
"revisits": self.revisit_results or {"checked": 0, "pending": []},
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_revisits.py -v`
Expected: All tests PASS

**Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add gtm/runner.py tests/test_revisits.py
git commit -m "feat: hook revisit phase into runner.finish() — returns due checks for Claude"
```

---

## Task 5: Update CLI tracking command

Improve the `tracking` command to show check status, next check times, and escalation state.

**Files:**
- Modify: `gtm/cli.py`

**Step 1: Update `cmd_tracking` in `gtm/cli.py`**

Replace the existing `cmd_tracking` function:

```python
def cmd_tracking(args):
    from gtm.engagement import get_active_tracking_count
    from gtm.db import get_connection
    from datetime import datetime

    count = get_active_tracking_count(DB_PATH)
    print("=== Reply Tracking ===")
    print(f"  Active trackers: {count}")

    conn = get_connection(DB_PATH)

    # Per-platform breakdown
    rows = conn.execute(
        "SELECT platform, COUNT(*) as cnt FROM reply_tracking WHERE status = 'active' GROUP BY platform"
    ).fetchall()
    if rows:
        print()
        for r in rows:
            print(f"    {r['platform']}: {r['cnt']}")

    # Show upcoming checks
    upcoming = conn.execute(
        """SELECT platform, comment_url, checks_done, max_checks, next_check_at
           FROM reply_tracking WHERE status = 'active'
           ORDER BY next_check_at LIMIT 10"""
    ).fetchall()
    if upcoming:
        print(f"\n  Upcoming checks:")
        now = datetime.utcnow()
        for u in upcoming:
            next_at = datetime.fromisoformat(u["next_check_at"])
            diff = (next_at - now).total_seconds() / 60
            if diff < 0:
                time_str = "OVERDUE"
            elif diff < 60:
                time_str = f"in {int(diff)}m"
            else:
                time_str = f"in {int(diff/60)}h {int(diff%60)}m"
            url = (u["comment_url"] or u["platform"])[:50]
            print(f"    [{u['checks_done']}/{u['max_checks']}] {u['platform']}: {url} — {time_str}")

    # Show recent results
    recent = conn.execute(
        """SELECT platform, status, comment_url, checks_done
           FROM reply_tracking
           WHERE status IN ('replied', 'exhausted')
           ORDER BY last_checked_at DESC LIMIT 5"""
    ).fetchall()
    if recent:
        print(f"\n  Recent results:")
        for r in recent:
            status_icon = "replied" if r["status"] == "replied" else "no reply"
            url = (r["comment_url"] or r["platform"])[:50]
            print(f"    [{status_icon}] {r['platform']}: {url} ({r['checks_done']} checks)")

    conn.close()
```

**Step 2: Test manually**

```bash
python3 -m gtm tracking
```

**Step 3: Commit**

```bash
git add gtm/cli.py
git commit -m "feat: improve tracking CLI — show upcoming checks, escalation state, recent results"
```

---

## Task 6: Update docs and guide

Add revisit phase documentation.

**Files:**
- Modify: `docs/gtm-python-guide.md`
- Modify: `CLAUDE.md`

**Step 1: Add revisits section to `docs/gtm-python-guide.md`**

Add after the "Reply Tracking & Engagement" section:

```markdown
## Reply Revisits (Post-Session)

```python
# Use at: after runner.finish() to check for replies to your comments
# runner.finish() calls run_revisits() automatically

from gtm.revisits import (
    get_due_revisits, run_revisits, schedule_next_check,
    parse_reddit_comment_replies, parse_hn_comment_replies, parse_devto_comment_replies,
)

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# After runner.finish(), check what needs revisiting
result = runner.revisit_results
# Returns: {
#   "checked": 6,
#   "replies_found": 0,
#   "no_reply": 0,
#   "exhausted": 0,
#   "needs_reply": [],
#   "pending": [
#     {"tracking_id": 1, "platform": "twitter", "target_url": "...", "comment_url": "...", "checks_done": 0},
#   ],
# }

# For each pending entry, Claude does:
# 1. WebFetch the comment_url or target_url
# 2. Parse with the right parser:
#    Reddit:  parse_reddit_comment_replies(json_data, "our_username")
#    HN:      parse_hn_comment_replies(our_item, kid_items)
#    Dev.to:  parse_devto_comment_replies(comment_json)
# 3. If replies found → reply via Owl, then mark_replied()
# 4. If no replies → schedule_next_check() (escalates 15→15→30 min)
# 5. After 3 failed checks → mark_exhausted()

# Check intervals: 1st=15min, 2nd=15min, 3rd=30min, then exhausted
```
```

**Step 2: Add to CLAUDE.md**

Add after the Intelligence Engine "Phase 4: Post-Session" section:

```markdown
### Phase 5: Reply Revisits (automatic after finish)

After `runner.finish()`, check `runner.revisit_results` for pending revisits:

```python
# runner.finish() auto-populates runner.revisit_results
for entry in runner.revisit_results["pending"]:
    # WebFetch the comment URL to check for replies
    # Parse with platform-specific parser from gtm.revisits
    # If reply found → Owl to reply back, mark_replied()
    # If no reply → schedule_next_check() (15→15→30 min escalation)
    pass
```

Check intervals: 15 min → 15 min → 30 min → exhausted (dropped).
Only comments from the last 24 hours are revisited.
```

**Step 3: Commit**

```bash
git add docs/gtm-python-guide.md CLAUDE.md
git commit -m "docs: add reply revisit queue usage to guide and CLAUDE.md"
```

---

## Summary

| Task | What it builds | Files |
|------|---------------|-------|
| 1 | Escalating check intervals (15→15→30) | `gtm/engagement.py`, `tests/test_revisits.py` |
| 2 | Per-platform reply parsers | `gtm/revisits.py`, `tests/test_revisits.py` |
| 3 | Revisit orchestrator (due checks, scheduling) | `gtm/revisits.py`, `tests/test_revisits.py` |
| 4 | Runner integration (finish → revisits) | `gtm/runner.py`, `tests/test_revisits.py` |
| 5 | CLI tracking improvements | `gtm/cli.py` |
| 6 | Documentation updates | `docs/gtm-python-guide.md`, `CLAUDE.md` |

Total: 1 new file, 4 modified files, 6 commits.
