from datetime import datetime, timedelta

from gtm.db import get_connection


def update_keyword_score(db_path, keyword, platform, replies=0, upvotes=0,
                         comments_made=1, posts_found=0):
    now = datetime.utcnow().isoformat()
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT * FROM keyword_performance WHERE keyword = ? AND platform = ?",
            (keyword, platform),
        ).fetchone()

        if existing:
            new_times = existing["times_used"] + 1
            new_replies = existing["replies_received"] + replies
            new_comments = existing["comments_made"] + comments_made
            new_posts = existing["posts_found"] + posts_found
            total_upvotes = existing["avg_upvotes"] * existing["times_used"] + upvotes
            new_avg_upvotes = total_upvotes / new_times
            recency_bonus = 2.0
            score = (new_replies * 3) + (new_avg_upvotes * 1) + (new_comments * 0.5) + recency_bonus

            conn.execute(
                """UPDATE keyword_performance
                   SET times_used = ?, posts_found = ?, comments_made = ?,
                       replies_received = ?, avg_upvotes = ?, last_used_at = ?, score = ?
                   WHERE keyword = ? AND platform = ?""",
                (new_times, new_posts, new_comments, new_replies, new_avg_upvotes,
                 now, score, keyword, platform),
            )
        else:
            score = (replies * 3) + (upvotes * 1) + (comments_made * 0.5) + 2.0
            conn.execute(
                """INSERT INTO keyword_performance
                   (keyword, platform, times_used, posts_found, comments_made,
                    replies_received, avg_upvotes, last_used_at, score)
                   VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)""",
                (keyword, platform, posts_found, comments_made, replies,
                 upvotes, now, score),
            )
        conn.commit()
    finally:
        conn.close()


def get_weighted_keywords(db_path, platform, n=5):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT keyword, score FROM keyword_performance WHERE platform = ? ORDER BY score DESC",
            (platform,),
        ).fetchall()
    finally:
        conn.close()
    return [(r["keyword"], r["score"]) for r in rows[:n]]


def seed_keywords(db_path, platform, keywords):
    conn = get_connection(db_path)
    try:
        for kw in keywords:
            conn.execute(
                """INSERT OR IGNORE INTO keyword_performance
                   (keyword, platform, times_used, score)
                   VALUES (?, ?, 0, 0)""",
                (kw, platform),
            )
        conn.commit()
    finally:
        conn.close()


def update_peak_times(db_path, platform, day, hour, replies=0, upvotes=0):
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT * FROM peak_times WHERE platform = ? AND day_of_week = ? AND hour = ?",
            (platform, day, hour),
        ).fetchone()

        engagement = (upvotes * 1) + (replies * 5)

        if existing:
            n = existing["sample_count"]
            new_n = n + 1
            new_avg_replies = (existing["avg_replies"] * n + replies) / new_n
            new_avg_upvotes = (existing["avg_upvotes"] * n + upvotes) / new_n
            new_score = (existing["engagement_score"] * n + engagement) / new_n

            conn.execute(
                """UPDATE peak_times
                   SET actions_taken = actions_taken + 1,
                       avg_replies = ?, avg_upvotes = ?,
                       engagement_score = ?, sample_count = ?
                   WHERE platform = ? AND day_of_week = ? AND hour = ?""",
                (new_avg_replies, new_avg_upvotes, new_score, new_n,
                 platform, day, hour),
            )
        else:
            conn.execute(
                """INSERT INTO peak_times
                   (platform, day_of_week, hour, actions_taken,
                    avg_replies, avg_upvotes, engagement_score, sample_count)
                   VALUES (?, ?, ?, 1, ?, ?, ?, 1)""",
                (platform, day, hour, replies, upvotes, engagement),
            )
        conn.commit()
    finally:
        conn.close()


def get_best_hours(db_path, platform, top_n=3):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT day_of_week, hour, engagement_score, sample_count
               FROM peak_times WHERE platform = ?
               ORDER BY engagement_score DESC LIMIT ?""",
            (platform, top_n),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def calculate_engagement_score(db_path, action_id):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """SELECT COALESCE(MAX(upvotes), 0) as upvotes,
                      COALESCE(MAX(replies), 0) as replies
               FROM outcomes WHERE action_id = ?""",
            (action_id,),
        ).fetchone()
    finally:
        conn.close()
    if row["upvotes"] == 0 and row["replies"] == 0:
        return 0
    return (row["upvotes"] * 1) + (row["replies"] * 5)
