# Failover role gate — 2026-11-11 23:40

- `on_message` now returns early when `/run/failover/role` exists and is not `leader`.
- Written by `pi-infra/failover/leaderd.py` (leaderd@pi / leaderd@vm). Missing file = old behaviour.
- Why: when the Oracle VM leads, the Pi's bot (still running) must not double-reply.
- Needs a restart of discord-claude to take effect (asked Gaurav first).
- Not gated: the bot's own 07:00 task-list post (daily_loop) — only doubles in the short Pi-standby window.
