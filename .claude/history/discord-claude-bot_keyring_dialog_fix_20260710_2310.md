# Keyring dialog on monitor — cause + fix (2026-07-10 23:10)

## Symptom
Monitor showed a GNOME dialog: **"Choose password for new keyring"** over a white
kiosk page. Pi has no keyboard/mouse, so it was undismissable locally.

## Cause
The media stack (option b: `cage → chromium --kiosk`, built earlier today) launched
Chromium for the first time with a fresh profile (`~/.config/chromium-media`).
Chromium asked gnome-keyring for its os_crypt storage key; no keyring exists on
this Pi (`~/.local/share/keyrings/` is empty), so `gcr-prompter` popped the
create-keyring dialog inside cage. The white background was Chromium's
`about:blank` idle page. Harmless, but blocking and unclickable.

## Fix
1. `media.py` — added `--password-store=basic` to `CHROMIUM_FLAGS` (plaintext
   profile store, never touches gnome-keyring). Permanent fix.
2. Killed `gcr-prompter` (dialog gone) and the idle cage/chromium process group
   (screen back to console). Nothing was playing.
3. Scheduled `systemctl restart discord-claude` via transient systemd timer
   (`restart-discord-claude-once`, +120 s) so the running bot picks up the new
   flag — delayed so the in-flight Claude task could reply first.

## Notes
- Do NOT create a keyring / set a keyring password on this Pi; kiosk Chromium
  stores nothing sensitive and `basic` keeps it prompt-free.
- Pattern for future GUI prompts on the monitor: no local input exists — find
  the prompter process (`gcr-prompter`, polkit agent, etc.) and kill it remotely.
