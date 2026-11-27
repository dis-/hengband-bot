"""Freeze n1-b life-419's Morivant gold piles and the Outpost board the loot walk took after the Inn teleport.

Source: n1-b life-419 (Zombie Magic-Eater CL50, build bot-da2924aea) on hengband.net, owner-halt
loop-detected 2026-11-27 11:06:54 (turn 11262708).  Copied to
C:/hengband-backups/pdca/captures/n1b-419-town-seek-loot-loop-1127: ``state-tail600.jsonl`` and
``decisions-tail600.jsonl`` (the last 600 lines of ~/hengbot-soak/n1-b/life-419/state.jsonl and
jsonlog/bot-decisions.jsonl) and ``incident-captures/20261127-110654-loop-detected`` (its
``town-arrival/policy.pkl``, the policy at the visit's arrival, turn 11259421, and
``policy-state.json``, the policy at the halt).

The fixture keeps the boards of ``TURNS``: Morivant (town id 2) at 11260613, the gold at (34,79)
in view, and at 11261289, the gold at (64,180) in view; the Outpost (town id 0) at 11262113, the
first board after the Inn teleport (me-staff:return-outpost '1ma'), and the decision rows of the
Outpost walk and the stop (turns 11262110-11262708: turn, reason, key, position, loot).  The
magic-eater device lists come from the arrival checkpoint (turns 11259113-11259149) and the staff
sequence's absorbed counts, stage and remaining staffs from the halt's policy-state.json.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-419-town-loot-memory-1127.json.gz"
TURNS = (11260613, 11261289, 11262113)
WALK = (11262110, 11262708)


def main():
    from hengbot.latch_onset_capture import restore_checkpoint_bytes
    from hengbot.policy import HengbotPolicy
    from hengbot.town_arrival_checkpoint import policy_file

    incident = ROOT / "incident-captures" / "20261127-110654-loop-detected"
    states = [json.loads(line) for line in (ROOT / "state-tail600.jsonl").open(encoding="utf-8")]
    boards = []
    for turn in TURNS:
        same = [row for row in states if row.get("type") == "player_turn" and row["turn"] == turn]
        boards.append(same[-1])
    decisions = [json.loads(line) for line in (ROOT / "decisions-tail600.jsonl").open(encoding="utf-8")]
    recorded = [{"turn": row["turn"], "reason": row["reason"], "key": row["key"],
                 "position": [row["position"]["y"], row["position"]["x"]],
                 "loot": row.get("loot")}
                for row in decisions if WALK[0] <= row["turn"] <= WALK[1]]
    arrival = restore_checkpoint_bytes(HengbotPolicy, policy_file(incident / "town-arrival").read_bytes())
    device_lists = {kind: [turn, [dict(row) for row in rows]]
                    for kind, (turn, rows) in arrival._me_device_lists.items()}
    halt = json.loads((incident / "policy-state.json").read_text(encoding="utf-8"))["state"]
    sequence = halt["_me_staff_sequence"]
    case = dict(source="n1b-419-town-seek-loot-loop-1127", boards=boards, recorded=recorded,
                device_lists=device_lists,
                staff_sequence={name: sequence[name] for name in ("absorbed", "stage", "remaining")})
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} {len(recorded)}\n")


if __name__ == "__main__":
    main()
