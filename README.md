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

Write each policy decision to a structured JSONL file for live inspection:

```powershell
python -m hengbot --state-file bot-state.jsonl --send-to-window `
  --decision-log jsonlog\bot-decisions.jsonl
powershell -File scripts\watch-decisions.ps1
```

The viewer shows the current objective and policy reason alongside the next key,
floor, position, HP/MP, supplies, visible hostiles, and store context.

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
5. **Return to town** when the 23-slot pack is full or food is running out.
   Use only an identified Word of Recall scroll; otherwise seek upstairs, and
   never descend again before reaching town. A full pack also blocks re-entry.
6. **Pick up** loot on the current tile.
7. **Descend** when standing on downstairs (`>`); when hurt, safe, and not
   bleeding, rest to recover first, up to a bounded number of turns.
8. **Beeline to a known downstairs** through corridors and closed doors.
9. **Eat** when hungry and safe.
10. **Hunt** an easy, nearby monster for XP while no downstairs is known.
11. **Explore** toward the unknown. The frontier search is door-aware (a closed
    door is opened by moving *orthogonally* into it) and edge-aware (it heads for
    the rim of the view radius), with a visit penalty that spreads coverage.
12. **Anti-stuck**: take any known stairs to a fresh floor, or wander to the
    least-visited neighbour. The bot never freezes in place indefinitely, and a
    livelock guard breaks out of any move the game keeps rejecting.

Most decisions are a single key. Item use is a short macro (a command letter
plus the inventory letter, e.g. `qc`); the follow loop nudges the game with
Escape if a snapshot fails to arrive, clearing any message/`-more-` prompt.
Exact duplicate command snapshots are throttled to one retry every two seconds,
which prevents Windows input from accumulating while still allowing rejected
moves to reach the policy's bounded livelock breaker.

This requires the extended snapshot from the `codex/bot-json-output` build
(PR #5488), which also emits player status effects, inventory, and equipment.

The strict snapshot mode (identified by `player.class_id`) also enables the
pre-depth-20 town workflow:

- keep five free pack slots and depth-scaled Word of Recall stock (1/3/6/9/10)
- carry five food items, a lantern with five oil flasks, and three Teleport
  scrolls before entering depth 10 or deeper
- return when required stock is destroyed, food is exhausted, or the pack fills
- protect equipment in Home and sell only unaware potions/scrolls found below 20
- raise money on Yeek cave level 1 without using downstairs; when prepared, use
  five Treasure Detection scrolls over five separate mining trips
- after conquering Yeek cave, collect visible drops, return, finish the normal
  town routine, buy rumors until Angband recall unlocks, then recall to Angband

Hengband emits only visible monster identity, a coarse health band, observable
status effects, and attitude. Position is joined through the visible map's
monster index. Exact HP, speed, and capabilities are not emitted: the bot locates
`lib/edit/MonraceDefinitions.jsonc` from the state-file path and derives static
race knowledge by matching each visible monster's `race_id`. Use
`--monrace-definitions PATH` to override that lookup.

Player and item data follows the same observable-information rule. Hunger is a
HUD band (`fainting`, `weak`, `hungry`, `normal`, `full`, or `gorged`) and recall
is only an active/inactive flag; exact internal counters are not emitted.
Unaware items omit `sval`, unidentified items omit charges and fuel, and Home or
Museum stock uses those same redaction rules without exposing an internal price.
