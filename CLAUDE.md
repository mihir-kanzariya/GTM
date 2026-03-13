# GTM Automation — Master Strategy

## Products

### Blocpad
- **URL**: https://blocpad.com
- **What it is**: A unified real-time workspace that combines task management (Kanban boards, list views), Notion-style documentation/wiki, and team collaboration — all synced in real time.
- **Key features**: Kanban boards, slash-command editor, nested wiki pages, real-time presence indicators, inline comments/mentions, autosave with version history, smart notifications, daily digests.
- **Tech**: Next.js, TypeScript, Supabase Postgres with Row Level Security, Supabase Realtime.
- **Target audience**: Software dev teams, startups, agencies, remote teams, founders tired of juggling Jira + Notion + Slack.
- **Positioning**: "Jira, Notion, and Slack had a fast, opinionated child." Eliminates tool-switching friction.
- **Competitors**: Notion, Jira, Linear, ClickUp, Asana, Monday.com

### Blocfeed
- **URL**: https://blocfeed.com
- **What it is**: A free, lightweight in-app bug reporting NPM package. Users click any element, submit annotated screenshots with full technical context. AI auto-triages, categorizes, and clusters reports.
- **Key features**: Element-level selection (captures CSS selector, coordinates, URL), AI-powered triage (categorization, priority, sentiment, clustering), annotated screenshots, integrations (Slack, Linear, Jira, email), trend/spike detection.
- **Tech**: ~8KB bundle, async loading, framework-agnostic (React, Next.js, Vue, Svelte, Angular).
- **Target audience**: Vibe coders/AI developers (Cursor, Bolt, v0 users), product managers, developers needing precise bug reproduction.
- **Positioning**: Free forever, setup in 2 minutes, reports in 10 seconds. Element-level precision vs competitors. Privacy-first (no tracking, no fingerprinting).
- **Competitors**: Marker.io, BugHerd, Usersnap

---

## Keywords

### Blocpad-related
- project management tool
- team collaboration software
- Notion alternative
- Jira alternative
- all-in-one workspace
- real-time collaboration
- kanban board tool
- remote team tools
- task management for startups
- wiki documentation tool
- project management for developers

### Blocfeed-related
- bug reporting tool
- in-app feedback widget
- user feedback tool
- bug tracking for developers
- visual bug reporting
- AI bug triage
- free bug reporting tool
- QA testing tools
- user testing feedback
- developer tools
- vibe coding tools
- ship fast bug reporting

### General / Community
- indie hacker tools
- SaaS tools for startups
- developer productivity
- building in public
- side project tools
- startup tech stack
- solopreneur tools

---

## Engagement Behavior Rules

### Action Mixing
Never repeat the same pattern. Vary actions randomly using these approximate weights:

| Action Pattern       | Weight |
|---------------------|--------|
| Like/upvote only     | 22%    |
| Comment/reply only   | 18%    |
| Like + comment       | 20%    |
| Follow/join          | 13%    |
| Skip entirely        | 12%    |
| Save/bookmark        | 10%    |
| Share/retweet/boost  | 5%     |

### Platform-Specific Action Counts
| Platform      | Actions per session | Notes                              |
|--------------|--------------------|------------------------------------|
| Twitter       | 100-150            | Very high volume: likes, replies, retweets, follows, 2-3 daily posts |
| Reddit        | 10-15              | Join subs, follow rules, 1 post per sub max |
| Dev.to        | 10-20              | Post articles, comments, likes, follows |
| Product Hunt  | 3-8                | Upvotes, comments, saves           |
| Indie Hackers | 3-8                | Comments, likes                    |
| Hacker News   | 6-9                | Upvotes, comments/replies. Grows 20% daily |

### Daily Posting
- **Twitter**: 2-3 original tweets/threads per day (building-in-public, hot takes, questions, tips, engagement bait)
- **Reddit**: 1 post per subreddit per session max (questions, discussions, experiences — NOT promotions)
- **Dev.to**: 1 article per session (tutorials, experience posts, listicles, comparisons)

### Subreddit Rules (Reddit-specific)
- **ALWAYS read subreddit rules before posting or commenting**
- Respect self-promotion policies, flair requirements, and posting guidelines
- If rules ban self-promotion, just give helpful advice — no product mentions

### Human Mimicry
- Add random delays between actions (30s to 5min)
- Vary session length (10-40 minutes)
- Don't engage with every post in a thread — skip some
- Scroll past content sometimes without interacting
- Simulate cursor movement and reading time
- Never perform actions in a perfectly regular pattern
- Short pause (30-90s) between platform switches — don't block

### Promotion Rules
- **ONLY promote when genuinely relevant** to the conversation topic
- **Never lead with product** — always lead with value/insight first
- **Max 1 promotion per 10 engagements** — the other 9 should be pure value
- **Vary promotion style**: sometimes mention by name, sometimes just describe the concept, sometimes share a link, sometimes just hint
- **Never use marketing language** — talk like a user/builder, not a salesperson
- **If the conversation isn't relevant, just add a helpful comment** — no promotion
- **Disclose when appropriate**: "I built something similar..." or "We use X for this..."

### Platform Character Limits & Content Length
Respect each platform's constraints. Never write content that gets truncated or feels out of place for the platform's norms.

| Platform      | Hard Limit           | Ideal Comment Length         | Notes                                                    |
|--------------|----------------------|------------------------------|----------------------------------------------------------|
| Twitter/X     | 280 chars (free), 25K (Premium) | 80-200 chars for replies | Short, punchy. Assume 280 limit unless Premium confirmed. |
| Reddit        | 10,000 chars         | 1-4 sentences (50-300 words) | Longer is fine for advice threads, short for casual subs  |
| Dev.to        | No strict limit      | 1-4 sentences (50-300 words) | Technical and conversational. Reference specifics from the article. |
| Product Hunt  | No strict limit      | 2-5 sentences (30-150 words) | Medium length. Thoughtful but not essays.                 |
| Indie Hackers | No strict limit      | 3-6 sentences (50-250 words) | Can go longer for detailed experience sharing             |

**Rules:**
- ALWAYS check you're within the hard character limit before posting
- On Twitter: count characters. If over 280, cut ruthlessly. No one reads thread replies that are walls of text anyway.
- On Reddit: match the thread energy. Short thread = short reply. Deep discussion = go longer.
- On Product Hunt: don't write an essay on someone's launch. Keep it focused.
- On Indie Hackers: longer is okay when sharing real experience, but don't ramble without substance.

### Human Writing Style — CRITICAL
Every comment, reply, and post MUST be undetectable by AI detection tools (GPTZero, Originality.ai, ZeroGPT, etc). Follow these rules strictly:

**Sentence structure:**
- Vary sentence length wildly — mix very short punchy sentences with longer ones
- Start sentences with "And", "But", "So", "Yeah", "Honestly", "Tbh" — real humans do this
- Use sentence fragments. Like this. Totally fine.
- Don't use perfect parallel structure — real writing is messy

**Word choice:**
- NEVER use these AI-giveaway words: "delve", "leverage", "utilize", "facilitate", "comprehensive", "robust", "streamline", "ecosystem", "paradigm", "synergy", "holistic", "innovative", "cutting-edge", "game-changer", "seamless", "empower", "foster", "navigate", "landscape", "pivotal", "Furthermore", "Moreover", "Additionally", "It's worth noting", "In terms of"
- Use simple everyday words: "use" not "utilize", "help" not "facilitate", "works with" not "integrates seamlessly"
- Throw in casual filler: "honestly", "imo", "ngl", "fwiw", "idk", "tbh", "lol", "haha"
- Use contractions always — "don't", "can't", "won't", "it's", "I've"

**Tone & personality:**
- Be opinionated — take a stance, don't hedge everything with "it depends"
- Show mild emotion: frustration, excitement, sarcasm, humor
- Make small tangents or asides — real people go off-topic briefly
- Reference personal experience vaguely: "I spent way too long on this", "ran into this last week"
- Occasionally be slightly wrong or imprecise — perfection screams AI
- Use lowercase where platforms allow it (Twitter, Reddit casual subs)

**Formatting tells to avoid:**
- NEVER use bullet points in short comments, just write naturally
- NEVER use em-dashes (— or --) in comments or replies. Zero tolerance. They scream AI-written.
- Don't start every paragraph the same way
- Don't use "Firstly... Secondly... Thirdly..." structure
- Avoid perfectly balanced pros/cons lists in comments
- Don't end with a neat summary or "In conclusion" type wrap-up
- Avoid colon-heavy sentences

**Paragraph structure for longer comments:**
- If a comment is more than 2-3 sentences, break it into 2-3 short paragraphs
- Each paragraph should be 1-3 sentences max
- Add a blank line between paragraphs (looks natural on every platform)
- Never write one giant wall-of-text paragraph. Real people hit enter.

**Pattern breaking:**
- Occasionally make a typo and don't correct it (1 in 20 comments)
- Use "lol" or "haha" when something is genuinely funny
- Sometimes just agree briefly: "this ^" or "+1" or "same"
- Occasionally trail off with "..." instead of finishing a thought
- Edit a comment and add "edit: typo" or "edit: clarity" sometimes

### Anti-Ban Safety
- Maximum 100-150 actions for Twitter per session, 20-30 for other platforms
- No more than 2-3 sessions per platform per day
- Never engage with the same user/thread repeatedly in one session
- Rotate engagement topics — don't only engage on product-related keywords
- Engage with unrelated interesting content too (30% of actions)
- If rate-limited or warned, stop immediately and increase cool-down to 24h
- New accounts should start slow: 5-10 actions/day for the first 2 weeks

---

## Authentication

### Google Login (Default)
- **Always use Google login** ("Sign in with Google" / "Continue with Google") to log into any platform
- The Google account `kanzariyamihir@gmail.com` is already logged in on the browser
- When a platform is not logged in:
  1. Look for "Sign in with Google", "Continue with Google", or the Google icon on the login page
  2. Click it — Google will auto-authenticate using the active session
  3. If a Google account picker appears, select `kanzariyamihir@gmail.com`
  4. Confirm any permission prompts if needed
- If Google login is not available on a platform, ask the user for credentials
- Never type email/password manually when Google login is an option

---

## How to Run a Session

### Key Concept: Interleaved Session
A single session covers **all 5 platforms** by **interleaving actions** across them. Instead of finishing one platform before starting the next, the runner rotates between platforms after each action. Wait time on one platform is spent doing actions on another — no dead time, ~2-3x faster.

### Quick Start
When the user says "run", "start", "go", or "run a GTM session", follow this EXACT procedure:

### Step 0: Pre-flight Checks
```bash
cd ~/GTM && python3 -m gtm init    # ensure DB exists
cd ~/GTM && python3 -m gtm status  # show session info
cd ~/GTM && python3 -m gtm alerts  # check for safety warnings
```
Read the output. If promo ratio is high on a platform, skip promotions there.

### Step 1: Initialize Interleaved Runner
```python
from gtm.runner import InterleavedRunner, roll_action
runner = InterleavedRunner('/Users/mihirkanzariya/GTM/gtm.db', '/Users/mihirkanzariya/GTM/state.json')
# Goal is auto-selected by recommend_goal() based on current stats
# No need to set it manually — Claude picks what's needed as a GTM specialist
print(f"Goal: {runner.goal} ({runner.goal_reasoning})")
if runner.reason:
    print(f"Cannot start: {runner.reason}")
else:
    runner.start_all()  # creates sessions for ALL platforms at once
    print(f"Limits: {runner.platform_limits}")
    print(f"Max duration: {runner.max_duration_min} min")
```

### Step 2: Open All Platform Tabs
Before the action loop, open all 5 platforms in separate browser tabs:
- Read each platform's CLAUDE.md: `~/GTM/{platform}/CLAUDE.md`
- Open each platform in a new tab via owl
- Make sure you're logged in on each
- Search for a random keyword on each platform, sorted by New/Recent

### Step 3: Interleaved Action Loop
```python
while not runner.is_done():
    platform = runner.pick_next()  # picks a platform, avoids repeating same one
    if platform is None:
        break
    # Switch to that platform's tab
    # Do 1 action (like, comment, follow, etc)
    action = roll_action()
    # Check promotion: runner.should_promote(platform)
    # Check duplicates: runner.is_duplicate(url)
    # Execute via owl
    runner.record_action(platform, action, url, content='...')
    # Check progress: runner.progress()  -> {'twitter': '3/25', 'reddit': '2/12', ...}
    # NO delay between tab switches — just switch and act
```

**Key points:**
- `pick_next()` automatically avoids repeating the same platform twice in a row
- No platform-switch delay — tab switching IS the natural pause
- The only delay is between actions on the SAME platform (handled by interleaving)
- `runner.progress()` shows live progress like `{'twitter': '5/25', 'reddit': '3/12', ...}`

### Step 4: End Session
After all platforms are done or time limit hit:
```python
runner.finish()  # ends all sessions, updates state
summary = runner.summary()
```

### Step 5: Report
Show the user:
- Which platforms were engaged and how many actions each
- Total comments written vs likes vs skips
- Whether any promotions were included
- Run `python3 -m gtm stats` to show updated weekly report

### IMPORTANT: Human Mimicry During Execution
Between EVERY action, use owl to:
- Move the mouse to random positions (not directly to targets)
- Scroll up/down a bit as if reading
- Sometimes hover over a post without clicking
- Don't click buttons instantly — move to them naturally over 0.5-1.5 seconds
- Vary typing speed if typing comments
- Tab switching itself provides natural 2-5 second pauses — no artificial delays needed

### IMPORTANT: Never Block on Delays
- **Do NOT sleep for long periods** (5+ minutes) — it wastes user time and Claude may timeout
- **No delay between platform switches** — tab switching is instant and natural
- **No cooldown between sessions** — when the user says "run", start immediately.

### CLI Commands
- `python3 -m gtm init` — Initialize database and state file
- `python3 -m gtm status` — Check if session can start (cooldown, daily limit)
- `python3 -m gtm stats` — Weekly report with actions, promos, top comments
- `python3 -m gtm alerts` — Check for warnings (high promo ratio, inactivity, etc)
- `python3 -m gtm calendar` — Show upcoming content calendar (next 7 days)
- `python3 -m gtm keywords` — Show keyword performance per platform (top 5)
- `python3 -m gtm relationships` — Show high-value users (2+ interactions)
- `python3 -m gtm tracking` — Show active reply trackers per platform
- `python3 -m gtm decisions` — Show last 10 decisions with reasoning

### Files
- `~/GTM/gtm.db` — SQLite database (actions, sessions, outcomes, metrics, tracking, keywords, relationships, calendar, decisions)
- `~/GTM/state.json` — Session tracking (count, last session time)

---

## v2 Enhanced Session Flow

### Session Bootstrap (Context Recovery)
At session start, load full context from the decision log so you can pick up where you left off even after session compaction:

```python
from gtm.decisions import get_decision_summary
summary = get_decision_summary('/Users/mihirkanzariya/GTM/gtm.db', days=7)
# Returns: total_actions, comments, promotions, active_trackers,
#          promo_ratios, top_keywords, high_value_relationships,
#          calendar_today, recent_decisions (last 10 with reasoning)
```

Print the summary before starting engagement so you have full context.

### Recording Actions with v2 Parameters
When logging actions, pass extra context for reply tracking and relationships:

```python
runner.record_action(
    platform, action_type, target_url,
    target_title="Post title",
    content="Your comment text",
    promoted_product="blocfeed",       # if promoting
    keywords_matched="bug reporting",  # keyword used to find post
    comment_url="https://...",         # direct URL to your comment (for reply checking)
    author_username="devguy123",       # post author (for relationship tracking)
)
```

- Comments, like_and_comment, and replies are auto-enrolled for reply tracking
- Author interactions are auto-tracked in the relationships table
- Decisions are auto-logged for context recovery

### Twitter Thread Creation
One thread per session max. Check calendar first, then recent threads to avoid repeats:

```python
from gtm.calendar import get_today_content
from gtm.threads import get_recent_threads, log_thread, format_thread

# 1. Check if thread planned today
planned = get_today_content('/Users/mihirkanzariya/GTM/gtm.db', 'twitter')

# 2. Check recent threads (avoid topic repeats within 14 days)
recent = get_recent_threads('/Users/mihirkanzariya/GTM/gtm.db', days=14)

# 3. Pick thread type randomly: 'building_in_public' or 'general_founder'
# 4. Write 3-5 tweets, each under 280 chars
# 5. Post on https://x.com via Owl:
#    - Compose first tweet, post it
#    - Click on posted tweet, reply with tweet 2
#    - Repeat for remaining tweets
#    - Grab URL of first tweet

# 6. Log the thread
tweets = ["Tweet 1 text", "Tweet 2 text", "Tweet 3 text"]
formatted = format_thread(tweets)  # ensures 280 char limit
log_thread(db_path, session_id, 'building_in_public', 'Topic', formatted, first_tweet_url)
```

### Reply Checker Cron (Auto-Follow-Up)
All comments are tracked for replies. Set up the cron checker at session boundaries:

**Session start:**
```python
from gtm.cron import build_reply_checker_prompt, get_cron_expression
# Use CronCreate tool with:
#   schedule: "*/15 * * * *" (every 15 minutes)
#   prompt: build_reply_checker_prompt(db_path)
```

**Session end:**
```python
# Use CronDelete tool to stop the reply checker
```

**How it works:**
- Every comment/reply gets enrolled in `reply_tracking` with `next_check_at = now + 15min`
- Cron fires every 15 minutes, checks due entries
- For each: open the URL, look for replies to our comment
- If reply found: 70% chance we reply back, 30% skip (more human)
- Max 3 checks per comment, then marked `exhausted`
- All decisions logged for context recovery

### Module Reference
```
gtm/
├── db.py              # Schema + queries (11 tables)
├── runner.py          # InterleavedRunner (orchestrates all modules)
├── state.py           # Session state management
├── stats.py           # Weekly reports + alerts
├── cli.py             # CLI commands (9 subcommands)
├── engagement.py      # Reply tracking, follow-up logic, outcome checking
├── threads.py         # Twitter thread logging + formatting
├── analytics.py       # Keyword scoring, peak times, engagement scoring
├── relationships.py   # User tracking across sessions
├── calendar.py        # Content calendar management
├── cron.py            # Reply checker cron prompt builder
├── decisions.py       # Decision logging + session bootstrap context
└── revisits.py        # Post-session reply checking — parsers + orchestrator
```

---

## Intelligence Engine

### Pre-Session Setup (one-time)
```bash
python3 -m gtm niche set-industries ai saas developer-tools productivity
python3 -m gtm niche set-audiences developers indie-hackers founders solopreneurs
python3 -m gtm niche exclude politics crypto celebrity sports finance gaming
python3 -m gtm niche add-product blocpad.com "unified workspace for dev teams"
python3 -m gtm niche add-product blocfeed.com "in-app bug reporting with AI triage"
# Goal is auto-selected — no need to set manually (see Auto-Goal below)
```

### Auto-Goal Selection

The goal is picked automatically by `recommend_goal()` every session based on current stats. **Do NOT set it manually** — Claude acts as a GTM specialist and chooses what's needed.

| Situation | Goal | Reasoning |
|-----------|------|-----------|
| < 50 total actions (early stage) | **visibility** | Need presence first, nobody knows us yet |
| < 4 platforms active this week | **visibility** | Need broader reach across platforms |
| Promo ratio > 8% | **relationships** | Over-promoting, cool down and build trust |
| Low reply rate (< 5%) with 30+ actions | **visibility** | Not enough eyeballs, engagement too low |
| 10+ high-value relationships, promo < 5% | **conversions** | Trust built, safe to convert |
| 100+ actions this week, 0 promotions | **conversions** | Good presence, time to start promoting |
| Otherwise | **balanced** | Healthy mix of all strategies |

The runner prints the chosen goal and reasoning at session start:
```
Goal: visibility (reply rate only 0% with 323 actions, need more visibility)
```

To check what goal would be picked without running a session:
```bash
python3 -m gtm goal    # shows auto-recommend with reasoning
```

To override (rare, only if you know better):
```bash
python3 -m gtm goal set conversions          # force global goal
python3 -m gtm goal set relationships twitter # force per-platform
```

### Phase 1: Discovery Scan (2-3 min, no Owl)

Before engagement, collect signals using WebFetch/WebSearch:

```python
from gtm.collectors import parse_reddit_response, parse_hn_stories, parse_devto_response, build_search_queries, get_niche_subreddits
from gtm.intelligence import store_signals, create_topic, compute_trend_score, compute_opportunity_score

# 1. Fetch Reddit hot posts from niche subreddits
subreddits = get_niche_subreddits(db_path)
for sub in subreddits:
    # WebFetch f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
    # signals = parse_reddit_response(response_json)
    # store_signals(db_path, signals, session_id)

# 2. Fetch HN top stories
# WebFetch "https://hacker-news.firebaseio.com/v0/topstories.json"
# For each story ID: WebFetch f"https://hacker-news.firebaseio.com/v0/item/{id}.json"
# signals = parse_hn_stories(story_objects)
# store_signals(db_path, signals, session_id)

# 3. Fetch Dev.to trending
# WebFetch "https://dev.to/api/articles?top=1&per_page=30"
# signals = parse_devto_response(articles)
# store_signals(db_path, signals, session_id)

# 4. WebSearch for Twitter/X trends
# queries = build_search_queries(db_path)
# For each query: WebSearch(query)

# 5. Claude clusters signals into topics (semantic grouping)
# 6. create_topic() or update_topic_mentions() for each cluster
# 7. compute_trend_score() and compute_opportunity_score() for each topic
```

### Phase 2: Load Briefing

```python
runner = InterleavedRunner(db_path, state_path)
runner.start_all()
briefing = runner.load_briefing()
# briefing contains: topics, weak_signals, opportunities, promo_status, pending_replies, relationships
# Use this context to guide engagement decisions
```

### Phase 3: Engagement (Owl)

Use briefing to guide actions:
- Search using topic key_phrases instead of hardcoded keywords
- Prioritize topics with high opportunity_score
- Post early on weak signals for maximum impact
- Check promo_status before promoting
- Engage with high-value relationships

During engagement, log discovered topics:
```python
runner.discover_topic("twitter", "MCP server adoption", key_phrases=["mcp servers", "tool use"])
```

### Phase 4: Post-Session (automatic)

`runner.finish()` automatically runs:
- `transition_statuses()` — promote topics based on mention thresholds
- `expire_stale()` — expire topics not seen recently
- `update_feedback()` — mark topics with good engagement as "proven"

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

### New CLI Commands
```bash
python3 -m gtm niche           # show/manage niche profile
python3 -m gtm goal            # show/manage goals
python3 -m gtm briefing        # pre-session briefing
python3 -m gtm trends          # active trends with scores
python3 -m gtm signals         # weak signals (early trends)
python3 -m gtm actions         # per-platform action types
```

### New Modules
```
gtm/
├── niche.py           # Niche profile CRUD (industries, audiences, exclusions, products)
├── goals.py           # User-configurable goals (global + per-platform)
├── intelligence.py    # Signal storage, topic clusters, scoring, briefing, feedback
└── collectors.py      # Platform signal parsers (Reddit, HN, Dev.to, GitHub)
```

---

## Per-Platform Config

Each platform subdirectory has its own CLAUDE.md with platform-specific rules. See:
- `reddit/CLAUDE.md`
- `twitter/CLAUDE.md`
- `devto/CLAUDE.md`
- `producthunt/CLAUDE.md`
- `indiehackers/CLAUDE.md`
- `hackernews/CLAUDE.md`
