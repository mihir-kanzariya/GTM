# GTM v2 Scaling Design

**Date:** 2026-03-09
**Status:** Approved
**Approach:** Modular Services (Approach 2)

---

## Summary

Scale the GTM automation from basic like/comment actions to a full engagement system with:
- Reply tracking with auto-follow-up (cron-based, 15min intervals, max 3 checks)
- Twitter thread creation (building-in-public + general founder content)
- Smart keyword rotation (explore/exploit scoring)
- Engagement scoring (measure ROI per action)
- Relationship tracking (build genuine connections across sessions)
- Content calendar (weekly planning)
- Peak time targeting (learn best hours per platform)
- Decision logging (full context recovery after session compaction)

All features designed together so the DB schema accounts for everything upfront. Implementation will be incremental.

---

## Decisions

- **Thread tweets:** Building-in-public + general founder content, mixed randomly
- **Reply behavior:** 70% reply / 30% let it go (more human-like)
- **Tracking scope:** ALL comments across all platforms get 3 checks at 15min intervals
- **Architecture:** Modular services — separate modules per feature domain, shared DB, runner orchestrates
- **All scaling features included:** smart keywords, content calendar, engagement scoring, relationship tracking, peak times
- **Shipped as:** One holistic design, implemented incrementally
- **Twitter URL:** https://x.com (not twitter.com)

---

## Database Schema

### Existing tables (unchanged)
- `sessions` — session tracking (id, platform, started_at, ended_at, total_actions, promoted_count)
- `actions` — every action logged (session_id, platform, action_type, target_url, target_title, content_written, promoted_product, keywords_matched)
- `daily_metrics` — aggregated daily stats per platform

### Modified table: `outcomes`

Currently exists but never populated. Redesigned:

```sql
CREATE TABLE IF NOT EXISTS outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id       INTEGER REFERENCES actions(id),
    check_number    INTEGER,
    checked_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    upvotes         INTEGER DEFAULT 0,
    replies         INTEGER DEFAULT 0,
    reply_content   TEXT,
    reply_author    TEXT,
    views           INTEGER,
    our_reply_id    INTEGER REFERENCES actions(id)
);
```

### New table: `reply_tracking`

```sql
CREATE TABLE IF NOT EXISTS reply_tracking (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id       INTEGER REFERENCES actions(id) UNIQUE,
    platform        TEXT,
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
```

Status values: `active` | `replied` | `exhausted` | `expired`

### New table: `threads`

```sql
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
```

- `thread_type`: 'building_in_public' | 'general_founder'
- `content`: JSON array of tweet texts
- `engagement`: JSON {likes, retweets, replies} updated on checks

### New table: `keyword_performance`

```sql
CREATE TABLE IF NOT EXISTS keyword_performance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         TEXT,
    platform        TEXT,
    times_used      INTEGER DEFAULT 0,
    posts_found     INTEGER DEFAULT 0,
    comments_made   INTEGER DEFAULT 0,
    replies_received INTEGER DEFAULT 0,
    avg_upvotes     REAL DEFAULT 0,
    last_used_at    DATETIME,
    score           REAL DEFAULT 0,
    UNIQUE(keyword, platform)
);
```

Score formula: `(replies_received * 3) + (avg_upvotes * 1) + (comments_made * 0.5) + recency_bonus`

### New table: `relationships`

```sql
CREATE TABLE IF NOT EXISTS relationships (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT,
    username        TEXT,
    display_name    TEXT,
    first_seen_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_interacted DATETIME,
    interaction_count INTEGER DEFAULT 1,
    interactions    TEXT,
    notes           TEXT,
    relationship_score REAL DEFAULT 0,
    UNIQUE(platform, username)
);
```

- `interactions`: JSON array [{action_id, type, date}]
- `relationship_score`: `interaction_count * 2 + (they_replied * 5)`

### New table: `content_calendar`

```sql
CREATE TABLE IF NOT EXISTS content_calendar (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT,
    content_type    TEXT,
    topic           TEXT,
    outline         TEXT,
    scheduled_for   DATE,
    status          TEXT DEFAULT 'planned',
    action_id       INTEGER REFERENCES actions(id),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

- `content_type`: 'thread' | 'article' | 'post' | 'tweet'
- `status`: 'planned' | 'posted' | 'skipped'

### New table: `peak_times`

```sql
CREATE TABLE IF NOT EXISTS peak_times (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT,
    day_of_week     INTEGER,
    hour            INTEGER,
    actions_taken   INTEGER DEFAULT 0,
    avg_replies     REAL DEFAULT 0,
    avg_upvotes     REAL DEFAULT 0,
    engagement_score REAL DEFAULT 0,
    sample_count    INTEGER DEFAULT 0,
    UNIQUE(platform, day_of_week, hour)
);
```

### New table: `decision_log`

```sql
CREATE TABLE IF NOT EXISTS decision_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
    category        TEXT,
    platform        TEXT,
    decision        TEXT,
    reasoning       TEXT,
    context         TEXT,
    session_id      TEXT REFERENCES sessions(id),
    outcome         TEXT
);
```

- `category`: 'design' | 'engagement' | 'promotion' | 'reply' | 'content' | 'keyword' | 'calendar'
- `context`: JSON with any relevant data (action_ids, URLs, scores)

---

## Module Architecture

```
gtm/
├── db.py              # Extended with new table creation + queries
├── runner.py          # InterleavedRunner (slim, delegates to modules)
├── state.py           # Unchanged
├── stats.py           # Extended with new metrics
├── cli.py             # Extended with new commands
├── engagement.py      # Reply tracking, follow-up logic, outcome checking
├── threads.py         # Twitter thread creation + templates
├── analytics.py       # Keyword scoring, peak times, engagement scoring
├── relationships.py   # User tracking across sessions
├── calendar.py        # Content calendar management
├── cron.py            # Cron job management (wraps CronCreate/CronDelete)
└── decisions.py       # Decision logging + session bootstrap context
```

### engagement.py

- `enroll_for_tracking(action_id, platform, target_url, comment_url)` — adds to reply_tracking after every comment
- `get_due_checks()` — returns entries where next_check_at <= now and checks_done < 3
- `record_check(tracking_id, upvotes, replies, reply_content, reply_author)` — logs outcome, increments check count
- `should_reply(reply_content)` — 70% probability roll
- `mark_replied(tracking_id, reply_action_id)` — links our follow-up reply
- `mark_exhausted(tracking_id)` — after 3rd check with no reply
- `get_active_tracking_count()` — for status display

### threads.py

- `generate_thread_outline(thread_type)` — returns topic + 3-5 tweet outlines
- `format_thread(outline)` — ensures each tweet under 280 chars
- `log_thread(session_id, thread_type, topic, tweets, first_tweet_url)` — saves to DB
- `get_recent_threads(days=7)` — avoid repeating topics

### analytics.py

- `update_keyword_score(keyword, platform, replies, upvotes)` — recalculates score
- `get_weighted_keywords(platform, n=5)` — top keywords with explore/exploit (70/30)
- `update_peak_times(platform, hour, day, replies, upvotes)` — logs engagement data
- `get_best_hours(platform, top_n=3)` — returns best session hours
- `calculate_engagement_score(action_id)` — composite from upvotes + replies

### relationships.py

- `track_interaction(platform, username, display_name, action_id, interaction_type)` — upsert
- `get_known_users(platform)` — users interacted with before
- `get_high_value_users(platform, min_interactions=3)` — worth engaging again
- `is_known_user(platform, username)` — quick check

### calendar.py

- `plan_week(start_date)` — generates content calendar for 7 days
- `get_today_content(platform)` — what's planned today
- `mark_posted(calendar_id, action_id)` — link to actual post
- `get_upcoming(days=3)` — preview

### cron.py

- `start_reply_checker()` — CronCreate every 15min
- `stop_reply_checker()` — CronDelete
- `get_active_jobs()` — CronList wrapper

### decisions.py

- `log_decision(db_path, category, decision, reasoning, context, platform, session_id)` — log any decision
- `get_recent_decisions(db_path, category, platform, limit=20)` — query decisions
- `get_session_decisions(db_path, session_id)` — all decisions from a session
- `get_decision_summary(db_path, days=7)` — digest for session bootstrap

---

## Reply Tracking & Cron Flow

### Phase 1: Enrollment (during session)

```
Action executed (comment/reply)
    -> runner.record_action() returns action_id
    -> engagement.enroll_for_tracking(action_id, platform, target_url, comment_url)
    -> decisions.log_decision('engagement', 'Enrolled comment for reply tracking', ...)
    -> reply_tracking row: status='active', checks_done=0, next_check_at=now+15min
```

### Phase 2: Cron checker (every 15min via CronCreate)

```
Cron fires -> "check_replies" prompt runs
    -> engagement.get_due_checks() returns list
    -> For each entry:
        1. Open target_url in browser via Owl
        2. Find our comment, check for replies
        3. Record outcome: engagement.record_check(...)
        4. analytics.update_keyword_score() with new data
        5. analytics.update_peak_times() with new data

        If reply found:
            -> Roll 70/30: engagement.should_reply()
            -> If yes: read reply, write response, post via Owl
                -> runner.record_action() for the reply
                -> engagement.mark_replied(tracking_id, reply_action_id)
                -> relationships.track_interaction(...)
                -> decisions.log_decision('reply', 'Replied to @user', ...)
            -> If no:
                -> decisions.log_decision('reply', 'Skipped reply — rolled 30%', ...)

        If no reply + checks_done == 3:
            -> engagement.mark_exhausted(tracking_id)

        If no reply + checks_done < 3:
            -> Update next_check_at = now + 15min
```

### Phase 3: Session integration

```
Session starts -> cron.start_reply_checker()
Session ends   -> cron.stop_reply_checker()
```

### Edge cases

- Comment URL not available -> store target_url + username, search for comment on revisit
- Post deleted -> mark tracking as 'expired', log decision
- Rate limited during check -> skip, don't increment checks_done, retry next cycle
- Multiple replies -> record all, auto-reply to most recent one only

---

## Twitter Thread System

### Thread types

**Building-in-public** (product-specific):
- What I shipped this week
- A bug that took forever to fix
- User feedback that changed our roadmap
- Metrics update
- Technical decision and why

**General founder** (broader):
- Hot takes on tools/frameworks
- Lessons learned building a SaaS
- Tips for indie hackers
- Comparisons or opinions on trends
- "Things I wish I knew when I started..."

### Thread structure

- Tweet 1: Hook (attention-grabbing opener)
- Tweet 2-4: Body (one idea per tweet)
- Tweet 5 (optional): CTA or takeaway (soft, not salesy)
- Min 3, max 5 tweets per thread
- Each tweet under 280 chars (hard limit)
- One thread per session max
- No topic repeats within 14 days

### Posting flow

```
1. calendar.get_today_content('twitter') -> check for planned thread
2. If planned: use it. If not: threads.generate_thread_outline(random_type)
3. Check threads.get_recent_threads(days=14) -> avoid overlap
4. Format tweets, verify each < 280 chars
5. Post via Owl on https://x.com:
   - Navigate to https://x.com
   - Click compose
   - Write tweet 1 via clipboard+paste
   - Post it
   - Click on posted tweet
   - Click reply, write tweet 2 via clipboard+paste
   - Post reply
   - Repeat for remaining tweets
   - Grab URL of first tweet
6. threads.log_thread(...)
7. engagement.enroll_for_tracking(...)
8. decisions.log_decision('content', 'Posted thread on ...', ...)
```

---

## Smart Keywords & Engagement Scoring

### Keyword scoring

```
score = (replies_received * 3) + (avg_upvotes * 1) + (comments_made * 0.5) + recency_bonus
```

- recency_bonus: +2 if used in last 3 days

### Keyword selection (explore/exploit)

- 70% chance: pick from top 3 by score (exploit)
- 30% chance: pick random keyword from full list (explore)

### Engagement scoring per action

```
engagement_score = (upvotes * 1) + (replies * 5) + (profile_clicks * 3)
```

Feeds back into keyword_performance.score, peak_times.engagement_score, relationships.relationship_score.

Score updates happen during the 15min cron reply checker — upvote counts update even without replies.

---

## Peak Time Targeting

### Data collection

Every action's timestamp + outcomes feed into peak_times table grouped by (platform, day_of_week, hour).

### Usage

```python
best_hours = analytics.get_best_hours('twitter', top_n=3)
# Returns: [(14, 'Wed', 7.1), (10, 'Mon', 6.8), (16, 'Fri', 5.2)]
```

Shown in `python3 -m gtm status` output. After 2+ weeks of data, recommends best session times per platform.

---

## Relationship Tracking

### When tracked

- We comment on someone's post -> track username
- Someone replies to our comment -> track with higher weight
- We reply back -> increment interaction count
- We follow someone -> track as interaction

### Score

```
relationship_score = interaction_count * 2 + (they_replied_to_us * 5)
```

### Usage during sessions

- If post author is known user with 3+ interactions -> prioritize engaging
- If known user -> reference past interactions naturally in comments
- If known user replies -> boost reply probability from 70% to 90%

---

## Content Calendar

### Weekly planning

```python
calendar.plan_week('2026-03-10')
```

### Rules

- Max 1 thread per day on Twitter
- Max 2 Dev.to articles per week
- Max 1 Reddit post per sub per session
- Alternate between product-specific and general content
- Check recent threads + past calendar to avoid topic repeats
- Calendar is a suggestion — can be overridden if trending content is more relevant

### Session integration

```
Session starts -> today_content = calendar.get_today_content(platform)
If planned: use it. If not: roll randomly as before.
After posting: calendar.mark_posted(calendar_id, action_id)
```

---

## Decision Logging

### What gets logged

| When | Category | Example |
|------|----------|---------|
| Chose keyword | keyword | "Used 'bug reporting tool' on reddit — score 8.2" |
| Rolled action | engagement | "Skipped post — duplicate URL" |
| Promoted | promotion | "Promoted product — ratio at 6%, relevant post" |
| Skipped promo | promotion | "Skipped promo — ratio at 9.8%" |
| Replied to reply | reply | "User @devguy asked about pricing — replying" |
| Skipped reply | reply | "User replied 'thanks' — rolled 30%, skipping" |
| Created thread | content | "4-tweet thread on shipping auth" |
| Calendar planned | calendar | "Scheduled devto article for Wednesday" |
| Peak time | design | "Started session at 2pm — best for twitter" |
| Session bootstrap | design | "Loaded: 12 active trackers, promo ratio OK" |

### Session bootstrap

On session start, `decisions.get_decision_summary(db_path, days=7)` returns:
- Last 7 days: action counts, comment counts, promotion counts
- Active reply trackers: count per platform
- Keyword performance: top 5 per platform
- Promo ratios: per platform
- Relationships: users with 3+ interactions
- Content calendar: today's planned content
- Recent decisions: last 10 key decisions with reasoning

This allows full context recovery after session compaction.

---

## Runner Changes

InterleavedRunner stays slim. After each record_action():

```python
if action_type in ('comment', 'like_and_comment'):
    engagement.enroll_for_tracking(action_id, platform, target_url, comment_url)
    if username:
        relationships.track_interaction(platform, username, ...)
    analytics.update_keyword_score(keyword_used, platform, ...)
    decisions.log_decision(...)
```

Session startup adds:
```python
cron.start_reply_checker()
summary = decisions.get_decision_summary(db_path, days=7)
# Print summary for context
```

Session end adds:
```python
cron.stop_reply_checker()
```
