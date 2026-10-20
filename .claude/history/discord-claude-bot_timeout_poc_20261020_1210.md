# Task timeout POC — why it exists, can it go (2026-10-20 12:10)
- Origin: TASK_TIMEOUT=600 came with the initial commit (template default), never a recorded design reason.
  Per-channel override added 2026-08-05 after a zh task died at 600s (d7e6a0a). projects channel still 600s.
- What it guards: one task per channel ("Already running…"), so a hung CLI would lock the channel; also runaway usage.
  !cancel already covers the manual case.
- What it costs: kill = no result event → session_id/chat history not updated for that turn; work cut mid-step
  (today 11:4x the queue-build turn in #projects was killed at 600s).
- Data, 30 days of ~/.claude/projects transcripts (incl. non-bot sessions): 1249 turns, median 18s, p90 178s, p99 37m.
  >10m: 42 turns (34 Animations, 5 Projects, 3 zh). Gap between consecutive events: p99 100s, p99.9 600s, >15m only 10.
- Proposal (not built): replace wall-clock limit with idle timeout (no stream event for 15m → kill) + hard cap ~3h.

## 12:2x built (Gaurav: "yes build it")
- bot.py: IDLE_TIMEOUT (env TASK_IDLE_TIMEOUT, 900s) watcher next to pump(); wall-clock limit = hard cap (TASK_TIMEOUT default 10800).
  Messages: "Stopped: no activity for 15m (idle limit)" / "Timed out after … hard cap". !status shows both.
- CLI spawned with start_new_session=True; kill_tree() = killpg SIGKILL for idle/cap/!cancel (plain kill left tool children holding stdout → proc.wait hung).
- .env: TASK_TIMEOUT 600 → 10800, + TASK_IDLE_TIMEOUT=900 (backup .env.bak-20261020). Per-channel caps unchanged (zh/blog/finance 25m, pi-ops/daily-tasks 10m, animation 3h).
- Tested with fake CLI: chatty finishes; silent killed at idle (15s poll); cap hit; cancel leaves no children.
- Backup bot.py.bak-20261020. NOT restarted yet — waiting for Gaurav's yes.
