import json
from datetime import datetime, timedelta

from gtm.db import get_connection

THREAD_TYPES = ["building_in_public", "general_founder"]
MAX_TWEET_LENGTH = 280


def log_thread(db_path, session_id, thread_type, topic, tweets, first_tweet_url):
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO threads
               (session_id, thread_type, topic, tweet_count,
                first_tweet_url, content)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, thread_type, topic, len(tweets),
             first_tweet_url, json.dumps(tweets)),
        )
        tid = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return tid


def get_recent_threads(db_path, days=14):
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT topic, thread_type, tweet_count, first_tweet_url, posted_at
               FROM threads WHERE posted_at > ?
               ORDER BY posted_at DESC""",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def format_thread(tweets):
    formatted = []
    for tweet in tweets:
        if len(tweet) > MAX_TWEET_LENGTH:
            formatted.append(tweet[:277] + "...")
        else:
            formatted.append(tweet)
    return formatted
