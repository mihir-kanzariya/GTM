import json
from datetime import datetime, timedelta

from gtm.db import get_connection


# --- Signal Storage ---

def store_signal(db_path, signal, session_id=None):
    """Store a single content signal. Returns its ID."""
    conn = get_connection(db_path)
    cur = conn.execute(
        """INSERT INTO content_signals (platform, source_url, title, text_snippet, author, author_followers, engagement, session_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            signal.get("platform"),
            signal.get("source_url"),
            signal.get("title"),
            signal.get("text_snippet"),
            signal.get("author"),
            signal.get("author_followers", 0),
            signal.get("engagement", 0),
            session_id,
        ),
    )
    conn.commit()
    signal_id = cur.lastrowid
    conn.close()
    return signal_id


def store_signals(db_path, signals, session_id=None):
    """Store multiple signals. Returns list of IDs."""
    return [store_signal(db_path, s, session_id) for s in signals]


# --- Topic Cluster CRUD ---

def create_topic(db_path, data):
    """Create a new topic cluster. Returns its ID."""
    platforms = data.get("platforms_seen", [])
    conn = get_connection(db_path)
    cur = conn.execute(
        """INSERT INTO topic_clusters
           (name, description, key_phrases, platforms_seen, platform_count,
            total_mentions, relevance, authority_score, velocity, last_seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (
            data["name"],
            data.get("description"),
            json.dumps(data.get("key_phrases", [])),
            json.dumps(platforms),
            len(platforms),
            data.get("total_mentions", 0),
            data.get("relevance", "unknown"),
            data.get("authority_score", 0),
            data.get("velocity", 0),
        ),
    )
    conn.commit()
    topic_id = cur.lastrowid
    conn.close()
    return topic_id


def get_topic(db_path, topic_id):
    """Get a single topic by ID. Returns dict or None."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM topic_clusters WHERE id = ?", (topic_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def get_topics_by_status(db_path, status):
    """Get all topics with a given status, ordered by trend_score desc."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM topic_clusters WHERE status = ? ORDER BY trend_score DESC",
        (status,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_topics(db_path):
    """Get all non-expired topics ordered by opportunity_score."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM topic_clusters WHERE status != 'expired' ORDER BY opportunity_score DESC",
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_topic_mentions(db_path, topic_id, new_mentions, new_platforms=None):
    """Add new mentions to a topic and update platforms list."""
    conn = get_connection(db_path)
    topic = conn.execute("SELECT * FROM topic_clusters WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        conn.close()
        return

    current_mentions = topic["total_mentions"] or 0
    current_platforms = json.loads(topic["platforms_seen"] or "[]")

    if new_platforms:
        merged_platforms = list(set(current_platforms + new_platforms))
    else:
        merged_platforms = current_platforms

    conn.execute(
        """UPDATE topic_clusters
           SET total_mentions = ?, platforms_seen = ?, platform_count = ?, last_seen_at = datetime('now')
           WHERE id = ?""",
        (current_mentions + new_mentions, json.dumps(merged_platforms), len(merged_platforms), topic_id),
    )
    conn.commit()
    conn.close()


# --- Trend Scoring ---

def compute_trend_score(db_path, topic_id):
    """Compute and store trend_score for a topic."""
    conn = get_connection(db_path)
    topic = conn.execute("SELECT * FROM topic_clusters WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        conn.close()
        return

    frequency = min(topic["total_mentions"] or 0, 100) / 10  # normalize to 0-10
    velocity = min(max(topic["velocity"] or 0, -5), 5)       # clamp -5 to 5
    authority = min(topic["authority_score"] or 0, 50) / 5    # normalize to 0-10
    platform_div = min(topic["platform_count"] or 0, 6) / 0.6  # normalize to 0-10

    trend_score = (
        frequency * 0.3
        + velocity * 0.4
        + authority * 0.2
        + platform_div * 0.1
    )

    conn.execute("UPDATE topic_clusters SET trend_score = ? WHERE id = ?", (round(trend_score, 2), topic_id))
    conn.commit()
    conn.close()


def compute_opportunity_score(db_path, topic_id, goal="balanced"):
    """Compute and store opportunity_score for a topic."""
    conn = get_connection(db_path)
    topic = conn.execute("SELECT * FROM topic_clusters WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        conn.close()
        return

    trend = topic["trend_score"] or 0

    relevance_map = {"high": 3.0, "medium": 1.5, "low": 0.5, "none": -10, "unknown": 0}
    relevance = relevance_map.get(topic["relevance"], 0)

    engagement = min(topic["engagement_potential"] or 0, 10)
    saturation_penalty = (topic["saturation"] or 0) * 5

    goal_bonus = {
        "visibility": 2 if topic["status"] == "emerging" else 0,
        "conversions": 3 if topic["relevance"] == "high" else 0,
        "relationships": 2,
        "balanced": 1,
    }.get(goal, 1)

    score = trend + relevance + engagement + goal_bonus - saturation_penalty
    conn.execute("UPDATE topic_clusters SET opportunity_score = ? WHERE id = ?", (round(score, 2), topic_id))
    conn.commit()
    conn.close()


# --- Lifecycle ---

def transition_statuses(db_path):
    """Transition topics between status levels based on mentions and velocity."""
    conn = get_connection(db_path)
    # weak -> emerging (8+ mentions AND velocity > 0)
    conn.execute(
        """UPDATE topic_clusters SET status = 'emerging'
           WHERE status = 'weak' AND total_mentions >= 8 AND velocity > 0"""
    )
    # emerging -> confirmed (20+ mentions)
    conn.execute(
        """UPDATE topic_clusters SET status = 'confirmed'
           WHERE status = 'emerging' AND total_mentions >= 20"""
    )
    # any -> cooling (velocity negative, not already cooling/expired)
    conn.execute(
        """UPDATE topic_clusters SET status = 'cooling'
           WHERE status NOT IN ('cooling', 'expired', 'proven') AND velocity < -1"""
    )
    conn.commit()
    conn.close()


def expire_stale(db_path):
    """Expire topics not seen recently."""
    conn = get_connection(db_path)
    now = datetime.utcnow()
    # Weak topics: expire after 3 days without being seen
    cutoff_weak = (now - timedelta(days=3)).isoformat()
    conn.execute(
        """UPDATE topic_clusters SET status = 'expired'
           WHERE status IN ('weak', 'cooling') AND last_seen_at < ?""",
        (cutoff_weak,),
    )
    # Other topics: expire after 5 days without being seen
    cutoff_other = (now - timedelta(days=5)).isoformat()
    conn.execute(
        """UPDATE topic_clusters SET status = 'expired'
           WHERE status NOT IN ('expired', 'proven') AND last_seen_at < ?""",
        (cutoff_other,),
    )
    conn.commit()
    conn.close()


# --- Briefing System ---

from gtm.niche import get_niche, is_excluded_topic
from gtm.goals import get_goals, get_goal_for_platform


def get_weak_signals(db_path):
    """Get weak topics with strong structural signals (multi-platform, rising, authoritative)."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM topic_clusters
           WHERE status = 'weak'
             AND platform_count >= 2
             AND velocity > 0
             AND authority_score >= 3
           ORDER BY velocity DESC
           LIMIT 10""",
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_content_opportunities(db_path, goal="balanced", limit=5):
    """Get top content opportunities sorted by opportunity_score."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM topic_clusters
           WHERE status != 'expired' AND relevance IN ('high', 'medium')
           ORDER BY opportunity_score DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_briefing(db_path, state_path, platforms=None):
    """Build a full pre-session briefing from all tables."""
    from gtm.state import PLATFORMS as ALL_PLATFORMS

    target_platforms = platforms or ALL_PLATFORMS
    goals = get_goals(state_path)
    niche = get_niche(db_path)
    goal = goals["default"]

    # Active topics
    topics = get_active_topics(db_path)

    # Weak signals
    weak = get_weak_signals(db_path)

    # Opportunities (score with current goal)
    for t in topics:
        compute_opportunity_score(db_path, t["id"], goal)
    opportunities = get_content_opportunities(db_path, goal)

    # Promo safety per platform
    conn = get_connection(db_path)
    promo_status = {}
    three_days_ago = (datetime.utcnow() - timedelta(days=3)).isoformat()
    for p in target_platforms:
        row = conn.execute(
            """SELECT COUNT(*) as total,
                      COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
               FROM actions WHERE platform = ? AND created_at > ?""",
            (p, three_days_ago),
        ).fetchone()
        if row["total"] > 0:
            ratio = row["promos"] / row["total"]
            promo_status[p] = "blocked" if ratio > 0.08 else "safe"
        else:
            promo_status[p] = "safe"

    # Pending replies
    pending = conn.execute(
        "SELECT * FROM reply_tracking WHERE status = 'active' ORDER BY next_check_at LIMIT 10"
    ).fetchall()

    # High-value relationships
    relationships = {}
    for p in target_platforms:
        users = conn.execute(
            """SELECT username, interaction_count, relationship_score
               FROM relationships WHERE platform = ? AND interaction_count >= 2
               ORDER BY relationship_score DESC LIMIT 5""",
            (p,),
        ).fetchall()
        if users:
            relationships[p] = [dict(u) for u in users]

    conn.close()

    return {
        "goal": goal,
        "goals_by_platform": goals["platforms"],
        "niche": niche,
        "topics": [dict(t) for t in topics[:20]],
        "weak_signals": [dict(s) for s in weak],
        "opportunities": [dict(o) for o in opportunities],
        "promo_status": promo_status,
        "pending_replies": [dict(r) for r in pending],
        "relationships": relationships,
    }


def update_feedback(db_path):
    """Post-session learning: promote topics with good engagement to 'proven'."""
    conn = get_connection(db_path)
    # Topics we've posted about with good engagement → proven
    conn.execute(
        """UPDATE topic_clusters SET status = 'proven'
           WHERE status IN ('emerging', 'confirmed')
             AND times_we_posted > 0
             AND avg_engagement > 5.0"""
    )
    conn.commit()
    conn.close()


def record_topic_engagement(db_path, topic_id, engagement_score):
    """Record that we posted about a topic and how it performed."""
    conn = get_connection(db_path)
    topic = conn.execute("SELECT * FROM topic_clusters WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        conn.close()
        return
    posted = (topic["times_we_posted"] or 0) + 1
    prev_avg = topic["avg_engagement"] or 0
    new_avg = ((prev_avg * (posted - 1)) + engagement_score) / posted
    conn.execute(
        "UPDATE topic_clusters SET times_we_posted = ?, avg_engagement = ? WHERE id = ?",
        (posted, round(new_avg, 2), topic_id),
    )
    conn.commit()
    conn.close()
