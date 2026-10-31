"""Freeze the D47 board: n1-c life-065 on Yeek cave 1F (2026-10-31 19:19).

Source (incident capture copied from the viewing bot to
C:/hengband-backups/pdca/captures/n1c-life065-loop-1031):
incident-captures/20261031-191955-loop-detected, build 47df7109c.

The fixture keeps the ring's player_turn row of the first
``fixedquest:q2-travel-needs-funds`` decision (16311, turn 5135804), that
decision row's facts and fundraising purpose, the fundraising mode of the
decision before it (16310: "mine"; the wait itself rewrote it to "prepare"),
the checkpoint's remembered terrain (the floor of the stop; only waits
followed), and the monster races of the board.

The snapshot ring copy is the tail of a multi-member gzip: decoding starts at
the first member header and keeps whole members only.  Only this extraction
tool reads the capture; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_dungeon_loops_1031 import decision_rows
from tests.extract_recall_dungeon_prompt_fixture import ring_rows


CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-life065-loop-1031/"
               "incident-captures/20261031-191955-loop-detected")
OUTPUT = Path(__file__).with_name("fixtures") / "q2-funds-floor-20261031.json.gz"
SEQUENCE = 16311
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "objective",
                   "position", "fundraising", "mining")


def main():
    ring_path = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
    tail_path = CAPTURE / "decision-tail.jsonl"
    state_path = CAPTURE / "policy-state.json"
    decisions = {row.get("decision_sequence"): row for row in decision_rows(tail_path)}
    decision, before = decisions[SEQUENCE], decisions[SEQUENCE - 1]
    board = [row for row in ring_rows(ring_path.read_bytes())
             if row["type"] == "player_turn" and row["turn"] == decision["turn"]][-1]
    checkpoint = json.loads(state_path.read_text(encoding="utf-8"))
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    ids = {row["race_id"] for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    case = dict(
        source=str(CAPTURE),
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (ring_path, tail_path, state_path)},
        board=board,
        decision={field: decision[field] for field in DECISION_FIELDS},
        mode_before=before["fundraising"]["mode"],
        purpose=decision["claim"]["fundraising_purpose"],
        terrain=checkpoint["terrain"],
        modes={field: checkpoint["modes_and_latches"][field]
               for field in ("_crossarea_fundraising_enforced", "_fundraising_runs_started")},
        monraces={str(key): asdict(races[key]) for key in sorted(ids)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
