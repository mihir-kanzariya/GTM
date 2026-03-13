# GTM Automation

Automated Go-To-Market engagement system powered by Claude Code. Runs interleaved sessions across 6 platforms, auto-picks goals based on stats, tracks replies, and builds relationships — all from a single "run" command.

## What It Does

- **Interleaved multi-platform sessions** — engages on Reddit, Twitter/X, Dev.to, Product Hunt, Indie Hackers, and Hacker News simultaneously
- **Auto-goal selection** — analyzes your stats and picks the right strategy (visibility, conversions, relationships, or balanced)
- **Intelligence engine** — scans trending topics, scores opportunities, builds pre-session briefings
- **Reply revisit queue** — tracks your comments, checks for replies via WebFetch, responds via Owl
- **Human mimicry** — random delays, varied actions, natural writing style, anti-ban safety
- **Promotion safety** — enforces max 1:10 promo ratio, logs decisions for context recovery

## Setup

```bash
git clone <repo-url> ~/GTM
cd ~/GTM
python3 -m gtm init
```

No pip install needed. Uses only Python standard library (sqlite3, json, os, datetime).

**Requirements:**
- Python 3.9+
- Claude Code (with Owl MCP plugin for screen automation)

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
python3 -m gtm niche set-industries ai saas developer-tools
python3 -m gtm niche set-audiences developers founders
python3 -m gtm niche add-product blocfeed.com "bug reporting tool"
python3 -m gtm actions                 # View per-platform action types and weights
```

## How It Works

### Session Flow

```
Step 0: Pre-flight (status, alerts, briefing)
Step 1: Discovery scan — WebFetch Reddit/HN/Dev.to for trending topics
Step 2: Initialize runner — auto-picks goal, creates sessions for all platforms
Step 3: Open platform tabs, interleaved engagement loop
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

1. Checks all due comments via WebFetch (no screen automation for checking)
2. If someone replied → responds via Owl
3. If no reply → schedules next check with escalating interval
4. After 3 failed checks (15 min → 15 min → 30 min) → drops it

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

## Products

This system promotes two products contextually (max 1:10 ratio):

- **[Blocpad](https://blocpad.com)** — Unified workspace for dev teams (Kanban + Docs + Chat)
- **[Blocfeed](https://blocfeed.com)** — Free in-app bug reporting with AI triage
