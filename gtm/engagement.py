import random
from datetime import datetime, timedelta

from gtm.db import get_connection

REPLY_PROBABILITY = 0.7
CHECK_INTERVALS = [15, 15, 30]  # minutes: 1st, 2nd, 3rd check


def _get_check_interval(checks_done):
    """Return interval in minutes for the next check based on how many checks done."""
    if checks_done < len(CHECK_INTERVALS):
        return CHECK_INTERVALS[checks_done]
    return CHECK_INTERVALS[-1]


def enroll_for_tracking(db_path, action_id, platform, target_url, comment_url=None):
    next_check = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT id FROM reply_tracking WHERE action_id = ?", (action_id,)
        ).fetchone()
        if existing:
            return existing["id"]
        cursor = conn.execute(
            """INSERT INTO reply_tracking
               (action_id, platform, target_url, comment_url, next_check_at)
               VALUES (?, ?, ?, ?, ?)""",
            (action_id, platform, target_url, comment_url, next_check),
        )
        tid = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return tid


def get_due_checks(db_path):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM reply_tracking
               WHERE status = 'active'
               AND next_check_at <= datetime('now')
               AND checks_done < max_checks
               ORDER BY next_check_at"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def record_check(db_path, tracking_id, upvotes=0, replies=0,
                 reply_content=None, reply_author=None):
    now = datetime.utcnow().isoformat()
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM reply_tracking WHERE id = ?", (tracking_id,)
        ).fetchone()
        new_checks = row["checks_done"] + 1
        check_number = new_checks

        # Escalating interval
        next_interval = _get_check_interval(new_checks)
        next_check = (datetime.utcnow() + timedelta(minutes=next_interval)).isoformat()

        conn.execute(
            """INSERT INTO outcomes
               (action_id, check_number, upvotes, replies, reply_content, reply_author)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (row["action_id"], check_number, upvotes, replies, reply_content, reply_author),
        )

        new_status = "exhausted" if new_checks >= row["max_checks"] else "active"
        conn.execute(
            """UPDATE reply_tracking
               SET checks_done = ?, last_checked_at = ?, next_check_at = ?, status = ?
               WHERE id = ?""",
            (new_checks, now, next_check, new_status, tracking_id),
        )
        conn.commit()
    finally:
        conn.close()


def should_reply(reply_content):
    return random.random() < REPLY_PROBABILITY


def mark_replied(db_path, tracking_id, reply_action_id):
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE reply_tracking SET status = 'replied' WHERE id = ?",
            (tracking_id,),
        )
        conn.execute(
            """UPDATE outcomes SET our_reply_id = ?
               WHERE action_id = (SELECT action_id FROM reply_tracking WHERE id = ?)
               ORDER BY checked_at DESC LIMIT 1""",
            (reply_action_id, tracking_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_exhausted(db_path, tracking_id):
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE reply_tracking SET status = 'exhausted' WHERE id = ?",
            (tracking_id,),
        )
        conn.commit()
    finally:
        conn.close()


def get_active_tracking_count(db_path):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM reply_tracking WHERE status = 'active'"
        ).fetchone()
    finally:
        conn.close()
    return row["cnt"]
