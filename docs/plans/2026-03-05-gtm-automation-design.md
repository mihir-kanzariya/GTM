# GTM Automation System — Design Document

**Date**: 2026-03-05
**Status**: Approved

## Overview
A folder-based automation system at `~/GTM/` that provides strategy, configuration, and behavioral rules for social media engagement across Reddit, Twitter/X, Product Hunt, and Indie Hackers. The system uses CLAUDE.md files as the configuration layer, with actual execution handled by the "owl" plugin (to be integrated later).

## Goals
1. Increase followers and visibility for Blocpad and Blocfeed
2. Build authentic community presence across 4 platforms
3. Promote products naturally — only when relevant
4. Mimic human behavior to avoid platform bans
5. Vary engagement patterns (like-only, comment-only, mixed, skip)

## Structure
```
~/GTM/
├── CLAUDE.md              # Master: products, keywords, behavior rules
├── docs/plans/            # Design docs
├── reddit/CLAUDE.md       # Reddit-specific strategy
├── twitter/CLAUDE.md      # Twitter/X-specific strategy
├── producthunt/CLAUDE.md  # Product Hunt-specific strategy
└── indiehackers/CLAUDE.md # Indie Hackers-specific strategy
```

## Products
- **Blocpad** (blocpad.com): Unified workspace — task management + docs + collaboration
- **Blocfeed** (blocfeed.com): Free in-app bug reporting with AI triage

## Keywords
Auto-derived from products covering: project management, bug reporting, dev tools, Notion/Jira alternatives, indie hacker tools, SaaS, startup tech stack, etc.

## Behavior Design
- **Action mixing**: 25% like-only, 20% comment-only, 25% like+comment, 15% skip, 5% share, 10% save
- **Promotion ratio**: Max 1 in 10 engagements; rest is pure value
- **Human mimicry**: Random delays (30s-5min), varied sessions, natural scrolling, cursor movement
- **Anti-ban**: 20-30 actions/platform/session, 2-3 sessions/day max, rotate topics, engage with unrelated content

## Execution
Handled by "owl" plugin (user will integrate separately). CLAUDE.md files serve as the configuration and strategy layer.

## Next Steps
- User integrates owl plugin for browser automation
- Keywords can be updated per-session in master CLAUDE.md
- Products section updated as features ship
