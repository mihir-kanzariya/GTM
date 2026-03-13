import json
from datetime import datetime, timedelta

from gtm.db import get_connection


def log_decision(db_path, category, decision, reasoning, context=None,
                 platform=None, session_id=None):
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO decision_log
               (category, platform, decision, reasoning, context, session_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (category, platform, decision, reasoning, context, session_id),
        )
        did = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return did


def get_recent_decisions(db_path, category=None, platform=None, limit=20):
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM decision_log WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if platform:
            query += " AND platform = ?"
            params.append(platform)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_session_decisions(db_path, session_id):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM decision_log WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_decision_summary(db_path, days=7):
    conn = get_connection(db_path)
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as total FROM actions WHERE created_at > ?", (cutoff,)
        ).fetchone()
        total_actions = row["total"]

        row = conn.execute(
            """SELECT COUNT(*) as total FROM actions
               WHERE created_at > ? AND action_type IN ('comment', 'reply', 'like_and_comment')""",
            (cutoff,),
        ).fetchone()
        total_comments = row["total"]

        row = conn.execute(
            """SELECT COUNT(*) as total FROM actions
               WHERE created_at > ? AND promoted_product IS NOT NULL""",
            (cutoff,),
        ).fetchone()
        total_promotions = row["total"]

        trackers = conn.execute(
            "SELECT platform, COUNT(*) as cnt FROM reply_tracking WHERE status = 'active' GROUP BY platform"
        ).fetchall()
        active_trackers = {r["platform"]: r["cnt"] for r in trackers}

        from gtm.state import PLATFORMS
        promo_ratios = {}
        for p in PLATFORMS:
            r = conn.execute(
                """SELECT COUNT(*) as total,
                          COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
                   FROM actions WHERE platform = ? AND created_at > ?""",
                (p, cutoff),
            ).fetchone()
            promo_ratios[p] = round(r["promos"] / r["total"], 3) if r["total"] > 0 else 0.0

        top_keywords = {}
        for p in PLATFORMS:
            kws = conn.execute(
                "SELECT keyword, score FROM keyword_performance WHERE platform = ? ORDER BY score DESC LIMIT 5",
                (p,),
            ).fetchall()
            top_keywords[p] = [(r["keyword"], r["score"]) for r in kws]

        high_value = conn.execute(
            "SELECT platform, username, interaction_count FROM relationships WHERE interaction_count >= 3 ORDER BY interaction_count DESC LIMIT 10"
        ).fetchall()

        today = datetime.utcnow().strftime("%Y-%m-%d")
        calendar_today = conn.execute(
            "SELECT platform, content_type, topic FROM content_calendar WHERE scheduled_for = ? AND status = 'planned'",
            (today,),
        ).fetchall()

        recent = conn.execute(
            "SELECT category, platform, decision, reasoning FROM decision_log ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()
    finally:
        conn.close()

    return {
        "total_actions": total_actions,
        "total_comments": total_comments,
        "total_promotions": total_promotions,
        "active_trackers": active_trackers,
        "promo_ratios": promo_ratios,
        "top_keywords": top_keywords,
        "high_value_relationships": [dict(r) for r in high_value],
        "calendar_today": [dict(r) for r in calendar_today],
        "recent_decisions": [dict(r) for r in recent],
    }
