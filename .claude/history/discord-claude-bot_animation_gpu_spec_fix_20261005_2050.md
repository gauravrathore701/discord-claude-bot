# animation channel note: GPU spec fix — 2026-10-05 20:50

## Change
`.claude/channels.json` -> channels.animation.notes[5]
("GPU NODE AVAILABLE" note)

- was: `GTX 1660 Ti`
- now: `GTX 1650 4 GB VRAM`

1 string replaced, nothing else touched.
JSON re-parsed OK after edit.

## Why
Wrong card on record. Oct 2 inventory over SSH:
`nvidia-smi` -> NVIDIA GeForce GTX 1650, 4 GB,
driver 566.36. Cycles lists it twice (CUDA + OPTIX).
Benchmark 1080p 64spp OptiX: peak VRAM 1442/4096 MB.
Source: Animations/.claude/history/
Animations_pc_gpu_node_installed_20261002_1235.md

4 GB is the binding limit; a 1660 Ti (6 GB) on
record invites scenes that OOM the real card.

## Backup
`.claude/channels.json.bak-20261005`

## Pending
Needs `systemctl restart discord-claude` to load.
Not restarted — awaiting Gaurav's yes.
