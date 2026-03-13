# GTM Session Workflow & Logging — Design Document

**Date**: 2026-03-05
**Status**: Approved

## Overview
Two interconnected systems for the GTM automation: (1) a state-machine session runner that auto-rotates across platforms with cooldown management, and (2) a SQLite-based logging and analytics system with CLI reporting and outcome tracking.

---

## Part 1: Session Workflow / Runner

### Session Lifecycle

```
1. INIT        → Read state.json, pick platform (longest cooldown gap)
2. DISCOVER    → Search platform for keyword-matched content (New/Rising/Hot)
3. EVALUATE    → Score each post for relevance, promotion opportunity, engagement value
4. DECIDE      → Roll action-mix dice (like/comment/skip/etc per master weights)
5. EXECUTE     → Owl plugin performs the action (with human mimicry delays)
6. LOG         → Write action to SQLite, update state.json
7. LOOP        → Repeat steps 3-6 for next post (until session limit hit)
8. COOLDOWN    → Record session end time, set platform cooldown
```

### State File: `~/GTM/state.json`

```json
{
  "platforms": {
    "reddit":       { "last_session": "2026-03-05T14:30:00Z", "cooldown_min": 180, "session_count_today": 1 },
    "twitter":      { "last_session": "2026-03-05T10:15:00Z", "cooldown_min": 120, "session_count_today": 2 },
    "producthunt":  { "last_session": "2026-03-04T18:00:00Z", "cooldown_min": 240, "session_count_today": 0 },
    "indiehackers": { "last_session": "2026-03-04T09:00:00Z", "cooldown_min": 180, "session_count_today": 0 }
  },
  "daily_reset": "2026-03-05"
}
```

### Platform Selection Logic
1. Check if `daily_reset` is today. If not, reset all `session_count_today` to 0.
2. Filter platforms where `now - last_session > cooldown_min` AND `session_count_today < 3`.
3. From qualifying platforms, pick the one with the longest gap since last session.
4. If none qualify, report "All platforms on cooldown" and stop.

### Session Limits (randomized per run)
- Actions per session: random between 15-30
- Session duration: random between 10-40 minutes
- Whichever limit is hit first ends the session

### Content Discovery Flow
1. Read keywords from `~/GTM/CLAUDE.md`
2. Search the selected platform using keywords
3. Sort by New/Rising for engagement opportunity, Hot for visibility
4. Filter out already-engaged URLs (check SQLite `actions` table, last 7 days)
5. Score remaining posts for relevance and engagement potential

### Action Decision Flow
1. Roll against action-mix weights from master CLAUDE.md
2. If "comment/reply" selected, check promotion ratio (1:10 max)
3. If promotion eligible AND post is genuinely relevant to Blocpad/Blocfeed, include natural mention
4. If promotion not eligible or not relevant, write pure-value comment
5. Apply human writing style rules from master CLAUDE.md
6. Apply platform-specific character limits and tone

### Human Mimicry During Execution
- Random delay between actions: 30s to 5min (weighted toward 1-2 min)
- Simulate scrolling and cursor movement via owl before each action
- Vary reading time based on content length (short post = 5-15s, long post = 20-60s)
- Occasionally scroll past content without interacting (part of "skip" action)
- Don't click directly on targets — scroll to them naturally

---

## Part 2: SQLite Database

### Database: `~/GTM/gtm.db`

#### Table: `sessions`
```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    total_actions INTEGER DEFAULT 0,
    promoted_count INTEGER DEFAULT 0
);
```

#### Table: `actions`
```sql
CREATE TABLE actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    platform TEXT NOT NULL,
    action_type TEXT NOT NULL,  -- like/upvote/comment/reply/retweet/quote/skip/save/follow/bookmark
    target_url TEXT,
    target_title TEXT,
    content_written TEXT,       -- NULL for likes/saves/skips
    promoted_product TEXT,      -- blocpad/blocfeed/NULL
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    keywords_matched TEXT       -- comma-separated keywords that led to discovery
);
```

#### Table: `outcomes`
```sql
CREATE TABLE outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id INTEGER NOT NULL REFERENCES actions(id),
    checked_at DATETIME NOT NULL DEFAULT (datetime('now')),
    upvotes INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    views INTEGER               -- NULL if not available
);
```

#### Table: `daily_metrics`
```sql
CREATE TABLE daily_metrics (
    date DATE NOT NULL,
    platform TEXT NOT NULL,
    total_actions INTEGER DEFAULT 0,
    comments_written INTEGER DEFAULT 0,
    promotions INTEGER DEFAULT 0,
    promotion_ratio REAL DEFAULT 0.0,
    PRIMARY KEY (date, platform)
);
```

### Duplicate Prevention
Before engaging with any post:
```sql
SELECT id FROM actions WHERE target_url = ? AND created_at > datetime('now', '-7 days');
```
If any rows returned, skip that post.

---

## Part 3: CLI Stats Reporter

### Weekly Summary Command

Output format:
```
=== GTM Weekly Report (Feb 27 - Mar 05) ===

Platform       Actions  Comments  Promotions  Ratio    Sessions
-------------- -------  --------  ----------  -------  --------
Reddit              45       18           2   1:22.5        6
Twitter             62       24           3   1:20.7        8
Product Hunt        15        8           1   1:15.0        3
Indie Hackers       22       12           2   1:11.0        4
-------------- -------  --------  ----------  -------  --------
TOTAL              144       62           8   1:18.0       21

Promotion Safety: OK (under 1:10 threshold on all platforms)

=== Top Performing Comments ===
1. [Reddit r/SaaS] "honestly we had the same..." - 23 upvotes, 4 replies
2. [Twitter] "tbh the biggest thing..." - 15 likes, 2 replies
3. [IH] "when we launched we..." - 8 upvotes, 3 replies

=== Alerts ===
- Reddit session count high today (3/3) - next session tomorrow
- No Product Hunt activity in 2 days - consider a session
```

### Outcome Checking Phase
Runs independently (once daily, or on-demand):
1. Query actions from past 48h where no outcome record exists
2. Visit each `target_url` via owl plugin
3. Find our comment/reply and record current upvotes/replies
4. Insert into `outcomes` table

### Alert Triggers
- Promotion ratio exceeds 1:8 on any platform (warning)
- Promotion ratio exceeds 1:5 on any platform (critical - stop promoting)
- No activity on a platform for 3+ days
- Session count at daily max (3)
- A comment received negative engagement (downvotes, flagged)

---

## File Structure Update

```
~/GTM/
├── CLAUDE.md
├── state.json              # Session state and cooldowns
├── gtm.db                  # SQLite database
├── docs/plans/             # Design documents
├── reddit/CLAUDE.md
├── twitter/CLAUDE.md
├── producthunt/CLAUDE.md
└── indiehackers/CLAUDE.md
```

## Next Steps
- Implement state.json initialization and platform selection logic
- Create SQLite database with schema
- Add session workflow instructions to master CLAUDE.md
- Build CLI stats query (can be done as SQL queries Claude runs directly)
- Integrate owl plugin for action execution and outcome checking
