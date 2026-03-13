# GTM Automation

Automated Go-To-Market engagement system powered by [Claude Code](https://claude.com/claude-code) and [OpenOwl](https://openowl.dev). Runs interleaved sessions across 6 platforms, auto-picks goals based on stats, tracks replies, and builds relationships — all from a single "run" command.

## What It Does

- **Interleaved multi-platform sessions** — engages on Reddit, Twitter/X, Dev.to, Product Hunt, Indie Hackers, and Hacker News simultaneously
- **Auto-goal selection** — analyzes your stats and picks the right strategy (visibility, conversions, relationships, or balanced)
- **Intelligence engine** — scans trending topics, scores opportunities, builds pre-session briefings
- **Reply revisit queue** — tracks your comments, checks for replies, responds automatically
- **Human mimicry** — random delays, varied actions, natural writing style, anti-ban safety
- **Promotion safety** — enforces max 1:10 promo ratio, logs decisions for context recovery

## Platform Support

**Tested and works well on macOS (Apple Silicon and Intel).** Windows is not tested and may have issues with OpenOwl screen automation. Linux is untested.

**Best experience:** Run this with [Claude Code](https://claude.com/claude-code) — it reads `CLAUDE.md` natively, handles multi-step sessions, and integrates directly with OpenOwl as an MCP server. Other AI coding tools may work but Claude Code is what this was built for and tested with.

## Prerequisites

- **macOS** (recommended, tested)
- **Python 3.11+** (tested with 3.11.11)
- **[Claude Code](https://claude.com/claude-code)** — CLI agent that runs the sessions
- **[OpenOwl](https://openowl.dev) v0.3.5+** — MCP plugin for screen automation (browser control, clicking, typing, screenshots)

### Installing OpenOwl

OpenOwl is required for browser automation (engaging on platforms, posting comments, clicking buttons, etc.). Install it as an MCP server in Claude Code:

```bash
# Install OpenOwl MCP server (v0.3.5 or higher recommended)
npx openowl@latest
# Follow full setup at: https://openowl.dev
```

> **Tested with OpenOwl v0.3.5.** Older versions (< 0.2.2) lack macOS support. Make sure you're on v0.3.5+ for the best experience on macOS.

Make sure OpenOwl is configured and running as an MCP server before starting sessions. Without it, Claude Code can analyze and plan but cannot interact with platforms.

### Python Version

This project uses **only Python standard library** — no pip dependencies. Just make sure you have Python 3.9 or higher:

```bash
python3 --version  # should be 3.9+
```

## Setup

```bash
git clone https://github.com/mihir-kanzariya/GTM.git ~/GTM
cd ~/GTM
python3 -m gtm init
```

### Configure Your Niche

Before your first session, set up your niche profile:

```bash
python3 -m gtm niche set-industries ai saas developer-tools
python3 -m gtm niche set-audiences developers founders indie-hackers
python3 -m gtm niche add-product site.com "short description"
```

## Usage

Open Claude Code in `~/GTM` and say **"run"**. That's it.

Claude reads `CLAUDE.md`, auto-picks the goal, runs all platforms, checks for replies, and reports results.

### CLI Commands

```bash
# Setup
python3 -m gtm init                    # Create DB + state file

# Pre-session
python3 -m gtm status                  # Session status, per-platform actions today
python3 -m gtm alerts                  # Safety warnings (promo ratio, inactivity)
python3 -m gtm briefing                # Pre-session intelligence summary
python3 -m gtm goal                    # View goals + auto-recommendation

# Monitoring
python3 -m gtm stats                   # Weekly report with top comments
python3 -m gtm tracking                # Reply tracking — upcoming checks, recent results
python3 -m gtm trends                  # Active topics with trend/opportunity scores
python3 -m gtm signals                 # Early weak signals to post on
python3 -m gtm keywords                # Keyword performance per platform
python3 -m gtm relationships           # High-value users (2+ interactions)
python3 -m gtm decisions               # Recent decisions with reasoning
python3 -m gtm calendar                # Upcoming content calendar

# Config
python3 -m gtm niche                   # View/manage niche profile
python3 -m gtm actions                 # View per-platform action types and weights
```

## How It Works

### Session Flow

```
Step 0: Pre-flight (status, alerts, briefing)
Step 1: Discovery scan — fetches Reddit/HN/Dev.to for trending topics
Step 2: Initialize runner — auto-picks goal, creates sessions for all platforms
Step 3: Open platform tabs, interleaved engagement loop via OpenOwl
Step 4: Session ends — runner.finish()
Step 5: Revisit phase — check comments for replies (15→15→30 min escalation)
Step 6: Report results
```

### Auto-Goal Selection

The system picks the right goal every session based on your data:

| Situation | Goal | Why |
|-----------|------|-----|
| < 50 total actions | visibility | Early stage, need presence |
| < 4 platforms active | visibility | Need broader reach |
| Promo ratio > 8% | relationships | Cool down, build trust |
| Low reply rate (< 5%) | visibility | Not enough eyeballs |
| 10+ high-value relationships | conversions | Leverage built trust |
| 100+ actions, 0 promos | conversions | Safe to start promoting |
| Otherwise | balanced | Mix of everything |

### Reply Revisit Queue

When you post a comment, it's auto-tracked. After each session:

1. Checks all due comments via API calls (no screen automation for checking)
2. If someone replied, responds via OpenOwl
3. If no reply, schedules next check with escalating interval
4. After 3 failed checks (15 min → 15 min → 30 min), drops it

## Architecture

```
gtm/
├── runner.py          # InterleavedRunner — orchestrates all platforms
├── db.py              # SQLite schema (14 tables)
├── state.py           # Session state (PLATFORMS list, cooldowns)
├── cli.py             # CLI entry point (15 commands)
├── stats.py           # Weekly reports + alerts
├── engagement.py      # Reply tracking, escalating intervals
├── revisits.py        # Post-session reply checking — parsers + orchestrator
├── intelligence.py    # Topic clusters, scoring, briefing, feedback
├── collectors.py      # Platform signal parsers (Reddit, HN, Dev.to, GitHub)
├── niche.py           # Niche profile CRUD
├── goals.py           # Auto-goal recommendation + manual overrides
├── decisions.py       # Decision logging + context recovery
├── relationships.py   # User tracking across sessions
├── analytics.py       # Keyword scoring, peak times
├── threads.py         # Twitter thread logging
├── calendar.py        # Content calendar
└── cron.py            # Reply checker cron prompt builder
```

### Data

- `gtm.db` — SQLite database (14 tables: sessions, actions, outcomes, reply_tracking, topics, signals, relationships, keywords, calendar, decisions, etc.)
- `state.json` — Session state (last session, count, goals)

## Platform Config

Each platform has its own rules in `{platform}/CLAUDE.md`:
- `reddit/CLAUDE.md`
- `twitter/CLAUDE.md`
- `devto/CLAUDE.md`
- `producthunt/CLAUDE.md`
- `indiehackers/CLAUDE.md`
- `hackernews/CLAUDE.md`

## Adding Your Products

This repo ships with no products configured. You define them once via CLI and everything else picks them up automatically.

### Step 1: Add your products
```bash
python3 -m gtm niche add-product myapp.com "project management tool for remote teams"
python3 -m gtm niche add-product myblog.com "developer blog about building in public"
```

### Step 2: Set your niche (so Claude finds relevant posts)
```bash
python3 -m gtm niche set-industries ai saas developer-tools
python3 -m gtm niche set-audiences developers founders indie-hackers
python3 -m gtm niche exclude politics crypto celebrity sports
```

### Step 3: Verify your setup
```bash
python3 -m gtm niche
```

That's it. When you run a session, Claude automatically:
- Loads your products from the DB via `load_briefing()`
- Uses them for contextual promotion (max 1 promo per 10 engagements)
- Checks promo ratio per platform before mentioning any product
- Logs which product was promoted in each action for tracking

No need to edit CLAUDE.md or any config files — everything reads from the database.

## Customization

- **Engagement rules** — adjust action weights, session limits, promotion ratio in `CLAUDE.md`
- **Writing style** — modify tone, platform-specific behavior
- **Niche profile** — set industries, audiences, and exclusions via CLI

## License

MIT
