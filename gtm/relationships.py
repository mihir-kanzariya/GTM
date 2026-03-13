import json
from datetime import datetime

from gtm.db import get_connection


def track_interaction(db_path, platform, username, display_name, action_id,
                      interaction_type):
    now = datetime.utcnow().isoformat()
    interaction_entry = {
        "action_id": action_id,
        "type": interaction_type,
        "date": now,
    }
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT * FROM relationships WHERE platform = ? AND username = ?",
            (platform, username),
        ).fetchone()

        if existing:
            interactions = json.loads(existing["interactions"] or "[]")
            interactions.append(interaction_entry)
            new_count = existing["interaction_count"] + 1
            score = new_count * 2
            conn.execute(
                """UPDATE relationships
                   SET interaction_count = ?, last_interacted = ?,
                       interactions = ?, relationship_score = ?,
                       display_name = ?
                   WHERE platform = ? AND username = ?""",
                (new_count, now, json.dumps(interactions), score,
                 display_name, platform, username),
            )
        else:
            interactions = json.dumps([interaction_entry])
            conn.execute(
                """INSERT INTO relationships
                   (platform, username, display_name, last_interacted,
                    interaction_count, interactions, relationship_score)
                   VALUES (?, ?, ?, ?, 1, ?, 2)""",
                (platform, username, display_name, now, interactions),
            )
        conn.commit()
    finally:
        conn.close()


def get_known_users(db_path, platform):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT username, display_name, interaction_count, relationship_score
               FROM relationships WHERE platform = ?
               ORDER BY relationship_score DESC""",
            (platform,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_high_value_users(db_path, platform, min_interactions=3):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT username, display_name, interaction_count, relationship_score
               FROM relationships
               WHERE platform = ? AND interaction_count >= ?
               ORDER BY relationship_score DESC""",
            (platform, min_interactions),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def is_known_user(db_path, platform, username):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM relationships WHERE platform = ? AND username = ?",
            (platform, username),
        ).fetchone()
    finally:
        conn.close()
    return row is not None
