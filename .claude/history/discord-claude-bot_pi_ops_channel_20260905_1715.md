# pi-ops channel + native ops commands — 2026-09-05

## Request
Gaurav gave channel `1537133272319008798` for running
commands on the Pi, asked for the cheapest model since AI is
mostly not needed, and wanted four things: Claude usage
(session + weekly + reset times), a reboot command, the Pi's
current IP, and a way to write reminders.

## Design decision
All four are implemented **natively in the bot process** —
no Claude call, no tokens. `ops.handle(text)` runs before
the model is ever invoked. AI only gets involved for fuzzy
reminder timing, which is what Gaurav asked for.

## New file: ops.py
- `!usage` — reads `~/.claude/.credentials.json` and calls
  `https://api.anthropic.com/api/oauth/usage` with the OAuth
  bearer token. Reports 5-hour and 7-day utilisation with a
  10-block bar, both reset times converted to IST with a
  relative "in 2h 41m", any active warning/critical limit,
  and the plan name.
- `!ip` — hostname, LAN address (via a UDP connect to
  8.8.8.8, no traffic sent), the interface carrying the
  default route, and the public address from api.ipify.org.
- `!reboot` — **two-step**. Bare `!reboot` arms it for 60s
  and warns that the tunnel, every site and the bot go down.
  `!reboot confirm` then schedules
  `sudo systemd-run --collect --unit=pi-reboot-once
  --on-active=10 systemctl reboot`. Detached on purpose: a
  direct `systemctl reboot` would kill the bot mid-reply
  because it lives in its own unit's cgroup — the same
  problem as blog topic 16.
- `!remind <when> | <message>` — appends one line to
  `daily-script/reminder/reminders.txt`. Accepts `HH:MM`
  (daily recurring), `YYYY-MM-DD HH:MM`, `today HH:MM`,
  `tomorrow HH:MM`, `+2h`, `+30m`. Commas in the message are
  converted to semicolons because the file is
  comma-delimited. Unparseable times return a usage hint
  and tell him to ask Claude in plain English instead.
- `!ops` — lists the commands.

## bot.py changes
- `import ops` added.
- Dispatch inserted at the top of the built-in command
  block: `!reboot` is rejected outside the `pi-ops` channel;
  every other ops command works in any channel.
Backup: `bot.py.bak-20260905`.

## channels.json
Fifth entry: id 1537133272319008798, name `pi-ops`,
root_dir /home/gaurav, project_routing false,
timeout_minutes 10, with 5 notes — never re-implement the
native commands, keep replies short, only fuzzy reminder
timing reaches the model, never call systemctl reboot
directly, and the deletion rule still applies here.

Seeded `sessions/1537133272319008798/model.json` ->
`{"model": "haiku"}` and caveman `full`.

## Tested before restart
`ops.usage()`, `ops.ip()` and `ops.remind()` all run
correctly from the CLI. The test reminder line written
during testing was removed again. `!reboot` was NOT
executed.

## Not done
Bot not restarted yet — awaiting Gaurav's yes.
