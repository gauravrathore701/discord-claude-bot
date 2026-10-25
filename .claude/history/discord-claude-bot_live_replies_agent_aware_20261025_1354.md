# Live replies, background-work aware idle timeout, reply quotes (2026-10-25)

Gaurav asked for three changes to the Discord -> Claude bridge (`bot.py`).

## 1. Background work counts as activity
- New `BgTracker` follows pending background work from the stream. Experiment with the CLI
  (bg Bash `sleep`, bg Agent, stdin kept open) showed structured `system` events:
  - `background_tasks_changed` -> `{"tasks":[{"task_id":"bnv1op7qb","task_type":"local_bash"}, {"task_id":"a7fe…","task_type":"local_agent"}]}` (full list, authoritative)
  - `task_started` (`task_id`, `is_backgrounded: true`), `task_notification` (`task_id`, `status: completed`), `task_updated`.
- Text patterns (`running in background with ID:`, `agentId:`, `Monitor started (task`,
  `resumedAgentId`, `<task-notification>`, `Successfully stopped task:`) are a fallback only.
- `idle_watch` skips the idle kill while anything is pending; hard cap unchanged.

## 2. Each reply posted as soon as it is ready
- `run_claude(..., post)` calls `post(text)` on every `result` event; returns only unposted text
  (timeout/idle notice, stderr, no output, failed posts). History still logs all results joined.
- `do_task` got `post()` (same extract_sends / checklist / send_long / send_files / Slack path) and
  `drop_status()` (status deleted once, at the first reply).

## 3. Stay available + quotes
- On a result stdin closes only when nothing is pending; otherwise new messages are injected as
  `[Gaurav] …` (`[Gaurav, mid-task] …` before the first result) and the next result replies to them.
- 60s-quiet safety valve closes stdin when nothing is pending.
- Messages arriving after stdin closed but before exit: ⏳ reaction, run as the next task (one queued max).
- `quote_prefix()` adds `[Replying to: «…»]` / `[Replying to your message: «…»]` (800 chars) for Discord replies.

## Tests
- `.claude/tests/check_bg_tracker.py` (real trimmed stream fixture) -> OK.
- Offline end-to-end `run_claude` with haiku: plain task -> 1 post, exit in 4s; bg sleep 25 + injected
  message -> posts STARTED, BANANA, FINISHED, exit at 31s, remainder empty.

Backup: `bot.py.bak-20261025b`. Service NOT restarted (needs Gaurav's go-ahead).
