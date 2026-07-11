# Hengband Bot Client

Experimental external bot for Hengband's `--bot-json-output` mode.

The first milestone is intentionally small:

- read JSON Lines snapshots emitted before player input
- convert snapshots into a typed state model
- choose one conservative next key
- print the key so an input adapter can consume it later

## Usage

From this directory:

```powershell
python -m hengbot --state-file ..\.worktrees\bot-json-output\bot-state.jsonl --once
```

Or follow the file continuously:

```powershell
python -m hengbot --state-file ..\.worktrees\bot-json-output\bot-state.jsonl
```

To send chosen keys to a running Hengband window. The default target is the
Windows class name `ANGBAND`:

```powershell
python -m hengbot --state-file ..\.worktrees\bot-json-output\bot-state.jsonl --send-to-window
```

To inspect visible windows:

```powershell
python -m hengbot --state-file ..\.worktrees\bot-json-output\bot-state.jsonl --list-windows
```

## Current Policy

`HengbotPolicy` is goal-seeking: survive, gain levels, and keep descending
toward the bottom of the dungeon. Each snapshot is resolved to a key, in
priority order:

1. **Emergency consumables** — read a Teleport scroll when about to die with
   enemies near, quaff a Healing potion when badly hurt, or eat before fainting.
   Only *identified* items are used, matched by category and sval.
2. **Ride out confusion** in place when it is safe, rather than stumbling.
3. **Flee** when HP is low, swarmed, or too afraid to fight — step away, escape
   by stairs when desperate, or read a relocation scroll when cornered.
4. **Melee** an adjacent hostile, weakest (and sleeping) first — unless afraid.
5. **Pick up** loot on the current tile.
6. **Descend** when standing on downstairs (`>`); when hurt, safe, and not
   bleeding, rest to recover first, up to a bounded number of turns.
7. **Beeline to a known downstairs** through corridors and closed doors.
8. **Eat** when hungry and safe.
9. **Hunt** an easy, nearby monster for XP while no downstairs is known.
10. **Explore** toward the unknown. The frontier search is door-aware (a closed
    door is opened by moving *orthogonally* into it) and edge-aware (it heads for
    the rim of the view radius), with a visit penalty that spreads coverage.
11. **Anti-stuck**: take any known stairs to a fresh floor, or wander to the
    least-visited neighbour. The bot never freezes in place indefinitely, and a
    livelock guard breaks out of any move the game keeps rejecting.

Most decisions are a single key. Item use is a short macro (a command letter
plus the inventory letter, e.g. `qc`); the follow loop nudges the game with
Escape if a snapshot fails to arrive, clearing any message/`-more-` prompt.

This requires the extended snapshot from the `codex/bot-json-output` build
(PR #5488), which also emits player status effects, inventory, and equipment.
