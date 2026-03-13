import sqlite3
import os
import uuid
from datetime import datetime


def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = get_connection(db_path)
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            started_at DATETIME NOT NULL,
            ended_at DATETIME,
            total_actions INTEGER DEFAULT 0,
            promoted_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            platform TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_url TEXT,
            target_title TEXT,
            content_written TEXT,
            promoted_product TEXT,
            created_at DATETIME NOT NULL DEFAULT (datetime('now')),
            keywords_matched TEXT
        );

        CREATE TABLE IF NOT EXISTS outcomes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id       INTEGER NOT NULL REFERENCES actions(id),
            check_number    INTEGER,
            checked_at      DATETIME NOT NULL DEFAULT (datetime('now')),
            upvotes         INTEGER DEFAULT 0,
            replies         INTEGER DEFAULT 0,
            reply_content   TEXT,
            reply_author    TEXT,
            views           INTEGER,
            our_reply_id    INTEGER REFERENCES actions(id)
        );

        CREATE TABLE IF NOT EXISTS daily_metrics (
            date DATE NOT NULL,
            platform TEXT NOT NULL,
            total_actions INTEGER DEFAULT 0,
            comments_written INTEGER DEFAULT 0,
            promotions INTEGER DEFAULT 0,
            promotion_ratio REAL DEFAULT 0.0,
            PRIMARY KEY (date, platform)
        );

        CREATE TABLE IF NOT EXISTS reply_tracking (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id       INTEGER REFERENCES actions(id) UNIQUE,
            platform        TEXT NOT NULL,
            target_url      TEXT,
            comment_url     TEXT,
            status          TEXT DEFAULT 'active',
            checks_done     INTEGER DEFAULT 0,
            max_checks      INTEGER DEFAULT 3,
            check_interval_min INTEGER DEFAULT 15,
            next_check_at   DATETIME,
            last_checked_at DATETIME,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS threads (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT DEFAULT 'twitter',
            thread_type     TEXT,
            topic           TEXT,
            tweet_count     INTEGER,
            first_tweet_url TEXT,
            content         TEXT,
            posted_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_id      TEXT REFERENCES sessions(id),
            engagement      TEXT
        );

        CREATE TABLE IF NOT EXISTS keyword_performance (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword         TEXT NOT NULL,
            platform        TEXT NOT NULL,
            times_used      INTEGER DEFAULT 0,
            posts_found     INTEGER DEFAULT 0,
            comments_made   INTEGER DEFAULT 0,
            replies_received INTEGER DEFAULT 0,
            avg_upvotes     REAL DEFAULT 0,
            last_used_at    DATETIME,
            score           REAL DEFAULT 0,
            UNIQUE(keyword, platform)
        );

        CREATE TABLE IF NOT EXISTS relationships (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT NOT NULL,
            username        TEXT NOT NULL,
            display_name    TEXT,
            first_seen_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_interacted DATETIME,
            interaction_count INTEGER DEFAULT 1,
            interactions    TEXT,
            notes           TEXT,
            relationship_score REAL DEFAULT 0,
            UNIQUE(platform, username)
        );

        CREATE TABLE IF NOT EXISTS content_calendar (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT NOT NULL,
            content_type    TEXT NOT NULL,
            topic           TEXT,
            outline         TEXT,
            scheduled_for   DATE,
            status          TEXT DEFAULT 'planned',
            action_id       INTEGER REFERENCES actions(id),
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS peak_times (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT NOT NULL,
            day_of_week     INTEGER NOT NULL,
            hour            INTEGER NOT NULL,
            actions_taken   INTEGER DEFAULT 0,
            avg_replies     REAL DEFAULT 0,
            avg_upvotes     REAL DEFAULT 0,
            engagement_score REAL DEFAULT 0,
            sample_count    INTEGER DEFAULT 0,
            UNIQUE(platform, day_of_week, hour)
        );

        CREATE TABLE IF NOT EXISTS decision_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
            category        TEXT NOT NULL,
            platform        TEXT,
            decision        TEXT NOT NULL,
            reasoning       TEXT,
            context         TEXT,
            session_id      TEXT REFERENCES sessions(id),
            outcome         TEXT
        );

        CREATE TABLE IF NOT EXISTS niche_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS content_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            source_url TEXT,
            title TEXT,
            text_snippet TEXT,
            author TEXT,
            author_followers INTEGER DEFAULT 0,
            engagement INTEGER DEFAULT 0,
            discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            topic_id INTEGER REFERENCES topic_clusters(id)
        );

        CREATE TABLE IF NOT EXISTS topic_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            key_phrases TEXT,
            first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen_at DATETIME,
            status TEXT DEFAULT 'weak',
            total_mentions INTEGER DEFAULT 0,
            platforms_seen TEXT,
            platform_count INTEGER DEFAULT 0,
            velocity REAL DEFAULT 0,
            authority_score REAL DEFAULT 0,
            trend_score REAL DEFAULT 0,
            relevance TEXT DEFAULT 'unknown',
            saturation REAL DEFAULT 0,
            engagement_potential REAL DEFAULT 0,
            opportunity_score REAL DEFAULT 0,
            times_we_posted INTEGER DEFAULT 0,
            avg_engagement REAL DEFAULT 0,
            best_angle TEXT,
            expires_at DATETIME
        );

        CREATE INDEX IF NOT EXISTS idx_content_signals_platform ON content_signals(platform, discovered_at);
        CREATE INDEX IF NOT EXISTS idx_content_signals_topic ON content_signals(topic_id);
        CREATE INDEX IF NOT EXISTS idx_topic_clusters_status ON topic_clusters(status, trend_score);

        CREATE INDEX IF NOT EXISTS idx_actions_target_url ON actions(target_url);
        CREATE INDEX IF NOT EXISTS idx_actions_session ON actions(session_id);
        CREATE INDEX IF NOT EXISTS idx_actions_platform_date ON actions(platform, created_at);
        CREATE INDEX IF NOT EXISTS idx_outcomes_action ON outcomes(action_id);
        CREATE INDEX IF NOT EXISTS idx_reply_tracking_status ON reply_tracking(status, next_check_at);
        CREATE INDEX IF NOT EXISTS idx_keyword_platform ON keyword_performance(platform, score);
        CREATE INDEX IF NOT EXISTS idx_relationships_platform ON relationships(platform, username);
        CREATE INDEX IF NOT EXISTS idx_decision_log_category ON decision_log(category, timestamp);
        CREATE INDEX IF NOT EXISTS idx_threads_posted ON threads(posted_at);
        CREATE INDEX IF NOT EXISTS idx_content_calendar_date ON content_calendar(scheduled_for, status);
    """)
    finally:
        conn.close()


def create_session(db_path, platform):
    sid = str(uuid.uuid4())
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO sessions (id, platform, started_at) VALUES (?, ?, ?)",
            (sid, platform, datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return sid


def end_session(db_path, session_id):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) as total, COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos FROM actions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        conn.execute(
            "UPDATE sessions SET ended_at = ?, total_actions = ?, promoted_count = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), row["total"], row["promos"], session_id),
        )
        conn.commit()
    finally:
        conn.close()


def log_action(db_path, session_id, platform, action_type, target_url,
               target_title=None, content=None, promoted_product=None,
               keywords_matched=None):
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO actions
               (session_id, platform, action_type, target_url, target_title,
                content_written, promoted_product, keywords_matched)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, platform, action_type, target_url, target_title,
             content, promoted_product, keywords_matched),
        )
        action_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return action_id


def is_duplicate_url(db_path, url, days=7):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM actions WHERE target_url = ? AND created_at > datetime('now', ?)",
            (url, f"-{days} days"),
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def get_promotion_ratio(db_path, platform, days=7):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """SELECT
                 COUNT(*) as total,
                 COALESCE(SUM(CASE WHEN promoted_product IS NOT NULL THEN 1 ELSE 0 END), 0) as promos
               FROM actions
               WHERE platform = ? AND created_at > datetime('now', ?)""",
            (platform, f"-{days} days"),
        ).fetchone()
    finally:
        conn.close()
    if row["total"] == 0:
        return 0.0
    return row["promos"] / row["total"]
