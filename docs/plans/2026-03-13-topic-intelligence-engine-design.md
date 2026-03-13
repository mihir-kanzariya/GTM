# Topic Intelligence Engine — Design Document

**Date:** 2026-03-13
**Status:** Approved
**Goal:** Replace keyword tracking with a full topic intelligence pipeline that collects signals, detects trends, scores opportunities, and feeds structured context to the AI agent.

---

## Problem

The current system logs actions but doesn't learn. Keywords are hardcoded in CLAUDE.md. The AI starts each session blind — no knowledge of what's trending, what worked before, or what opportunities exist. 11 DB tables collect data that's never used for decisions.

## Niche Profile (Industry Boundaries)

The engine must stay within the user's industry. A **niche profile** acts as a hard filter at every layer — collection, clustering, and scoring. Topics outside the niche are dropped immediately.

### Configuration

```bash
python3 -m gtm niche                           # show current niche
python3 -m gtm niche set-industries ai saas developer-tools productivity
python3 -m gtm niche set-audiences developers indie-hackers founders solopreneurs
python3 -m gtm niche exclude politics crypto celebrity sports finance gaming
python3 -m gtm niche add-product blocpad.com "unified workspace for dev teams"
python3 -m gtm niche add-product blocfeed.com "in-app bug reporting with AI triage"
```

### Schema

```sql
CREATE TABLE IF NOT EXISTS niche_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,       -- 'industries', 'audiences', 'exclude', 'products'
    value TEXT NOT NULL,            -- JSON array
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Example data:
```
industries:  ["ai", "saas", "developer-tools", "productivity", "devops", "open-source"]
audiences:   ["developers", "indie-hackers", "founders", "solopreneurs", "product-managers"]
exclude:     ["politics", "crypto", "celebrity", "sports", "finance", "gaming", "entertainment"]
products:    [{"url": "blocpad.com", "desc": "unified workspace"}, {"url": "blocfeed.com", "desc": "bug reporting"}]
```

### Where the filter applies

| Layer | How niche filters |
|---|---|
| Signal Collection | Only collect from relevant subreddits, dev-focused searches, tech tags. Skip general trending. |
| Topic Clustering | Claude evaluates each topic: "Is this about AI/SaaS/dev-tools?" → assigns relevance (high/medium/low/none) |
| Trend Scoring | Topics with relevance `none` → dropped, never scored. Topics with `low` → scored but deprioritized. |
| Opportunity Scoring | Relevance is a multiplier — high relevance topics get 3x, medium get 1.5x, low get 0.5x |
| Content Angles | Only suggest angles that connect to user's products/industry |

### Source filtering examples

```
Reddit sources (niche: ai + saas + dev-tools):
  INCLUDE: r/webdev, r/SaaS, r/indiehackers, r/startups, r/devtools, r/artificial
  EXCLUDE: r/politics, r/cryptocurrency, r/gaming, r/sports

Twitter searches:
  INCLUDE: "developer tools", "saas", "ai agents", "indie hacker"
  EXCLUDE: general trending (too noisy, crosses niche boundaries)

HN: already dev-focused, but filter by story tags/content

Dev.to: inherently niche-filtered (all dev content)
```

### Relevance evaluation

During topic clustering, Claude assigns relevance by checking against the niche profile:

```
Input topic: "MCP server adoption"
Niche check: AI ✓, developer-tools ✓ → relevance: HIGH

Input topic: "Trump tariffs on tech"
Niche check: politics ✗ (excluded) → relevance: NONE → dropped

Input topic: "New Notion API features"
Niche check: saas ✓, productivity ✓ → relevance: HIGH

Input topic: "Bitcoin ETF approval"
Niche check: crypto ✗ (excluded) → relevance: NONE → dropped

Input topic: "Remote work burnout"
Niche check: not excluded, loosely related to founders → relevance: LOW
```

---

## Core Architecture

```
Signal Collection (WebSearch + WebFetch, no Owl)
   ↓
content_signals table
   ↓
Topic Extraction (Claude clusters semantically)
   ↓
topic_clusters table
   ↓
Trend Detection (velocity + authority + cross-platform)
   ↓
Opportunity Scoring (goal-weighted)
   ↓
Content Opportunities (structured context for Claude)
   ↓
Engagement (Owl)
   ↓
Feedback Learning (outcomes → score updates)
```

## Session Flow

```
Phase 1: Research (2-3 min, WebSearch + WebFetch only)
├── Collect 200+ signals from 5-6 sources
├── Claude clusters into topics
├── Score trends + opportunities
├── Build engagement plan with suggested angles
│
Phase 2: Engagement (Owl)
├── Search using discovered topic key_phrases
├── Engage with goal-weighted actions
├── Post content using suggested angles
├── Log everything with topic_id links
│
Phase 3: Post-Session Learning
├── Update trend scores (velocity, authority)
├── Check outcomes → update topic_performance
├── Transition topic statuses
├── Expire stale topics
```

---

## Layer 1: Signal Collection

Collect raw posts/signals from platform APIs and web search. No Owl needed.

### Data Sources

| Source | Method | Returns |
|---|---|---|
| Twitter/X | WebSearch `site:x.com <niche terms>` | Trending tweets, discussions |
| Reddit | WebFetch `reddit.com/r/{sub}/hot.json` | Hot posts with scores |
| Hacker News | WebFetch `hacker-news.firebaseio.com/v0/topstories.json` | Top 500 story IDs |
| Dev.to | WebFetch `dev.to/api/articles?top=1&per_page=30` | Trending articles with tags |
| GitHub | WebFetch `github.com/trending?since=daily` | Trending repos |
| General | WebSearch `"developers talking about" OR "dev community" this week` | Broad signal |

### Schema

```sql
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
```

---

## Layer 2: Topic Extraction

Claude groups signals into topics semantically. No vector embeddings needed — Claude IS the semantic engine.

### Process

1. Collect 200+ signals
2. Send titles/snippets to Claude: "Group these into topics. For each: name, post count, key phrases, sentiment."
3. Match against existing topics in DB (merge if semantically similar)
4. Create new topic_clusters for genuinely new topics

### Schema

```sql
CREATE TABLE IF NOT EXISTS topic_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    key_phrases TEXT,              -- JSON array: ["mcp servers", "tool use"]
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME,
    status TEXT DEFAULT 'weak',   -- weak | emerging | confirmed | proven | expired

    -- Trend signals
    total_mentions INTEGER DEFAULT 0,
    platforms_seen TEXT,           -- JSON array: ["twitter", "hackernews"]
    platform_count INTEGER DEFAULT 0,
    velocity REAL DEFAULT 0,
    authority_score REAL DEFAULT 0,
    trend_score REAL DEFAULT 0,

    -- Opportunity signals
    relevance TEXT DEFAULT 'unknown',  -- high | medium | low | none
    saturation REAL DEFAULT 0,
    engagement_potential REAL DEFAULT 0,
    opportunity_score REAL DEFAULT 0,

    -- Content tracking
    times_we_posted INTEGER DEFAULT 0,
    avg_engagement REAL DEFAULT 0,
    best_angle TEXT,

    -- Lifecycle
    expires_at DATETIME
);
```

---

## Layer 3: Trend Detection

Compute trend score from four signals:

```
trend_score =
    frequency * 0.3      -- raw mention count
  + velocity * 0.4       -- growth rate (most important)
  + authority * 0.2      -- credible sources weigh more
  + platform_diversity * 0.1  -- multi-platform = stronger
```

### Velocity Calculation

```python
velocity = (mentions_last_12h - mentions_previous_12h) / max(mentions_previous_12h, 1)
```

### Authority Weights

| Source | Weight |
|---|---|
| HN frontpage | +5 |
| GitHub trending repo | +5 |
| High-follower account (10k+) | +3 |
| Medium account (1k+) | +2 |
| Random user | +1 |

### Status Transitions

```
weak (3+ mentions)
  → emerging (8+ mentions AND velocity > 0)
    → confirmed (20+ mentions)
      → proven (we posted AND got good engagement)

Any stage:
  → cooling (velocity negative for 2 sessions)
    → expired (not seen in 5 days, OR weak + not seen in 3 days)
```

---

## Layer 4: Opportunity Detection

Not every trend is worth acting on. Score opportunities:

```
opportunity_score =
    trend_score
  + relevance            -- does it match our niche?
  + engagement_potential -- do posts about it get replies?
  + goal_bonus           -- does it align with user's current goal?
  - saturation_penalty   -- is the conversation already crowded?
```

### Goal Alignment Bonuses

| Goal | Bonus conditions |
|---|---|
| visibility | +2 for emerging trends (catch waves early) |
| conversions | +3 for high-relevance topics (our niche only) |
| relationships | +2 for topics with known users active |
| balanced | +1 flat |

---

## Layer 5: Content Angle Generation

Output to Claude is structured context, not raw keywords:

```python
{
    "topic": "MCP server adoption",
    "stage": "emerging",
    "trend_score": 8.2,
    "opportunity_score": 7.5,
    "context": {
        "what": "Developers discovering MCP protocol for AI tool integration",
        "where": ["twitter (12)", "hackernews (3)", "reddit (2)"],
        "sentiment": "excitement + confusion",
        "key_voices": ["@anthropic", "u/webdev_guru"],
    },
    "suggested_angles": [
        "explain simply — most posts show confusion",
        "personal experience — authentic > tutorial",
        "comparison — hot take format works here",
    ],
    "avoid": "Generic 'MCP is great' — 80% saturation",
    "platforms_to_post": {
        "twitter": "thread (highest volume)",
        "hackernews": "comment in existing thread",
        "reddit": "reply with experience",
    },
}
```

---

## Layer 6: Feedback Learning

After each session, update scoring tables:

1. Check outcomes for posts linked to topics
2. Update topic avg_engagement, best_angle
3. Topics with good engagement → "proven" status
4. Topics with poor engagement → lower opportunity score
5. Feed proven topics into future briefings with higher weight

---

## Weak Signal Detection

The highest-value feature. Detect topics with 3-5 mentions but strong structural signals:

```sql
SELECT * FROM topic_clusters
WHERE status = 'weak'
  AND platform_count >= 2
  AND velocity > 0
  AND authority_score >= 5
ORDER BY velocity DESC;
```

Weak signals get flagged in briefings:

```
WEAK SIGNALS (post early for max impact):
- "MCP servers" — 4 mentions, 2 platforms, rising velocity
  Suggested: insight thread explaining the concept
```

### Content Strategy by Stage

| Stage | Strategy |
|---|---|
| weak signal | Insight posts, be first to explain |
| emerging | Commentary, hot takes, comparisons |
| confirmed | Tutorials, threads, deep dives |
| proven | Repurpose best-performing angles |

---

## User-Configurable Goals

Goals are stored in state.json. Can be set globally or per-platform.

```bash
python3 -m gtm goal set balanced                    # default
python3 -m gtm goal set twitter visibility
python3 -m gtm goal set reddit relationships
python3 -m gtm goal                                 # show current goals
```

Goals shape: action weights, keyword selection, who to engage, when to promote, content angles.

---

## New Module: `gtm/intelligence.py`

Single module that reads all tables and produces actionable output:

```python
# Signal collection
def collect_signals(db_path, platforms, session_id) -> list[dict]

# Topic clustering
def cluster_signals(db_path, signals) -> list[dict]
def merge_with_existing(db_path, new_topics) -> None

# Trend scoring
def compute_trend_scores(db_path) -> None
def compute_opportunity_scores(db_path, goal) -> None
def transition_statuses(db_path) -> None
def expire_stale(db_path) -> None

# Briefing
def get_briefing(db_path, goal, platforms) -> dict
def get_weak_signals(db_path) -> list[dict]
def get_content_opportunities(db_path, goal, platform) -> list[dict]

# Feedback
def update_feedback(db_path, session_id) -> None

# Goals
def get_goals(state_path) -> dict
def set_goal(state_path, goal, platform=None) -> None
```

---

## CLI Commands

```bash
# Niche profile
python3 -m gtm niche                           # show current niche profile
python3 -m gtm niche set-industries ai saas developer-tools
python3 -m gtm niche set-audiences developers indie-hackers founders
python3 -m gtm niche exclude politics crypto celebrity sports
python3 -m gtm niche add-product blocpad.com "unified workspace"
python3 -m gtm niche add-product blocfeed.com "bug reporting"

# Goals
python3 -m gtm goal                    # show current goals
python3 -m gtm goal set <strategy>     # set default (visibility|conversions|relationships|balanced)
python3 -m gtm goal set <platform> <strategy>  # per-platform override

# Intelligence
python3 -m gtm briefing                # full pre-session briefing
python3 -m gtm briefing twitter        # single platform
python3 -m gtm trends                  # show active trends with scores
python3 -m gtm signals                 # show weak signals
python3 -m gtm insights               # show what the engine has learned
```

---

## DB Changes Summary

| Change | Details |
|---|---|
| NEW: `niche_profile` | Industry boundaries, audiences, exclusions, products |
| NEW: `content_signals` | Raw signals collected from feeds |
| NEW: `topic_clusters` | Topics with trend/opportunity scores |
| REPLACE: `keyword_performance` | Absorbed into topic_clusters.key_phrases |
| REPLACE: `daily_metrics` | Was dead, now computed from content_signals |
| KEEP: All other 9 tables | sessions, actions, outcomes, reply_tracking, threads, relationships, content_calendar, peak_times, decision_log |

---

## Rate Limiting Rules

- Max 2 trend-based posts per day
- Max 1 post per topic per session
- Discovery scan: max 10 API calls per session
- Don't chase every trend — only top 3 opportunities per session
