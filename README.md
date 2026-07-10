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

The initial policy is deliberately simple and survival-biased:

- step away when HP is below 30% and a visible monster exists
- attack an adjacent visible hostile monster by moving into it
- move toward known downstairs
- otherwise move toward a known tile adjacent to unknown terrain
- prefer less-visited routes when exploring
- wait one turn when no useful move is known

The output is a single Hengband key per snapshot. Consecutive duplicate
snapshots are ignored so the same decision is not sent repeatedly.
