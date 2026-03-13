import json
import os

VALID_GOALS = ["visibility", "conversions", "relationships", "balanced"]


def _load_state(state_path):
    if not os.path.exists(state_path):
        return {}
    with open(state_path, "r") as f:
        return json.load(f)


def _save_state(state_path, state):
    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def get_goals(state_path):
    """Return goals dict with 'default' and 'platforms' keys."""
    state = _load_state(state_path)
    goals = state.get("goals", {})
    return {
        "default": goals.get("default", "balanced"),
        "platforms": goals.get("platforms", {}),
    }


def set_goal(state_path, goal, platform=None):
    """Set a goal globally or for a specific platform."""
    if goal not in VALID_GOALS:
        raise ValueError(f"Invalid goal '{goal}'. Must be one of: {VALID_GOALS}")
    state = _load_state(state_path)
    if "goals" not in state:
        state["goals"] = {"default": "balanced", "platforms": {}}
    if platform:
        state["goals"]["platforms"][platform] = goal
    else:
        state["goals"]["default"] = goal
    _save_state(state_path, state)


def get_goal_for_platform(state_path, platform):
    """Get the effective goal for a platform (override or default)."""
    goals = get_goals(state_path)
    return goals["platforms"].get(platform, goals["default"])


def recommend_goal(db_path, state_path):
    """Analyze current stats and recommend the best goal as a GTM specialist.

    Logic:
    - Week 1-2 (< 50 total actions): visibility — need presence first
    - Low engagement (< 5% reply rate): visibility — not enough eyeballs
    - Good visibility but 0 promotions: conversions — time to convert
    - High promo ratio (> 8%): relationships — cool down, build trust
    - Strong relationships (10+ high-value users): conversions — leverage trust
    - Default: balanced
    """
    from gtm.db import get_connection
    from datetime import datetime, timedelta

    conn = get_connection(db_path)
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    two_weeks_ago = (datetime.utcnow() - timedelta(days=14)).isoformat()

    # Total actions ever
    total_ever = conn.execute(
        "SELECT COUNT(*) as cnt FROM actions"
    ).fetchone()["cnt"]

    # This week's stats
    week = conn.execute(
        """SELECT
             COUNT(*) as actions,
             COALESCE(SUM(CASE WHEN action_type IN ('comment','reply') THEN 1 ELSE 0 END), 0) as comments,
             COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
           FROM actions WHERE created_at > ?""",
        (week_ago,),
    ).fetchone()

    # Reply rate (how many of our comments got replies)
    tracking = conn.execute(
        """SELECT
             COUNT(*) as total,
             COALESCE(SUM(CASE WHEN status = 'replied' THEN 1 ELSE 0 END), 0) as replied
           FROM reply_tracking WHERE created_at > ?""",
        (two_weeks_ago,),
    ).fetchone()

    # High-value relationships
    relationships = conn.execute(
        "SELECT COUNT(*) as cnt FROM relationships WHERE interaction_count >= 3"
    ).fetchone()["cnt"]

    # Active platforms (posted in last 7 days)
    active_platforms = conn.execute(
        "SELECT COUNT(DISTINCT platform) as cnt FROM actions WHERE created_at > ?",
        (week_ago,),
    ).fetchone()["cnt"]

    conn.close()

    actions = week["actions"]
    comments = week["comments"]
    promos = week["promos"]
    reply_rate = tracking["replied"] / max(tracking["total"], 1)
    promo_ratio = promos / max(actions, 1)

    reasoning = []

    # Early stage — need visibility first
    if total_ever < 50:
        reasoning.append(f"early stage ({total_ever} total actions), need presence first")
        return "visibility", "; ".join(reasoning)

    # Low platform coverage
    if active_platforms < 4:
        reasoning.append(f"only {active_platforms} platforms active this week, need broader reach")
        return "visibility", "; ".join(reasoning)

    # High promo ratio — need to cool down and build trust
    if promo_ratio > 0.08:
        reasoning.append(f"promo ratio at {promo_ratio:.0%}, need to build trust before converting")
        return "relationships", "; ".join(reasoning)

    # Low engagement — not enough eyeballs
    if actions > 30 and reply_rate < 0.05:
        reasoning.append(f"reply rate only {reply_rate:.0%} with {actions} actions, need more visibility")
        return "visibility", "; ".join(reasoning)

    # Strong relationships — time to convert
    if relationships >= 10 and promo_ratio < 0.05:
        reasoning.append(f"{relationships} high-value relationships, promo ratio safe at {promo_ratio:.0%}")
        return "conversions", "; ".join(reasoning)

    # Good visibility, zero promos — can start converting
    if actions > 100 and promos == 0:
        reasoning.append(f"{actions} actions this week with 0 promotions, safe to start converting")
        return "conversions", "; ".join(reasoning)

    # Default
    reasoning.append(f"{actions} actions, {reply_rate:.0%} reply rate, {promo_ratio:.0%} promo ratio")
    return "balanced", "; ".join(reasoning)
