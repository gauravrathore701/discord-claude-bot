# Image/file sending from bot

- Claude writes `[[send: /abs/path]]` on its own line → bot strips it, uploads file after the answer.
- `extract_sends()` + `send_files()` in bot.py; 10 files/msg, 10 MB cap, missing/oversize → ⚠️ line.
- New base point `send_files` (omittable) tells Claude the marker.
- Slack relay gets the answer with markers stripped (no files mirrored).
- Backup: bot.py.bak-20261024. Needs `discord-claude` restart to go live.
