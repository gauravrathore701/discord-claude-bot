# Mid-task message injection (2026-10-20 12:20)
Ask: correcting a running task ("NAS not NASA") got "Already running… !cancel". Want it fed into the running session.
- CLI 2.1.296 supports `-p --input-format stream-json`; a user line written to stdin mid-run is picked up at the next tool boundary, same turn (tested raw + through run_claude with haiku).
- bot.py: user_msg(); prompt now on stdin (no argv limit either); state.active_stdin/injected; stdin closed on first result;
  all result texts joined; on_message writes `[Gaurav, mid-task] text` + ↪️ reaction. Webhooks/attachments → old reply.
- Resume across runs verified (code-word test). Backup bot.py.bak-20261020b. Restart pending Gaurav's yes.
- 12:14 restart queued (Gaurav: yes)
