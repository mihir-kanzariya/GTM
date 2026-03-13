#!/usr/bin/env python3
"""GTM Automation CLI.

Usage:
    python3 -m gtm init          Initialize database and state
    python3 -m gtm status        Show current session state
    python3 -m gtm stats         Show weekly stats report
    python3 -m gtm alerts        Show active alerts
    python3 -m gtm niche         Manage niche profile
    python3 -m gtm goal          Manage session goals
    python3 -m gtm briefing      Show pre-session briefing
    python3 -m gtm trends        Show active trends
    python3 -m gtm signals       Show weak signals
"""

import argparse
import os
import sys

GTM_DIR = os.path.expanduser("~/GTM")
DB_PATH = os.path.join(GTM_DIR, "gtm.db")
STATE_PATH = os.path.join(GTM_DIR, "state.json")


def cmd_init(args):
    from gtm.db import init_db
    from gtm.state import load_state
    init_db(DB_PATH)
    load_state(STATE_PATH)
    print("Database initialized at", DB_PATH)
    print("State initialized at", STATE_PATH)


def cmd_status(args):
    from datetime import datetime, timedelta
    from gtm.state import load_state, can_start_session, PLATFORMS
    from gtm.db import get_connection

    state = load_state(STATE_PATH)
    print("=== Session Status ===")

    running_since = state.get("running_since")
    running_platforms = state.get("running_platforms")
    if running_since and running_platforms:
        elapsed = (datetime.utcnow() - datetime.fromisoformat(running_since.rstrip("Z"))).total_seconds() / 60
        print(f"  Status:            RUNNING ({int(elapsed)}m)")
        print(f"  Platforms:         {', '.join(running_platforms)}")
        print(f"  Started at:        {running_since[:16]}")
    else:
        print(f"  Status:            IDLE")
        print(f"  Last session:      {state.get('last_session', 'never')[:16]}")

    print(f"  Sessions today:    {state.get('session_count_today', 0)}")
    print()

    conn = get_connection(DB_PATH)
    now = datetime.utcnow()
    today_start = now.strftime("%Y-%m-%d") + "T00:00:00"

    display_names = {
        "reddit": "Reddit", "twitter": "Twitter",
        "producthunt": "Product Hunt", "indiehackers": "Indie Hackers",
        "devto": "Dev.to", "hackernews": "Hacker News",
    }

    header = f"{'Platform':<15} {'Today':>7}  {'Last Active':>16}  {'Sessions':>8}"
    print(header)
    print("-" * len(header))

    total_today = 0
    total_sessions = 0

    for platform in PLATFORMS:
        name = display_names.get(platform, platform)

        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM actions WHERE platform = ? AND created_at > ?",
            (platform, today_start),
        ).fetchone()
        today_count = row["cnt"]

        sess = conn.execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE platform = ? AND started_at > ?",
            (platform, today_start),
        ).fetchone()
        sessions_today = sess["cnt"]

        last = conn.execute(
            "SELECT MAX(created_at) as last FROM actions WHERE platform = ?",
            (platform,),
        ).fetchone()
        if last and last["last"]:
            last_dt = datetime.fromisoformat(last["last"])
            gap = now - last_dt
            if gap.days == 0:
                last_str = last["last"][11:16] + " today"
            elif gap.days == 1:
                last_str = "yesterday"
            else:
                last_str = f"{gap.days}d ago"
        else:
            last_str = "never"

        print(f"{name:<15} {today_count:>7}  {last_str:>16}  {sessions_today:>8}")
        total_today += today_count
        total_sessions += sessions_today

    print("-" * len(header))
    print(f"{'TOTAL':<15} {total_today:>7}  {'':>16}  {total_sessions:>8}")
    conn.close()

    print()
    if running_since and running_platforms:
        print(f"Session in progress — {', '.join(running_platforms)}")
    else:
        ok, reason = can_start_session(state)
        print(f"Status: READY — all platforms will be covered in next session")


def cmd_stats(args):
    from gtm.stats import weekly_report
    print(weekly_report(DB_PATH))


def cmd_alerts(args):
    from gtm.stats import get_alerts
    alerts = get_alerts(DB_PATH, STATE_PATH)
    if alerts:
        print("=== Alerts ===")
        for a in alerts:
            print(f"  - {a}")
    else:
        print("No alerts. All good.")


def cmd_calendar(args):
    from gtm.calendar import get_upcoming
    upcoming = get_upcoming(DB_PATH, days=7)
    if upcoming:
        print("=== Content Calendar ===")
        for item in upcoming:
            print(f"  [{item['scheduled_for']}] {item['platform']}/{item['content_type']}: {item['topic']}")
    else:
        print("No upcoming content planned.")


def cmd_keywords(args):
    from gtm.analytics import get_weighted_keywords
    from gtm.state import PLATFORMS
    print("=== Keyword Performance ===")
    found = False
    for p in PLATFORMS:
        kws = get_weighted_keywords(DB_PATH, p, n=5)
        if kws:
            found = True
            print(f"\n  {p}:")
            for kw, score in kws:
                print(f"    {kw}: {score:.1f}")
    if not found:
        print("  (no keyword data yet)")


def cmd_relationships(args):
    from gtm.relationships import get_high_value_users
    from gtm.state import PLATFORMS
    print("=== High-Value Relationships ===")
    found = False
    for p in PLATFORMS:
        users = get_high_value_users(DB_PATH, p, min_interactions=2)
        if users:
            found = True
            print(f"\n  {p}:")
            for u in users:
                print(f"    @{u['username']} ({u['interaction_count']} interactions, score {u['relationship_score']:.0f})")
    if not found:
        print("  (no high-value relationships yet)")


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


def cmd_decisions(args):
    from gtm.decisions import get_recent_decisions
    decisions = get_recent_decisions(DB_PATH, limit=10)
    if decisions:
        print("=== Recent Decisions ===")
        for d in decisions:
            platform = d.get('platform') or 'global'
            print(f"  [{d['category']}] ({platform}) {d['decision']}")
            if d.get('reasoning'):
                print(f"    Why: {d['reasoning']}")
    else:
        print("No decisions logged yet.")


def cmd_niche(args):
    from gtm.niche import get_niche, set_niche_field, add_product

    if args.action == "set-industries":
        set_niche_field(DB_PATH, "industries", args.values)
        print(f"Industries set: {args.values}")
    elif args.action == "set-audiences":
        set_niche_field(DB_PATH, "audiences", args.values)
        print(f"Audiences set: {args.values}")
    elif args.action == "exclude":
        set_niche_field(DB_PATH, "exclude", args.values)
        print(f"Excluded: {args.values}")
    elif args.action == "add-product":
        if len(args.values) < 2:
            print("Usage: gtm niche add-product <url> <description>")
            return
        add_product(DB_PATH, args.values[0], " ".join(args.values[1:]))
        print(f"Product added: {args.values[0]}")
    else:
        niche = get_niche(DB_PATH)
        print("=== Niche Profile ===")
        print(f"  Industries:  {', '.join(niche['industries']) or '(not set)'}")
        print(f"  Audiences:   {', '.join(niche['audiences']) or '(not set)'}")
        print(f"  Exclude:     {', '.join(niche['exclude']) or '(not set)'}")
        if niche["products"]:
            print(f"  Products:")
            for p in niche["products"]:
                print(f"    {p['url']} — {p['desc']}")
        else:
            print(f"  Products:    (none)")


def cmd_goal(args):
    from gtm.goals import get_goals, set_goal, VALID_GOALS

    if args.action == "set":
        if not args.values:
            print(f"Usage: gtm goal set <{'|'.join(VALID_GOALS)}> [platform]")
            return
        goal = args.values[0]
        platform = args.values[1] if len(args.values) > 1 else None
        try:
            set_goal(STATE_PATH, goal, platform)
            if platform:
                print(f"Goal for {platform}: {goal}")
            else:
                print(f"Default goal: {goal}")
        except ValueError as e:
            print(f"Error: {e}")
    else:
        from gtm.goals import recommend_goal
        goals = get_goals(STATE_PATH)
        print("=== Goals ===")
        print(f"  Default: {goals['default']}")
        if goals["platforms"]:
            for p, g in goals["platforms"].items():
                print(f"  {p}: {g}")
        rec, reason = recommend_goal(DB_PATH, STATE_PATH)
        print(f"\n  Auto-recommend: {rec}")
        print(f"  Why: {reason}")
        print(f"\nValid goals: {', '.join(VALID_GOALS)}")


def cmd_briefing(args):
    import json
    from gtm.intelligence import get_briefing

    briefing = get_briefing(DB_PATH, STATE_PATH)
    print(f"=== Pre-Session Briefing (goal: {briefing['goal']}) ===\n")

    if briefing["niche"]["industries"]:
        print(f"Niche: {', '.join(briefing['niche']['industries'])}")
    print()

    if briefing["opportunities"]:
        print("Top Opportunities:")
        for t in briefing["opportunities"][:5]:
            phrases = json.loads(t["key_phrases"]) if t["key_phrases"] else []
            print(f"  [{t['status']}] {t['name']} (score: {t['opportunity_score']:.1f})")
            if phrases:
                print(f"    Search: {', '.join(phrases[:3])}")
        print()

    if briefing["weak_signals"]:
        print("Weak Signals (post early):")
        for s in briefing["weak_signals"][:5]:
            print(f"  {s['name']} — {s['total_mentions']} mentions, {s['platform_count']} platforms, velocity: {s['velocity']:.1f}")
        print()

    if briefing["promo_status"]:
        blocked = [p for p, s in briefing["promo_status"].items() if s == "blocked"]
        if blocked:
            print(f"Promo blocked on: {', '.join(blocked)}")
        else:
            print("Promo: safe on all platforms")
        print()

    if briefing["pending_replies"]:
        print(f"Pending replies: {len(briefing['pending_replies'])}")
        print()

    if briefing["relationships"]:
        print("High-value users:")
        for p, users in briefing["relationships"].items():
            names = [f"@{u['username']} ({u['interaction_count']}x)" for u in users[:3]]
            print(f"  {p}: {', '.join(names)}")


def cmd_trends(args):
    from gtm.intelligence import get_active_topics

    topics = get_active_topics(DB_PATH)
    if not topics:
        print("No active topics. Run a discovery scan first.")
        return

    print("=== Active Trends ===\n")
    header = f"  {'Topic':<30} {'Status':<12} {'Mentions':>8} {'Plat':>4} {'Vel':>6} {'Trend':>6} {'Opp':>6}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for t in topics[:20]:
        print(f"  {t['name'][:30]:<30} {t['status']:<12} {t['total_mentions']:>8} {t['platform_count']:>4} {(t['velocity'] or 0):>6.1f} {(t['trend_score'] or 0):>6.1f} {(t['opportunity_score'] or 0):>6.1f}")


def cmd_signals(args):
    import json
    from gtm.intelligence import get_weak_signals

    signals = get_weak_signals(DB_PATH)
    if not signals:
        print("No weak signals detected. Run a discovery scan to collect data.")
        return

    print("=== Weak Signals (Early Trends) ===\n")
    for s in signals:
        platforms = json.loads(s["platforms_seen"]) if s["platforms_seen"] else []
        print(f"  {s['name']}")
        print(f"    Mentions: {s['total_mentions']} | Platforms: {', '.join(platforms)} | Velocity: {s['velocity']:.1f}")
        print(f"    Authority: {s['authority_score']:.0f} | Relevance: {s['relevance']}")
        print()


def cmd_actions(args):
    from gtm.runner import PLATFORM_ACTIONS
    from gtm.state import PLATFORMS

    display_names = {
        "reddit": "Reddit", "twitter": "Twitter/X",
        "producthunt": "Product Hunt", "indiehackers": "Indie Hackers",
        "devto": "Dev.to", "hackernews": "Hacker News",
    }

    target = args.platform.lower() if args.platform else None

    for platform in PLATFORMS:
        if target and platform != target:
            continue
        config = PLATFORM_ACTIONS.get(platform, {})
        name = display_names.get(platform, platform)
        lo, hi = config.get("session_range", (3, 8))

        print(f"\n=== {name} ({lo}-{hi} actions/session) ===")
        header = f"  {'Action':<22} {'Weight':>6}  {'Max':>5}  {'Chars':>6}  Description"
        print(header)
        print("  " + "-" * (len(header) - 2))

        for action_type, info in config.get("actions", {}).items():
            weight = info["weight"]
            max_s = str(info["max_per_session"]) if "max_per_session" in info else "-"
            chars = str(info["char_limit"]) if "char_limit" in info else "-"
            desc = info["desc"]
            print(f"  {action_type:<22} {weight:>6}  {max_s:>5}  {chars:>6}  {desc}")

    if not target:
        print(f"\nFilter: python3 -m gtm actions <platform>")
        print(f"Platforms: {', '.join(PLATFORMS)}")


def main():
    parser = argparse.ArgumentParser(description="GTM Automation CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize database and state")
    sub.add_parser("status", help="Show session status")
    sub.add_parser("stats", help="Show weekly report")
    sub.add_parser("alerts", help="Show active alerts")
    sub.add_parser("calendar", help="Show upcoming content calendar")
    sub.add_parser("keywords", help="Show keyword performance")
    sub.add_parser("relationships", help="Show high-value relationships")
    sub.add_parser("tracking", help="Show active reply tracking")
    sub.add_parser("decisions", help="Show recent decisions")
    actions_parser = sub.add_parser("actions", help="Show available actions per platform")
    actions_parser.add_argument("platform", nargs="?", default=None,
                                help="Filter to a specific platform")

    niche_parser = sub.add_parser("niche", help="Manage niche profile")
    niche_parser.add_argument("action", nargs="?", default=None,
                              choices=["set-industries", "set-audiences", "exclude", "add-product"])
    niche_parser.add_argument("values", nargs="*", default=[])

    goal_parser = sub.add_parser("goal", help="Manage session goals")
    goal_parser.add_argument("action", nargs="?", default=None, choices=["set"])
    goal_parser.add_argument("values", nargs="*", default=[])

    sub.add_parser("briefing", help="Show pre-session briefing")
    sub.add_parser("trends", help="Show active trends")
    sub.add_parser("signals", help="Show weak signals")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "init": cmd_init, "status": cmd_status, "stats": cmd_stats,
        "alerts": cmd_alerts, "calendar": cmd_calendar,
        "keywords": cmd_keywords, "relationships": cmd_relationships,
        "tracking": cmd_tracking, "decisions": cmd_decisions,
        "actions": cmd_actions,
        "niche": cmd_niche, "goal": cmd_goal,
        "briefing": cmd_briefing, "trends": cmd_trends, "signals": cmd_signals,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
