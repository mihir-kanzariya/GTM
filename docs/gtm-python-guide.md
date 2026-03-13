# GTM Python Command Guide

All commands and functions available in the GTM automation system. Each section shows when and where to use them.

---

## CLI Commands

Run these from terminal: `python3 -m gtm <command>`

```bash
# --- Setup (run once) ---
python3 -m gtm init                          # First-time setup: creates DB + state file

# --- Niche Profile (run once, update as needed) ---
python3 -m gtm niche                         # View current niche profile
python3 -m gtm niche set-industries ai saas developer-tools  # Set your industries
python3 -m gtm niche set-audiences developers founders       # Set your target audiences
python3 -m gtm niche exclude politics crypto sports          # Exclude off-topic categories
python3 -m gtm niche add-product blocfeed.com "bug reporting"  # Add a product to promote

# --- Goals (auto-selected each session, manual override rarely needed) ---
python3 -m gtm goal                          # View current goals + auto-recommendation with reasoning
python3 -m gtm goal set balanced             # Manual override (rare): set default goal
python3 -m gtm goal set visibility twitter   # Manual override: force goal for a specific platform
# Goal is auto-picked by recommend_goal() based on stats:
#   < 50 actions → visibility (early stage)
#   < 4 platforms active → visibility (need reach)
#   promo ratio > 8% → relationships (cool down)
#   reply rate < 5% → visibility (need eyeballs)
#   10+ relationships → conversions (leverage trust)
#   100+ actions, 0 promos → conversions (safe to start)
#   otherwise → balanced

# --- Pre-Session Checks (run before every session) ---
python3 -m gtm status                        # Session status: running/idle, per-platform actions today
python3 -m gtm alerts                        # Safety warnings: high promo ratio, inactivity gaps
python3 -m gtm briefing                      # Full intelligence briefing: topics, weak signals, opportunities

# --- Intelligence Reports (check anytime) ---
python3 -m gtm trends                        # Active topics with trend/opportunity scores
python3 -m gtm signals                       # Weak signals (early trends worth posting about)

# --- Analytics (check weekly or after sessions) ---
python3 -m gtm stats                         # Weekly report: actions, comments, promos per platform
python3 -m gtm keywords                      # Top performing keywords per platform
python3 -m gtm relationships                 # High-value users you interact with frequently
python3 -m gtm tracking                      # Active reply trackers waiting for responses
python3 -m gtm decisions                     # Last 10 decisions with reasoning (context recovery)
python3 -m gtm calendar                      # Upcoming planned content (next 7 days)
python3 -m gtm actions                       # All action types per platform with weights/limits
python3 -m gtm actions twitter               # Filter to one platform
```

---

## Session Lifecycle

### Step 1: Pre-Flight

```python
# Use at: start of every session, before any engagement

from gtm.runner import InterleavedRunner
from gtm.decisions import get_decision_summary

# Recover context from previous sessions (what happened last 7 days)
summary = get_decision_summary('/Users/mihirkanzariya/GTM/gtm.db', days=7)
# Returns: total_actions, comments, promotions, active_trackers,
#          promo_ratios, top_keywords, high_value_relationships,
#          calendar_today, recent_decisions

# Initialize runner (auto-loads goal from state.json)
runner = InterleavedRunner(
    '/Users/mihirkanzariya/GTM/gtm.db',
    '/Users/mihirkanzariya/GTM/state.json',
    goal=None,  # optional: override goal, e.g. "visibility"
)
```

### Step 2: Discovery Scan (optional, 2-3 min)

```python
# Use at: before engagement to find what's trending
# Uses WebFetch/WebSearch only, NO Owl needed

from gtm.collectors import (
    parse_reddit_response, parse_hn_stories, parse_devto_response,
    build_search_queries, get_niche_subreddits,
)
from gtm.intelligence import store_signals, create_topic, compute_trend_score, compute_opportunity_score

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# Get subreddits matching your niche (ai, saas, dev-tools)
subreddits = get_niche_subreddits(db_path)
# Returns: ["webdev", "SaaS", "indiehackers", "startups", "artificial", "MachineLearning", ...]

# Fetch Reddit signals
# For each subreddit: WebFetch f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
# Then parse:
signals = parse_reddit_response(response_json, "reddit")
store_signals(db_path, signals, session_id="your-session-id")

# Fetch HN top stories
# WebFetch "https://hacker-news.firebaseio.com/v0/topstories.json" -> list of IDs
# For top 30 IDs: WebFetch f"https://hacker-news.firebaseio.com/v0/item/{id}.json"
signals = parse_hn_stories(story_objects)
store_signals(db_path, signals, session_id="your-session-id")

# Fetch Dev.to trending
# WebFetch "https://dev.to/api/articles?top=1&per_page=30"
signals = parse_devto_response(articles_json)
store_signals(db_path, signals, session_id="your-session-id")

# Build niche-aware search queries for Twitter/general
queries = build_search_queries(db_path)
# Returns: ['site:x.com ("ai" OR "saas") developer tools trending today', ...]
# For each: WebSearch(query)

# After collecting, Claude clusters signals into topics
# For each discovered topic:
tid = create_topic(db_path, {
    "name": "MCP server adoption",
    "description": "Developers discovering MCP protocol for AI tool integration",
    "key_phrases": ["mcp servers", "tool use", "ai agents"],
    "platforms_seen": ["twitter", "hackernews"],
    "total_mentions": 12,
    "relevance": "high",       # high|medium|low|none — based on niche match
    "authority_score": 8,       # HN frontpage +5, high-follower +3, etc.
    "velocity": 2.0,            # (mentions_last_12h - mentions_prev_12h) / max(prev, 1)
})
compute_trend_score(db_path, tid)
compute_opportunity_score(db_path, tid, goal="balanced")
```

### Step 3: Load Briefing

```python
# Use at: after discovery scan, before starting engagement

runner.start_all()  # creates session records for all platforms
briefing = runner.load_briefing()

# briefing contains:
# {
#   "goal": "balanced",
#   "goals_by_platform": {"twitter": "visibility"},
#   "niche": {"industries": [...], "audiences": [...], "exclude": [...], "products": [...]},
#   "topics": [{"name": "MCP servers", "status": "emerging", "trend_score": 8.2, ...}],
#   "weak_signals": [{"name": "...", "velocity": 1.5, "platform_count": 3, ...}],
#   "opportunities": [{"name": "...", "opportunity_score": 7.5, ...}],
#   "promo_status": {"twitter": "safe", "reddit": "blocked"},
#   "pending_replies": [...],
#   "relationships": {"twitter": [{"username": "dev_guru", "interaction_count": 5}]},
# }
```

### Step 4: Engagement Loop

```python
# Use at: main session loop — interleave actions across all platforms via Owl

from gtm.runner import roll_action

while not runner.is_done():
    # Pick next platform (avoids repeating same one)
    platform = runner.pick_next()
    if platform is None:
        break

    # Roll a random action based on platform weights/limits
    action = runner.roll_action(platform)
    # Returns: "like", "comment", "reply", "follow", "retweet", "skip", etc.

    # Get action details
    desc = runner.get_action_desc(platform, action)
    # Returns: "Reply to a tweet. 1-3 sentences, conversational, add value."

    char_limit = runner.get_char_limit(platform, action)
    # Returns: 280 for twitter reply, 10000 for reddit comment, None for like

    # Check if should promote
    if runner.should_promote(platform):
        # Safe to include a soft product mention (< 10% promo ratio)
        pass

    # Check for duplicate URLs before engaging
    if runner.is_duplicate("https://x.com/post/123"):
        continue  # skip, already engaged

    # Execute action via Owl, then record it
    runner.record_action(
        platform,
        action,
        "https://x.com/post/123",           # target URL
        target_title="Post about AI agents", # post title (optional)
        content="great point about agents",  # your comment text (optional)
        promoted_product="blocfeed",         # if promoting (optional)
        keywords_matched="ai agents",        # search keyword used (optional)
        comment_url="https://x.com/reply/1", # direct URL to your comment (optional)
        author_username="dev_guru",          # post author for relationship tracking (optional)
    )
    # Automatically: enrolls comments for reply tracking, tracks relationships, logs decisions

    # Log topics discovered during engagement
    runner.discover_topic("twitter", "MCP server adoption", key_phrases=["mcp", "tool use"])

    # Check progress
    progress = runner.progress()
    # Returns: {"twitter": "5/25", "reddit": "3/12", "producthunt": "1/5", ...}

    # Check action breakdown for a platform
    breakdown = runner.action_breakdown("twitter")
    # Returns: {"like": 3, "reply": 2, "retweet": 1}
```

### Step 5: End Session

```python
# Use at: when all platforms are done or time limit hit

runner.finish()
# Automatically runs:
#   transition_statuses()  -> promote topics (weak->emerging->confirmed)
#   expire_stale()         -> expire old topics not seen in 3-5 days
#   update_feedback()      -> mark topics with good engagement as "proven"
#   run_revisits()         -> check for replies to your comments
#   Updates state.json (session count, last session time)

summary = runner.summary()
# Returns: {
#   "platforms": ["twitter", "reddit", ...],
#   "total_actions": 42,
#   "actions_per_platform": {"twitter": 25, "reddit": 12, ...},
#   "limits_per_platform": {"twitter": 25, "reddit": 15, ...},
#   "max_duration_min": 35,
# }
```

---

## Niche Profile Management

```python
# Use at: one-time setup, or when changing target industries

from gtm.niche import get_niche, set_niche_field, add_product, get_products, is_excluded_topic

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# View current niche
niche = get_niche(db_path)
# Returns: {"industries": ["ai", "saas"], "audiences": ["developers"], "exclude": ["politics"], "products": [...]}

# Set industries (replaces existing)
set_niche_field(db_path, "industries", ["ai", "saas", "developer-tools"])

# Set target audiences
set_niche_field(db_path, "audiences", ["developers", "founders", "indie-hackers"])

# Set exclusion terms (topics matching these are dropped)
set_niche_field(db_path, "exclude", ["politics", "crypto", "sports", "gaming"])

# Add products to promote
add_product(db_path, "blocfeed.com", "in-app bug reporting with AI triage")
add_product(db_path, "blocpad.com", "unified workspace for dev teams")

# Get product list
products = get_products(db_path)
# Returns: [{"url": "blocfeed.com", "desc": "in-app bug reporting"}, ...]

# Check if a topic should be excluded
is_excluded_topic(db_path, "Bitcoin ETF approval")   # True (matches "crypto")
is_excluded_topic(db_path, "AI agents for devs")     # False
```

---

## Goal Management

```python
# Use at: before sessions to set engagement strategy

from gtm.goals import get_goals, set_goal, get_goal_for_platform, recommend_goal, VALID_GOALS

db_path = '/Users/mihirkanzariya/GTM/gtm.db'
state_path = '/Users/mihirkanzariya/GTM/state.json'

# Valid goals
VALID_GOALS  # ["visibility", "conversions", "relationships", "balanced"]

# Auto-recommend goal based on current stats (used by runner automatically)
goal, reasoning = recommend_goal(db_path, state_path)
# Returns: ("visibility", "reply rate only 0% with 323 actions, need more visibility")
# Runner uses this automatically — no manual setup needed

# Manual override (rare)
set_goal(state_path, "balanced")
set_goal(state_path, "visibility", platform="twitter")

# Get all goals
goals = get_goals(state_path)
# Returns: {"default": "balanced", "platforms": {"twitter": "visibility"}}

# Get effective goal for a platform (uses override if set, otherwise default)
get_goal_for_platform(state_path, "twitter")  # "visibility"
get_goal_for_platform(state_path, "devto")    # "balanced" (no override, uses default)
```

---

## Intelligence Engine

```python
# Use at: discovery scan, briefing, and post-session analysis

from gtm.intelligence import (
    # Signal storage
    store_signal, store_signals,
    # Topic management
    create_topic, get_topic, get_topics_by_status, get_active_topics, update_topic_mentions,
    # Scoring
    compute_trend_score, compute_opportunity_score,
    # Lifecycle
    transition_statuses, expire_stale,
    # Briefing
    get_briefing, get_weak_signals, get_content_opportunities,
    # Feedback
    update_feedback, record_topic_engagement,
)

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# --- Store raw signals from platform feeds ---
# Use at: during discovery scan after fetching from APIs

signal_id = store_signal(db_path, {
    "platform": "twitter",
    "title": "AI agents are changing dev workflows",
    "text_snippet": "Just tried building with MCP servers and...",
    "author": "@dev_user",
    "author_followers": 5000,
    "engagement": 142,
    "source_url": "https://x.com/dev_user/status/123",
})

# Batch store
ids = store_signals(db_path, [signal1, signal2, signal3], session_id="sess-uuid")

# --- Create and manage topic clusters ---
# Use at: after Claude groups signals into semantic topics

topic_id = create_topic(db_path, {
    "name": "MCP server adoption",
    "description": "Developers discovering MCP protocol",
    "key_phrases": ["mcp servers", "tool use", "ai agents"],
    "platforms_seen": ["twitter", "hackernews", "reddit"],
    "total_mentions": 15,
    "relevance": "high",
    "authority_score": 12,
    "velocity": 2.5,
})

# Get a topic
topic = get_topic(db_path, topic_id)

# Get topics by status
emerging = get_topics_by_status(db_path, "emerging")  # ordered by trend_score desc
# Status values: weak | emerging | confirmed | proven | cooling | expired

# Get all non-expired topics
active = get_active_topics(db_path)  # ordered by opportunity_score desc

# Update when topic is seen again
update_topic_mentions(db_path, topic_id, new_mentions=5, new_platforms=["devto"])

# --- Score topics ---
# Use at: after creating/updating topics during discovery

# Trend score = frequency*0.3 + velocity*0.4 + authority*0.2 + platform_diversity*0.1
compute_trend_score(db_path, topic_id)

# Opportunity score = trend + relevance + engagement + goal_bonus - saturation
compute_opportunity_score(db_path, topic_id, goal="visibility")

# --- Lifecycle transitions ---
# Use at: end of session (runner.finish() calls these automatically)

transition_statuses(db_path)  # weak->emerging (8+ mentions, velocity>0), emerging->confirmed (20+)
expire_stale(db_path)         # weak/cooling expire after 3 days, others after 5 days

# --- Briefing ---
# Use at: before engagement to get full context

briefing = get_briefing(db_path, '/Users/mihirkanzariya/GTM/state.json')

# Get just weak signals (post early for maximum impact)
weak = get_weak_signals(db_path)
# Returns: topics where status='weak', platform_count>=2, velocity>0, authority>=3

# Get top content opportunities
opps = get_content_opportunities(db_path, goal="visibility", limit=5)

# --- Feedback learning ---
# Use at: end of session (runner.finish() calls automatically)

update_feedback(db_path)  # promotes topics with good engagement to "proven"

# Record engagement on a specific topic
record_topic_engagement(db_path, topic_id, engagement_score=25)
# Updates times_we_posted and running avg_engagement
```

---

## Signal Collectors (Parsers)

```python
# Use at: during discovery scan to parse API responses into standard signal format

from gtm.collectors import (
    parse_reddit_response, parse_hn_stories, parse_devto_response,
    parse_github_trending, build_search_queries, get_niche_subreddits,
)

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# Parse Reddit JSON (from WebFetch "https://www.reddit.com/r/webdev/hot.json?limit=25")
signals = parse_reddit_response(reddit_json, "reddit")
# Returns: [{"platform": "reddit", "title": "...", "author": "...", "engagement": 42, ...}]

# Parse HN stories (from WebFetch per-story after getting top story IDs)
signals = parse_hn_stories(story_list)
# Returns: [{"platform": "hackernews", "title": "...", "engagement": 200, ...}]

# Parse Dev.to (from WebFetch "https://dev.to/api/articles?top=1&per_page=30")
signals = parse_devto_response(articles_json)
# Returns: [{"platform": "devto", "title": "...", "engagement": 30, ...}]

# Parse GitHub trending (from WebFetch "https://github.com/trending?since=daily")
signals = parse_github_trending(html_text)
# Returns: [{"platform": "github", "title": "owner/repo", ...}]

# Build search queries from niche profile
queries = build_search_queries(db_path)
# Returns: ['site:x.com ("ai" OR "saas") developer tools trending today', ...]

# Get subreddits matching niche
subs = get_niche_subreddits(db_path, max_subs=8)
# Returns: ["webdev", "SaaS", "artificial", "MachineLearning", "indiehackers", ...]
```

---

## Reply Tracking & Engagement

```python
# Use at: runner.record_action() handles enrollment automatically
# Manual use: when checking replies or managing tracking

from gtm.engagement import (
    enroll_for_tracking, get_due_checks, record_check,
    should_reply, mark_replied, mark_exhausted,
    get_active_tracking_count,
)

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# Enroll a comment for reply tracking (done automatically by runner)
tracking_id = enroll_for_tracking(db_path, action_id=42, platform="twitter",
    target_url="https://x.com/post/1", comment_url="https://x.com/reply/1")

# Get entries due for checking (used by cron reply checker)
due = get_due_checks(db_path)
# Returns: list of tracking entries where next_check_at <= now

# Record what we found when checking
record_check(db_path, tracking_id, upvotes=5, replies=2,
    reply_content="Great point!", reply_author="@someone")

# 70% chance to reply back (randomized for human mimicry)
if should_reply("Great point!"):
    # Reply via Owl, then:
    mark_replied(db_path, tracking_id, reply_action_id=43)
else:
    mark_exhausted(db_path, tracking_id)

# Check how many trackers are active
count = get_active_tracking_count(db_path)
```

---

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

---

## Relationships

```python
# Use at: runner.record_action() handles tracking automatically when author_username is provided
# Manual use: to check who your high-value contacts are

from gtm.relationships import track_interaction, get_known_users, get_high_value_users, is_known_user

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# Track an interaction (done automatically by runner)
track_interaction(db_path, "twitter", "dev_guru", "Dev Guru", action_id=42, interaction_type="reply")

# Get all known users on a platform
users = get_known_users(db_path, "twitter")

# Get high-value users (3+ interactions)
hvus = get_high_value_users(db_path, "twitter", min_interactions=3)
# Returns: [{"username": "dev_guru", "interaction_count": 5, "relationship_score": 45}]

# Check if someone is known
is_known_user(db_path, "twitter", "dev_guru")  # True/False
```

---

## Twitter Threads

```python
# Use at: when posting a multi-tweet thread (max 1 per session)

from gtm.threads import log_thread, get_recent_threads, format_thread

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# Check recent threads (avoid repeating topics within 14 days)
recent = get_recent_threads(db_path, days=14)

# Format tweets (truncate to 280 chars)
tweets = ["Tweet 1 text here", "Tweet 2 continues the thought", "Tweet 3 wraps up"]
formatted = format_thread(tweets)  # truncates any tweet over 280 chars

# Log after posting
log_thread(db_path, session_id="sess-uuid", thread_type="building_in_public",
    topic="Why we rebuilt our auth system", tweets=formatted,
    first_tweet_url="https://x.com/user/status/123")
```

---

## Content Calendar

```python
# Use at: planning content ahead of time, checking what's due today

from gtm.calendar import add_content, get_today_content, mark_posted, get_upcoming

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# Plan content
cal_id = add_content(db_path, "twitter", "thread", "MCP servers explained",
    outline="1. What is MCP\n2. Why it matters\n3. How to start",
    scheduled_for="2026-03-14")

# Check what's planned today
today = get_today_content(db_path, "twitter")

# Mark as posted after publishing
mark_posted(db_path, cal_id, action_id=42)

# See upcoming content (next 3 days)
upcoming = get_upcoming(db_path, days=3)
```

---

## Analytics & Keywords

```python
# Use at: after sessions to track what keywords/times perform best

from gtm.analytics import (
    update_keyword_score, get_weighted_keywords, seed_keywords,
    update_peak_times, get_best_hours, calculate_engagement_score,
)

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# Update keyword performance (done during sessions)
update_keyword_score(db_path, "ai agents", "twitter", replies=3, upvotes=15)

# Get top performing keywords
top = get_weighted_keywords(db_path, "twitter", n=5)
# Returns: [("ai agents", 45.2), ("developer tools", 32.1), ...]

# Pre-seed keywords
seed_keywords(db_path, "twitter", ["ai agents", "developer tools", "bug reporting"])

# Track best posting times
update_peak_times(db_path, "twitter", day="Monday", hour=14, replies=5, upvotes=20)
best = get_best_hours(db_path, "twitter", top_n=3)

# Calculate engagement score for an action
score = calculate_engagement_score(db_path, action_id=42)
# Returns: upvotes * 1 + replies * 5
```

---

## Decisions (Context Recovery)

```python
# Use at: start of session to recover what happened in previous sessions
# runner.record_action() logs decisions automatically

from gtm.decisions import log_decision, get_recent_decisions, get_decision_summary

db_path = '/Users/mihirkanzariya/GTM/gtm.db'

# Log a decision (done automatically by runner)
log_decision(db_path, "engagement", "Replied to AI thread",
    reasoning="High-value user, relevant topic", platform="twitter", session_id="sess-uuid")

# Get recent decisions
decisions = get_recent_decisions(db_path, category="engagement", limit=10)

# Full 7-day summary (use at session start for context recovery)
summary = get_decision_summary(db_path, days=7)
# Returns: {
#   "total_actions": 245,
#   "comments": 48,
#   "promotions": 12,
#   "active_trackers": 8,
#   "promo_ratios": {"twitter": 0.05, "reddit": 0.03},
#   "top_keywords": {"twitter": [("ai agents", 45.2)], ...},
#   "high_value_relationships": {"twitter": [{"username": "dev_guru", ...}]},
#   "calendar_today": [...],
#   "recent_decisions": [{"category": "engagement", "decision": "...", "reasoning": "..."}],
# }
```

---

## Reply Checker Cron

```python
# Use at: session start (create) and session end (delete)

from gtm.cron import build_reply_checker_prompt, get_cron_expression

# Build prompt for CronCreate tool
prompt = build_reply_checker_prompt('/Users/mihirkanzariya/GTM/gtm.db')
schedule = get_cron_expression()  # "*/15 * * * *" (every 15 minutes)

# Session start: CronCreate with schedule and prompt
# Session end: CronDelete to stop the checker
```

---

## Database & State

```python
# Use at: low-level operations, usually called by other modules

from gtm.db import get_connection, init_db, create_session, end_session, log_action, is_duplicate_url, get_promotion_ratio
from gtm.state import load_state, save_state, can_start_session, PLATFORMS

# PLATFORMS list (all supported platforms)
PLATFORMS  # ["reddit", "twitter", "producthunt", "indiehackers", "devto", "hackernews"]

# Get DB connection (WAL mode, Row factory)
conn = get_connection('/Users/mihirkanzariya/GTM/gtm.db')

# Check promo ratio before promoting
ratio = get_promotion_ratio(db_path, "twitter", days=7)  # e.g. 0.05 = 5%

# Check for duplicate URLs
is_duplicate_url(db_path, "https://x.com/post/123", days=7)  # True/False

# State management
state = load_state('/Users/mihirkanzariya/GTM/state.json')
save_state('/Users/mihirkanzariya/GTM/state.json', state)
```

---

## Quick Reference: Module Purpose

| Module | Purpose | When to use |
|--------|---------|-------------|
| `runner.py` | Session orchestration | Every session (start, loop, finish) |
| `intelligence.py` | Signals, topics, scoring, briefing | Discovery scan + briefing |
| `niche.py` | Industry boundaries | One-time setup |
| `goals.py` | Engagement strategy | Before sessions |
| `collectors.py` | Parse platform API responses | Discovery scan |
| `engagement.py` | Reply tracking | Automatic via runner |
| `revisits.py` | Post-session reply checking | Automatic via runner.finish() |
| `relationships.py` | User relationship tracking | Automatic via runner |
| `threads.py` | Twitter thread management | When posting threads |
| `calendar.py` | Content planning | Planning ahead |
| `analytics.py` | Keyword + time performance | After sessions |
| `decisions.py` | Context recovery | Session start |
| `cron.py` | Reply checker scheduling | Session boundaries |
| `db.py` | Database layer | Low-level, called by other modules |
| `state.py` | Session state | Called by runner |
| `stats.py` | Weekly reports + alerts | Checking performance |
| `cli.py` | Terminal commands | Human interaction |
