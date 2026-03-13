import json
import os
from datetime import datetime, timedelta


PLATFORMS = ["reddit", "twitter", "producthunt", "indiehackers", "devto", "hackernews"]


def create_default_state():
    now = (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z"
    return {
        "last_session": now,
        "session_count_today": 0,
        "daily_reset": datetime.utcnow().strftime("%Y-%m-%d"),
    }


def load_state(path):
    if not os.path.exists(path):
        state = create_default_state()
        save_state(path, state)
        return state

    with open(path, "r") as f:
        state = json.load(f)

    # Migrate old per-platform state to new format
    if "platforms" in state and "last_session" not in state:
        latest = None
        total_today = 0
        for p, info in state["platforms"].items():
            total_today += info.get("session_count_today", 0)
            last = info.get("last_session", "")
            if last and (latest is None or last > latest):
                latest = last
        state = {
            "last_session": latest or (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z",
            "session_count_today": total_today,
            "daily_reset": state.get("daily_reset", datetime.utcnow().strftime("%Y-%m-%d")),
        }
        save_state(path, state)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    if state.get("daily_reset") != today:
        state["session_count_today"] = 0
        state["daily_reset"] = today
        save_state(path, state)

    return state


def save_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def can_start_session(state):
    """Check if a new session can start. Always ready — no cooldown."""
    return True, "Ready"
