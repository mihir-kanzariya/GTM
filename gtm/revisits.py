"""Reply revisit system -- check if anyone replied to our comments via WebFetch.

Per-platform parsers detect replies in API/page responses.
The orchestrator (run_revisits) gathers due checks and processes them.
"""


def parse_reddit_comment_replies(json_data, our_username):
    """Parse Reddit comment JSON to find replies to our comment.

    Args:
        json_data: Response from WebFetch "{comment_permalink}.json"
                   This is a list of two Listings: [post, comments_tree]
        our_username: Our Reddit username to identify our comment

    Returns:
        List of reply dicts: [{"author": str, "content": str}]
    """
    replies = []
    if not json_data or len(json_data) < 2:
        return replies

    comments_listing = json_data[1]
    children = comments_listing.get("data", {}).get("children", [])

    for child in children:
        comment = child.get("data", {})
        if comment.get("author", "").lower() == our_username.lower():
            reply_data = comment.get("replies")
            if not reply_data or isinstance(reply_data, str):
                continue
            reply_children = reply_data.get("data", {}).get("children", [])
            for rc in reply_children:
                rd = rc.get("data", {})
                if rd.get("author") and rd.get("body"):
                    replies.append({
                        "author": rd["author"],
                        "content": rd["body"],
                    })
    return replies


def parse_hn_comment_replies(our_comment, kid_items):
    """Parse HN comment replies.

    Args:
        our_comment: Our comment item from HN API (has "kids" list of IDs)
        kid_items: List of fetched kid item dicts (already resolved from IDs)

    Returns:
        List of reply dicts: [{"author": str, "content": str}]
    """
    replies = []
    for kid in kid_items:
        if kid.get("by") and kid.get("text"):
            replies.append({
                "author": kid["by"],
                "content": kid["text"],
            })
    return replies


def parse_devto_comment_replies(comment_data):
    """Parse Dev.to comment replies.

    Args:
        comment_data: Response from WebFetch "https://dev.to/api/comments/{id}"
                      Has "children" array with reply comments

    Returns:
        List of reply dicts: [{"author": str, "content": str}]
    """
    replies = []
    children = comment_data.get("children", [])
    for child in children:
        user = child.get("user", {})
        if user.get("username") and child.get("body_html"):
            replies.append({
                "author": user["username"],
                "content": child["body_html"],
            })
    return replies


from datetime import datetime, timedelta

from gtm.db import get_connection
from gtm.engagement import _get_check_interval


def get_due_revisits(db_path, hours=24):
    """Get all reply tracking entries due for checking within the last N hours."""
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM reply_tracking
               WHERE status = 'active'
               AND next_check_at <= datetime('now')
               AND checks_done < max_checks
               AND created_at > ?
               ORDER BY next_check_at""",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def schedule_next_check(db_path, tracking_id):
    """Schedule the next check with escalating interval based on checks_done."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT checks_done FROM reply_tracking WHERE id = ?", (tracking_id,)
        ).fetchone()
        if not row:
            return
        next_interval = _get_check_interval(row["checks_done"])
        next_check = (datetime.utcnow() + timedelta(minutes=next_interval)).isoformat()
        conn.execute(
            "UPDATE reply_tracking SET next_check_at = ? WHERE id = ?",
            (next_check, tracking_id),
        )
        conn.commit()
    finally:
        conn.close()


def run_revisits(db_path, hours=24):
    """Orchestrate the revisit phase. Returns structured results for Claude to act on.

    This function does NOT perform WebFetch or Owl -- it returns entries
    that need checking so Claude can process them.
    """
    due = get_due_revisits(db_path, hours)

    result = {
        "checked": len(due),
        "replies_found": 0,
        "no_reply": 0,
        "exhausted": 0,
        "needs_reply": [],
        "pending": [],
    }

    for entry in due:
        result["pending"].append({
            "tracking_id": entry["id"],
            "platform": entry["platform"],
            "target_url": entry["target_url"],
            "comment_url": entry["comment_url"],
            "checks_done": entry["checks_done"],
        })

    return result
