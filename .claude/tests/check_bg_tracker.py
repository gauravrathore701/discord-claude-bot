"""Self-check for bot.BgTracker. Run: ./venv/bin/python .claude/tests/check_bg_tracker.py
Uses a real (trimmed) CLI stream: background Bash + background Agent, stdin kept open, 3 results."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from bot import BgTracker  # noqa: E402

# 1. real stream: pending at each result -> close stdin only on the last one
bg, at_results = BgTracker(), []
for line in open(os.path.join(HERE, "stream_bg_bash_agent.jsonl")):
    ev = json.loads(line)
    bg.feed(ev)
    if ev["type"] == "result":
        at_results.append(sorted(bg.pending))
assert at_results == [["a7fe2aaf8cb4867c4", "bnv1op7qb"], ["bnv1op7qb"], []], at_results

# 2. structured events alone
bg = BgTracker()
bg.feed({"type": "system", "subtype": "task_started", "task_id": "m1", "is_backgrounded": True})
assert bg.pending == {"m1"}
bg.feed({"type": "system", "subtype": "task_notification", "task_id": "m1", "status": "killed"})
assert bg.pending == set()

# 3. text fallback (older CLI without the system events)
bg = BgTracker()
def user(content):
    return {"type": "user", "message": {"content": content}}
bg.feed(user([{"type": "tool_result", "content": "Command running in background with ID: b1. Output..."}]))
bg.feed(user([{"type": "tool_result", "content": [{"type": "text", "text": "Async agent launched\nagentId: a2 (internal)"}]}]))
bg.feed(user([{"type": "tool_result", "content": "Monitor started (task m3, timeout 300000ms)"}]))
bg.feed(user([{"type": "tool_result", "content": '{"success":true,"resumedAgentId":"a4"}'}]))
assert bg.pending == {"b1", "a2", "m3", "a4"}, bg.pending
bg.feed(user("<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>"))
bg.feed(user([{"type": "tool_result", "content": "Successfully stopped task: m3 (sleep)"}]))
bg.feed(user("<task-notification><task-id>a2</task-id><status>failed</status></task-notification>"))
assert bg.pending == {"a4"}, bg.pending

# 4. once structured events appear, the list they carry wins over stale text matches
bg.feed({"type": "system", "subtype": "background_tasks_changed", "tasks": []})
assert bg.pending == set() and bg.structured
print("BgTracker self-check OK")
