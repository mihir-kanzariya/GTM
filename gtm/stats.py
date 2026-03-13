from datetime import datetime, timedelta

from gtm.db import get_connection
from gtm.state import load_state, PLATFORMS


def weekly_report(db_path):
    conn = get_connection(db_path)
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()

    lines = []
    today = datetime.utcnow().strftime("%b %d")
    week_ago_str = (datetime.utcnow() - timedelta(days=7)).strftime("%b %d")
    lines.append(f"=== GTM Weekly Report ({week_ago_str} - {today}) ===")
    lines.append("")
    header = f"{'Platform':<15} {'Actions':>7}  {'Comments':>8}  {'Promos':>6}  {'Ratio':>7}  {'Sessions':>8}"
    lines.append(header)
    lines.append("-" * len(header))

    total_actions = 0
    total_comments = 0
    total_promos = 0
    total_sessions = 0

    for platform in PLATFORMS:
        row = conn.execute(
            """SELECT
                 COUNT(*) as actions,
                 COALESCE(SUM(CASE WHEN action_type IN ('comment','reply') THEN 1 ELSE 0 END), 0) as comments,
                 COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
               FROM actions
               WHERE platform = ? AND created_at > ?""",
            (platform, week_ago),
        ).fetchone()

        sess = conn.execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE platform = ? AND started_at > ?",
            (platform, week_ago),
        ).fetchone()

        actions = row["actions"]
        comments = row["comments"]
        promos = row["promos"]
        sessions = sess["cnt"]

        ratio_str = f"1:{actions/promos:.1f}" if promos > 0 else "0:0"

        display_name = {
            "reddit": "Reddit",
            "twitter": "Twitter",
            "producthunt": "Product Hunt",
            "indiehackers": "Indie Hackers",
            "devto": "Dev.to",
            "hackernews": "Hacker News",
        }.get(platform, platform)

        lines.append(
            f"{display_name:<15} {actions:>7}  {comments:>8}  {promos:>6}  {ratio_str:>7}  {sessions:>8}"
        )

        total_actions += actions
        total_comments += comments
        total_promos += promos
        total_sessions += sessions

    lines.append("-" * len(header))
    total_ratio = f"1:{total_actions/total_promos:.1f}" if total_promos > 0 else "0:0"
    lines.append(
        f"{'TOTAL':<15} {total_actions:>7}  {total_comments:>8}  {total_promos:>6}  {total_ratio:>7}  {total_sessions:>8}"
    )

    lines.append("")
    safe = all(
        conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) * 1.0 / MAX(COUNT(*), 1)
               FROM actions WHERE platform = ? AND created_at > ?""",
            (p, week_ago),
        ).fetchone()[0] <= 0.1
        for p in PLATFORMS
    )
    lines.append(f"Promotion Safety: {'OK' if safe else 'WARNING - ratio too high'}")

    lines.append("")
    lines.append("=== Top Performing Comments ===")
    top = conn.execute(
        """SELECT a.platform, a.content_written, o.upvotes, o.replies
           FROM actions a
           JOIN outcomes o ON o.action_id = a.id
           WHERE a.created_at > ? AND a.content_written IS NOT NULL
           ORDER BY o.upvotes + o.replies DESC
           LIMIT 5""",
        (week_ago,),
    ).fetchall()

    if top:
        for i, row in enumerate(top, 1):
            snippet = row["content_written"][:40] + "..." if len(row["content_written"]) > 40 else row["content_written"]
            lines.append(f'{i}. [{row["platform"]}] "{snippet}" - {row["upvotes"]} upvotes, {row["replies"]} replies')
    else:
        lines.append("(no outcome data yet)")

    conn.close()
    return "\n".join(lines)


def get_alerts(db_path, state_path):
    alerts = []
    state = load_state(state_path)
    conn = get_connection(db_path)
    now = datetime.utcnow()

    # Per-platform alerts (activity gaps, promo ratios)
    for platform in PLATFORMS:
        display = {
            "reddit": "Reddit", "twitter": "Twitter",
            "producthunt": "Product Hunt", "indiehackers": "Indie Hackers",
            "devto": "Dev.to", "hackernews": "Hacker News",
        }.get(platform, platform)

        # Check for inactivity
        last_action = conn.execute(
            "SELECT MAX(created_at) as last FROM actions WHERE platform = ?",
            (platform,),
        ).fetchone()
        if last_action and last_action["last"]:
            last_dt = datetime.fromisoformat(last_action["last"])
            gap_days = (now - last_dt).days
            if gap_days >= 3:
                alerts.append(f"No {display} activity in {gap_days} days")

        # Check promo ratio
        three_days_ago = (now - timedelta(days=3)).isoformat()
        row = conn.execute(
            """SELECT COUNT(*) as total,
                      COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
               FROM actions WHERE platform = ? AND created_at > ?""",
            (platform, three_days_ago),
        ).fetchone()
        if row["total"] > 0:
            ratio = row["promos"] / row["total"]
            if ratio > 0.2:
                alerts.append(f"CRITICAL: {display} promotion ratio at 1:{1/ratio:.0f} - stop promoting")
            elif ratio > 0.125:
                alerts.append(f"WARNING: {display} promotion ratio at 1:{1/ratio:.0f} - reduce promotions")

    conn.close()
    return alerts
