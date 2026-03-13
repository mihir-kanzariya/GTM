from datetime import datetime, timedelta

from gtm.db import get_connection


def add_content(db_path, platform, content_type, topic, outline, scheduled_for):
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO content_calendar
               (platform, content_type, topic, outline, scheduled_for)
               VALUES (?, ?, ?, ?, ?)""",
            (platform, content_type, topic, outline, scheduled_for),
        )
        cid = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return cid


def get_today_content(db_path, platform):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT id, content_type, topic, outline
               FROM content_calendar
               WHERE platform = ? AND scheduled_for = ? AND status = 'planned'""",
            (platform, today),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def mark_posted(db_path, calendar_id, action_id):
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE content_calendar SET status = 'posted', action_id = ? WHERE id = ?",
            (action_id, calendar_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_upcoming(db_path, days=3):
    cutoff = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT id, platform, content_type, topic, outline, scheduled_for
               FROM content_calendar
               WHERE scheduled_for >= ? AND scheduled_for <= ? AND status = 'planned'
               ORDER BY scheduled_for""",
            (today, cutoff),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
