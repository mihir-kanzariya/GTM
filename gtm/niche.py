import json
from gtm.db import get_connection


def get_niche(db_path):
    """Return full niche profile as dict."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT key, value FROM niche_profile").fetchall()
    finally:
        conn.close()
    result = {"industries": [], "audiences": [], "exclude": [], "products": []}
    for row in rows:
        result[row["key"]] = json.loads(row["value"])
    return result


def set_niche_field(db_path, key, values):
    """Set a niche field (industries, audiences, exclude)."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO niche_profile (key, value, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, json.dumps(values)),
        )
        conn.commit()
    finally:
        conn.close()


def add_product(db_path, url, description):
    """Add a product to the niche profile."""
    products = get_products(db_path)
    if any(p["url"] == url for p in products):
        return
    products.append({"url": url, "desc": description})
    set_niche_field(db_path, "products", products)


def get_products(db_path):
    """Return list of products from niche profile."""
    niche = get_niche(db_path)
    return niche.get("products", [])


def is_excluded_topic(db_path, topic_text):
    """Check if a topic matches any exclusion terms (fuzzy stem match)."""
    niche = get_niche(db_path)
    excluded = niche.get("exclude", [])
    topic_lower = topic_text.lower()
    for term in excluded:
        term_lower = term.lower()
        # Direct substring match
        if term_lower in topic_lower:
            return True
        # Stem match: strip trailing 's' and check
        stem = term_lower.rstrip("s")
        if len(stem) >= 3 and stem in topic_lower:
            return True
    return False
