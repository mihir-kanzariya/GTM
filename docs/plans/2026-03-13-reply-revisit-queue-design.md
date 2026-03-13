# Reply Revisit Queue — Design Document

**Date:** 2026-03-13
**Status:** Approved
**Goal:** After each session, revisit recent comments via WebFetch to check if anyone replied, and respond via Owl only when a reply is found. Original actions always have full priority.

---

## Problem

Currently, reply tracking enrolls comments and relies on a cron job to check for replies every 15 minutes. This is disconnected from the session flow — checks happen in a separate process, timing is flat (always 15 min), and there's no integration with the runner. Comments posted during a session aren't revisited until the next cron tick, which may never fire if cron isn't set up.

## Solution

A post-session revisit phase that:
1. Runs after `runner.finish()` (original actions always complete first)
2. Gathers all due checks (this session + past 24h)
3. WebFetches each comment URL to detect replies (no Owl for checking)
4. If reply found → Claude replies via Owl
5. If no reply → schedules next check with escalating interval
6. After 3 failed checks → drops the comment

---

## Check Timing (Escalating Intervals)

| Check # | Interval after previous | Total time since comment |
|---------|------------------------|------------------------|
| 1st | 15 min after posting | 15 min |
| 2nd | 15 min after 1st check | 30 min |
| 3rd | 30 min after 2nd check | 60 min |
| After 3rd with no reply | Exhausted (dropped) | — |

If a reply is found at any check → reply back, mark done. No further checks.

---

## Session Flow Integration

```
Step 0: Pre-flight (status, alerts, briefing)
Step 1: runner.start_all()
Step 2: Engagement loop (original actions, full priority)
Step 3: runner.finish()
Step 4: Revisit phase  ← NEW
  │
  ├── get_due_revisits(db_path)  → due checks (this session + past 24h)
  ├── For each:
  │     ├── check_for_replies(platform, comment_url)  → WebFetch only
  │     ├── Reply found?
  │     │     YES → Claude decides to reply (70% chance)
  │     │           If yes → Owl reply, record_action(), mark_replied()
  │     │     NO  → schedule_next_check() with escalating interval
  │     └── 3rd failed check → mark_exhausted()
  │
Step 5: Report (summary + revisit results)
```

---

## Reply Detection by Platform

| Platform | Method | Parse |
|----------|--------|-------|
| Reddit | WebFetch `{comment_url}.json` | JSON `replies.data.children` under our comment |
| Hacker News | WebFetch `https://hacker-news.firebaseio.com/v0/item/{id}.json` | `kids` array on comment item |
| Dev.to | WebFetch `https://dev.to/api/comments/{id}` | `children` array in response |
| Twitter | WebSearch or WebFetch tweet URL | Replies below our tweet |
| Product Hunt | WebFetch discussion page | HTML parsing for new comments |
| Indie Hackers | WebFetch thread page | HTML parsing for new comments |

Reddit, HN, Dev.to have JSON APIs (reliable). Twitter, PH, IH require HTML parsing or WebSearch (best-effort).

---

## New Module: `gtm/revisits.py`

```python
# Check orchestration
def get_due_revisits(db_path) -> list[dict]
def run_revisits(db_path) -> dict  # returns summary of checks/replies/exhausted
def schedule_next_check(db_path, tracking_id) -> None

# Per-platform reply detection (WebFetch, no Owl)
def check_for_replies(platform, comment_url) -> dict | None
def parse_reddit_replies(json_data, comment_url) -> dict | None
def parse_hn_replies(json_data) -> dict | None
def parse_devto_replies(json_data) -> dict | None
```

---

## Changes to Existing Code

| File | Change |
|------|--------|
| `gtm/engagement.py` | `enroll_for_tracking()` — escalating intervals (15→15→30) instead of flat 15 min |
| `gtm/runner.py` | `InterleavedRunner.finish()` — return revisit results; add `revisit_results` attribute |
| `gtm/cli.py` | `tracking` command — show next check times and escalation state |

**No new tables.** Uses existing `reply_tracking` table (already has `checks_done`, `max_checks`, `next_check_at`, `status`).

---

## Revisit Report Format

After the revisit phase, Claude sees:

```
Revisit Results:
  Checked: 6 comments
  Replies found: 2
  - twitter: @dev_guru replied "totally agree, we use MCP too" → replied back
  - reddit: u/webdev_fan replied "how does it compare to X?" → replied back
  Replied: 2
  No reply yet: 3 (next check scheduled)
  Exhausted: 1 (dropped after 3 checks)
```
