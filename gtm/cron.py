"""Cron job management for GTM reply checking.

This module builds prompts for CronCreate/CronDelete. The actual cron tools
are Claude Code built-ins — this module just provides the prompt text and
interval configuration.
"""

REPLY_CHECK_INTERVAL_MIN = 15


def build_reply_checker_prompt(db_path):
    return f"""Check for replies to tracked comments in reply_tracking and respond if needed.

1. Run this Python to get due checks:
```python
from gtm.engagement import get_due_checks
due = get_due_checks("{db_path}")
print(f"{{len(due)}} comments due for checking")
for entry in due:
    print(f"  - [{{entry['platform']}}] {{entry['target_url']}} (check #{{entry['checks_done'] + 1}})")
```

2. For each due entry:
   - Open the target_url in the browser via Owl
   - Find our comment (look for our username)
   - Check if anyone replied to our comment
   - Take a screenshot to verify

3. Record the check:
```python
from gtm.engagement import record_check, should_reply, mark_replied
record_check("{db_path}", tracking_id, upvotes=X, replies=Y,
             reply_content="their reply text", reply_author="username")
```

4. If someone replied, use 70/30 probability to decide whether to reply back:
```python
if should_reply(reply_content):
    # Write a contextual, human-sounding response
    # Post it via Owl
    # Log it: mark_replied("{db_path}", tracking_id, reply_action_id)
```

5. Log decisions:
```python
from gtm.decisions import log_decision
log_decision("{db_path}", "reply", "Replied to @user about X", "relevant question")
```

6. Update analytics:
```python
from gtm.analytics import update_keyword_score, update_peak_times
```

Remember: multiply Owl screenshot coordinates by 1.5 for click targets (screen is 1920x1080, screenshots are 1280x720).
"""


def get_cron_expression():
    return f"*/{REPLY_CHECK_INTERVAL_MIN} * * * *"
