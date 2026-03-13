import random
from datetime import datetime

from gtm.db import init_db, create_session, end_session, log_action, is_duplicate_url, get_promotion_ratio
from gtm.state import load_state, save_state, PLATFORMS
from gtm.engagement import enroll_for_tracking
from gtm.decisions import log_decision

PROMO_RATIO_LIMIT = 0.1

# ---------------------------------------------------------------------------
# Per-platform action configs: weights, limits, char limits, descriptions
# ---------------------------------------------------------------------------
PLATFORM_ACTIONS = {
    "twitter": {
        "session_range": (20, 30),
        "actions": {
            "like": {
                "weight": 20,
                "max_per_session": 50,
                "desc": "Like a tweet. Quick engagement signal, low effort.",
            },
            "reply": {
                "weight": 15,
                "max_per_session": 15,
                "char_limit": 280,
                "desc": "Reply to a tweet. 1-3 sentences, match thread energy. Must be under 280 chars.",
            },
            "like_and_reply": {
                "weight": 15,
                "max_per_session": 15,
                "char_limit": 280,
                "desc": "Like + reply combo. Most natural human pattern. Like first, then reply.",
            },
            "retweet": {
                "weight": 5,
                "max_per_session": 5,
                "desc": "Retweet without commentary. Only for genuinely high-value content.",
            },
            "quote_tweet": {
                "weight": 5,
                "max_per_session": 3,
                "char_limit": 280,
                "desc": "Retweet with your own take added. Good for building-in-public visibility.",
            },
            "bookmark": {
                "weight": 8,
                "max_per_session": 10,
                "desc": "Save tweet for later. Invisible to others, zero risk action.",
            },
            "follow": {
                "weight": 10,
                "max_per_session": 15,
                "desc": "Follow an account. Target indie hackers, solo founders, dev tool makers.",
            },
            "skip": {
                "weight": 12,
                "desc": "Scroll past without interacting. Mimics real browsing behavior.",
            },
            "post": {
                "weight": 5,
                "max_per_session": 3,
                "char_limit": 280,
                "desc": "Original tweet. Building-in-public updates, hot takes, questions, tips.",
            },
            "thread": {
                "weight": 5,
                "max_per_session": 1,
                "desc": "Multi-tweet thread. 3-5 tweets, each under 280 chars. Max 1 per session.",
            },
        },
    },
    "reddit": {
        "session_range": (10, 15),
        "actions": {
            "upvote": {
                "weight": 25,
                "desc": "Upvote a post or comment. Primary low-effort engagement.",
            },
            "comment": {
                "weight": 20,
                "max_per_session": 15,
                "char_limit": 10000,
                "desc": "Top-level comment on a post. 1-4 sentences. ALWAYS read sub rules first.",
            },
            "reply": {
                "weight": 15,
                "max_per_session": 10,
                "char_limit": 10000,
                "desc": "Reply to an existing comment in a thread. Adds to discussion.",
            },
            "upvote_and_comment": {
                "weight": 10,
                "max_per_session": 10,
                "char_limit": 10000,
                "desc": "Upvote + comment combo. Natural human pattern.",
            },
            "save": {
                "weight": 5,
                "desc": "Bookmark a post. Invisible to others.",
            },
            "skip": {
                "weight": 12,
                "desc": "Read and scroll past without interacting.",
            },
            "join": {
                "weight": 3,
                "max_per_session": 3,
                "desc": "Join a subreddit. Max 1-3 new subs per session.",
            },
            "post": {
                "weight": 5,
                "max_per_session": 3,
                "desc": "Submit a new post. Max 1 per subreddit. Questions and discussions only, never self-promo.",
            },
            "downvote": {
                "weight": 5,
                "desc": "Downvote spam or off-topic content. Use very sparingly.",
            },
        },
    },
    "devto": {
        "session_range": (10, 20),
        "actions": {
            "like": {
                "weight": 25,
                "desc": "Heart-react an article. Quick signal of appreciation.",
            },
            "comment": {
                "weight": 20,
                "max_per_session": 15,
                "desc": "Comment on an article. Reference specifics from the post. 1-4 sentences.",
            },
            "like_and_comment": {
                "weight": 15,
                "max_per_session": 15,
                "desc": "Like + comment combo on an article.",
            },
            "follow": {
                "weight": 10,
                "max_per_session": 10,
                "desc": "Follow an author. Target active dev bloggers in your niche.",
            },
            "save": {
                "weight": 8,
                "desc": "Add article to reading list.",
            },
            "skip": {
                "weight": 12,
                "desc": "Browse without engaging.",
            },
            "post": {
                "weight": 10,
                "max_per_session": 1,
                "desc": "Publish an article. Max 1 per session. Tutorials, listicles, comparisons. Use 3-5 tags.",
            },
        },
    },
    "producthunt": {
        "session_range": (3, 8),
        "actions": {
            "upvote": {
                "weight": 30,
                "max_per_session": 10,
                "desc": "Upvote a product launch. Be selective, don't upvote everything.",
            },
            "comment": {
                "weight": 25,
                "max_per_session": 5,
                "desc": "Comment on a product page. Ask genuine questions about the product. 2-5 sentences.",
            },
            "reply": {
                "weight": 15,
                "max_per_session": 5,
                "desc": "Reply to maker or other commenters. Engage in discussion.",
            },
            "follow": {
                "weight": 10,
                "max_per_session": 5,
                "desc": "Follow a maker.",
            },
            "skip": {
                "weight": 20,
                "desc": "Browse launches without interacting. Don't upvote everything.",
            },
        },
    },
    "indiehackers": {
        "session_range": (3, 8),
        "actions": {
            "upvote": {
                "weight": 20,
                "desc": "Upvote a post.",
            },
            "comment": {
                "weight": 25,
                "max_per_session": 8,
                "desc": "Comment on a post. Share real experience. 3-6 sentences. Tired founder tone, not polished.",
            },
            "reply": {
                "weight": 20,
                "max_per_session": 8,
                "desc": "Reply to existing comments. Build conversations.",
            },
            "upvote_and_comment": {
                "weight": 10,
                "max_per_session": 5,
                "desc": "Upvote + comment combo.",
            },
            "follow": {
                "weight": 5,
                "max_per_session": 5,
                "desc": "Follow a user.",
            },
            "skip": {
                "weight": 20,
                "desc": "Read without engaging.",
            },
        },
    },
    "hackernews": {
        "session_range": (6, 9),
        "actions": {
            "upvote": {
                "weight": 50,
                "max_per_session": 30,
                "desc": "Upvote stories or comments. Click the triangle. Primary HN action.",
            },
            "comment": {
                "weight": 20,
                "max_per_session": 8,
                "desc": "Reply in a thread. Must be substantive, not '+1'. Plain text only, no markdown. 2-5 sentences.",
            },
            "reply": {
                "weight": 15,
                "max_per_session": 5,
                "desc": "Reply to a specific comment. Lead with insight or personal experience.",
            },
            "skip": {
                "weight": 15,
                "desc": "Read without engaging. HN has no save/follow/share.",
            },
        },
    },
}

# Actions that trigger reply tracking (auto-enrolled when recorded)
TRACKABLE_ACTIONS = {'comment', 'reply', 'like_and_reply', 'like_and_comment', 'upvote_and_comment'}


def get_platform_config(platform):
    """Get the full action config for a platform."""
    return PLATFORM_ACTIONS.get(platform, PLATFORM_ACTIONS["hackernews"])


def get_session_range(platform):
    """Get (min, max) action count for a platform session."""
    return get_platform_config(platform)["session_range"]


def get_action_info(platform, action_type):
    """Get config dict for a specific action on a platform. Returns None if not found."""
    config = get_platform_config(platform)
    return config["actions"].get(action_type)


def get_action_description(platform, action_type):
    """Get human-readable description of an action for a platform."""
    info = get_action_info(platform, action_type)
    return info["desc"] if info else "Unknown action."


def get_available_actions(platform):
    """Return list of all action types available on a platform."""
    return list(get_platform_config(platform)["actions"].keys())


def roll_action(platform, action_counts=None):
    """Pick a random action for a platform, respecting weights and session limits.

    Args:
        platform: Platform name (e.g. 'twitter', 'reddit')
        action_counts: Optional dict of {action_type: count_so_far} to enforce limits.
                       If None, ignores limits and just uses weights.

    Returns:
        action_type string (e.g. 'like', 'reply', 'upvote')
    """
    config = get_platform_config(platform)
    actions = config["actions"]

    # Build weighted pool, excluding actions that hit their max
    pool = []
    for action_type, info in actions.items():
        max_limit = info.get("max_per_session")
        if action_counts and max_limit:
            if action_counts.get(action_type, 0) >= max_limit:
                continue
        pool.extend([action_type] * info["weight"])

    if not pool:
        return "skip"
    return random.choice(pool)


class InterleavedRunner:
    """Runs a session interleaving actions across ALL platforms for speed.

    Instead of finishing one platform before starting the next, this runner
    rotates between platforms after each action. Wait time on one platform
    is spent doing actions on another — no dead time, no platform-switch delay.
    """

    def __init__(self, db_path, state_path, goal=None):
        self.db_path = db_path
        self.state_path = state_path
        self.started_at = datetime.utcnow()
        self.max_duration_min = random.randint(20, 50)

        # Per-platform action limits from PLATFORM_ACTIONS config
        self.platform_limits = {
            p: random.randint(*get_session_range(p))
            for p in PLATFORMS
        }
        self.platform_actions = {p: 0 for p in PLATFORMS}
        # Track per-action-type counts for limit enforcement
        self.action_type_counts = {p: {} for p in PLATFORMS}
        self.session_ids = {}  # platform -> session_id
        self.total_actions = 0
        self._last_platform = None

        init_db(self.db_path)
        self.state = load_state(self.state_path)
        self.reason = None

        # Load goal — auto-recommend if not specified
        self.goal_reasoning = None
        if goal:
            self.goal = goal
        else:
            try:
                from gtm.goals import recommend_goal
                self.goal, self.goal_reasoning = recommend_goal(self.db_path, self.state_path)
            except Exception:
                self.goal = "balanced"
        self.briefing = None  # populated by load_briefing()
        self.revisit_results = None

    def load_briefing(self):
        """Load pre-session intelligence briefing."""
        from gtm.intelligence import get_briefing
        self.briefing = get_briefing(self.db_path, self.state_path)
        return self.briefing

    def discover_topic(self, platform, topic_name, key_phrases=None, mentions=1):
        """Log a discovered topic during the session."""
        from gtm.intelligence import create_topic, get_active_topics, update_topic_mentions
        # Check if topic already exists
        existing = get_active_topics(self.db_path)
        for t in existing:
            if t["name"].lower() == topic_name.lower():
                update_topic_mentions(self.db_path, t["id"], mentions, [platform])
                return t["id"]
        # Create new topic
        return create_topic(self.db_path, {
            "name": topic_name,
            "key_phrases": key_phrases or [],
            "platforms_seen": [platform],
            "total_mentions": mentions,
            "relevance": "unknown",
        })

    def start_all(self, platforms=None):
        """Create session records for platforms. Defaults to all."""
        targets = platforms or PLATFORMS
        for p in targets:
            self.session_ids[p] = create_session(self.db_path, p)
        # Mark session as running in state
        self.state["running_since"] = datetime.utcnow().isoformat() + "Z"
        self.state["running_platforms"] = list(self.session_ids.keys())
        save_state(self.state_path, self.state)

    @property
    def active_platforms(self):
        """Platforms that haven't hit their action limit yet."""
        return [p for p in PLATFORMS if self.platform_actions[p] < self.platform_limits[p]]

    def pick_next(self):
        """Pick the next platform to act on. Avoids repeating the same one."""
        available = self.active_platforms
        if not available:
            return None
        # Prefer a different platform than the last one
        if self._last_platform and self._last_platform in available and len(available) > 1:
            candidates = [p for p in available if p != self._last_platform]
        else:
            candidates = available
        pick = random.choice(candidates)
        self._last_platform = pick
        return pick

    def should_promote(self, platform):
        """Check if promotion is safe for this platform."""
        ratio = get_promotion_ratio(self.db_path, platform, days=7)
        return ratio < PROMO_RATIO_LIMIT

    def is_duplicate(self, url):
        return is_duplicate_url(self.db_path, url)

    def roll_action(self, platform):
        """Pick a random action for a platform, respecting weights and limits."""
        return roll_action(platform, self.action_type_counts.get(platform, {}))

    def get_action_desc(self, platform, action_type):
        """Get the description for an action on a platform."""
        return get_action_description(platform, action_type)

    def get_char_limit(self, platform, action_type):
        """Get character limit for an action, or None if no limit."""
        info = get_action_info(platform, action_type)
        return info.get("char_limit") if info else None

    def record_action(self, platform, action_type, target_url, target_title=None,
                      content=None, promoted_product=None, keywords_matched=None,
                      comment_url=None, author_username=None):
        """Log an action for a specific platform."""
        if platform not in self.session_ids:
            return None
        aid = log_action(
            self.db_path, self.session_ids[platform], platform, action_type,
            target_url, target_title, content, promoted_product, keywords_matched,
        )
        self.platform_actions[platform] += 1
        self.total_actions += 1

        # Track per-action-type count for limit enforcement
        counts = self.action_type_counts.setdefault(platform, {})
        counts[action_type] = counts.get(action_type, 0) + 1

        # Auto-enroll trackable actions for reply tracking
        if action_type in TRACKABLE_ACTIONS:
            enroll_for_tracking(self.db_path, aid, platform, target_url, comment_url)
            log_decision(
                self.db_path, "engagement",
                f"Enrolled {action_type} for reply tracking",
                f"Posted on {platform}: {target_url}",
                session_id=self.session_ids[platform],
                platform=platform,
            )

        # Track relationships if author known
        if author_username:
            from gtm.relationships import track_interaction
            track_interaction(
                self.db_path, platform, author_username, None,
                aid, action_type,
            )

        return aid

    def is_platform_done(self, platform):
        """Check if a specific platform's action limit is reached."""
        return self.platform_actions[platform] >= self.platform_limits.get(platform, 5)

    def is_done(self):
        """Session is over when all platforms are done or time limit hit."""
        if not self.active_platforms:
            return True
        elapsed = (datetime.utcnow() - self.started_at).total_seconds() / 60
        return elapsed >= self.max_duration_min

    def finish(self):
        """End all platform sessions and update state."""
        for p, sid in self.session_ids.items():
            try:
                end_session(self.db_path, sid)
            except Exception:
                pass
        # Post-session intelligence updates
        try:
            from gtm.intelligence import update_feedback, transition_statuses, expire_stale
            transition_statuses(self.db_path)
            expire_stale(self.db_path)
            update_feedback(self.db_path)
        except Exception:
            pass  # Don't fail session finish if intelligence isn't set up

        # Post-session revisit check
        try:
            from gtm.revisits import run_revisits
            self.revisit_results = run_revisits(self.db_path)
        except Exception:
            self.revisit_results = {"checked": 0, "replies_found": 0, "no_reply": 0,
                                    "exhausted": 0, "needs_reply": [], "pending": []}

        self.state["last_session"] = datetime.utcnow().isoformat() + "Z"
        self.state["session_count_today"] = self.state.get("session_count_today", 0) + 1
        # Clear running status
        self.state.pop("running_since", None)
        self.state.pop("running_platforms", None)
        save_state(self.state_path, self.state)

    def get_action_delay(self):
        """Delay between actions (30s-3min). Spent switching to next platform's tab."""
        return random.triangular(30, 180, 60)

    def progress(self):
        """Return a dict showing per-platform progress."""
        return {
            p: f"{self.platform_actions[p]}/{self.platform_limits[p]}"
            for p in PLATFORMS
        }

    def action_breakdown(self, platform):
        """Return action type counts for a platform this session."""
        return dict(self.action_type_counts.get(platform, {}))

    def summary(self):
        """Return a summary dict of the session."""
        return {
            "goal": self.goal,
            "goal_reasoning": self.goal_reasoning,
            "platforms_engaged": list(self.session_ids.keys()),
            "total_actions": self.total_actions,
            "actions_per_platform": dict(self.platform_actions),
            "limits_per_platform": dict(self.platform_limits),
            "action_types": {p: dict(c) for p, c in self.action_type_counts.items() if c},
            "duration_min": int((datetime.utcnow() - self.started_at).total_seconds() / 60),
            "revisits": self.revisit_results or {"checked": 0, "pending": []},
        }


# Keep old runner as fallback
class SessionRunner:
    """Runs a full session across ALL platforms sequentially (legacy)."""

    def __init__(self, db_path, state_path):
        self.db_path = db_path
        self.state_path = state_path
        self.started_at = datetime.utcnow()
        self.platform_order = list(PLATFORMS)
        random.shuffle(self.platform_order)

        self.actions_per_platform = {
            p: random.randint(*get_session_range(p))
            for p in PLATFORMS
        }
        self.max_duration_min = random.randint(30, 90)

        self.current_platform_idx = 0
        self.current_platform_actions = 0
        self.total_actions = 0
        self.session_ids = {}

        init_db(self.db_path)
        self.state = load_state(self.state_path)
        self.reason = None

    @property
    def current_platform(self):
        if self.current_platform_idx >= len(self.platform_order):
            return None
        return self.platform_order[self.current_platform_idx]

    def start_platform(self):
        p = self.current_platform
        if p and p not in self.session_ids:
            self.session_ids[p] = create_session(self.db_path, p)
            self.current_platform_actions = 0
        return p

    def should_promote(self):
        p = self.current_platform
        if not p:
            return False
        ratio = get_promotion_ratio(self.db_path, p, days=7)
        return ratio < PROMO_RATIO_LIMIT

    def is_duplicate(self, url):
        return is_duplicate_url(self.db_path, url)

    def record_action(self, action_type, target_url, target_title=None,
                      content=None, promoted_product=None, keywords_matched=None):
        p = self.current_platform
        if not p or p not in self.session_ids:
            return None
        aid = log_action(
            self.db_path, self.session_ids[p], p, action_type,
            target_url, target_title, content, promoted_product, keywords_matched,
        )
        self.current_platform_actions += 1
        self.total_actions += 1
        return aid

    def is_platform_done(self):
        p = self.current_platform
        if not p:
            return True
        return self.current_platform_actions >= self.actions_per_platform.get(p, 5)

    def next_platform(self):
        p = self.current_platform
        if p and p in self.session_ids:
            end_session(self.db_path, self.session_ids[p])
        self.current_platform_idx += 1
        self.current_platform_actions = 0
        return self.current_platform

    def is_session_over(self):
        if self.current_platform is None:
            return True
        elapsed = (datetime.utcnow() - self.started_at).total_seconds() / 60
        return elapsed >= self.max_duration_min

    def finish(self):
        for p, sid in self.session_ids.items():
            try:
                end_session(self.db_path, sid)
            except Exception:
                pass
        self.state["last_session"] = datetime.utcnow().isoformat() + "Z"
        self.state["session_count_today"] = self.state.get("session_count_today", 0) + 1
        save_state(self.state_path, self.state)

    def get_random_delay(self):
        return random.triangular(30, 180, 60)

    def get_platform_switch_delay(self):
        return random.randint(30, 90)

    def summary(self):
        return {
            "platforms_engaged": list(self.session_ids.keys()),
            "total_actions": self.total_actions,
            "actions_per_platform": {
                p: self.actions_per_platform[p] for p in self.session_ids
            },
            "duration_min": int((datetime.utcnow() - self.started_at).total_seconds() / 60),
        }
