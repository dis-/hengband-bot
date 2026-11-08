"""Freeze the n1-b life-341 Angband 49F / D49 loop boards of 2026-11-08.

Source: the viewing Magic-Eater n1-b life-341 (Lv34), retired at 04:22 after three
``loop-detected`` stops, copied read-only from the viewing server:

  CAPTURES/20261108-040051-loop-detected   dungeon 12, 49F: a sleeping 巨大首なし (race 653)
                                           at [28,35]; retreat '2' at [35,36] (distance 7),
                                           explore '8' back at [36,36] (distance 8)
  CAPTURES/20261108-041846-loop-detected   Angband 49F: a sleeping 混沌の落とし子 (race 574)
                                           at [34,7]; retreat at [30,9] (4), explore back at
                                           [29,9]/[29,8] (5)
  INCIDENTS/20261108-041841-loop-detected  that stop's policy-state.json (the retreat vetoes
                                           and the deferred loot)
  SNAPSHOTS (jsonlog/snapshots/snapshots-current.jsonl.gz) and the decision log's tail: the
                                           restarted process of 04:18 up to the 04:20 stop
                                           (three sleeping 青オクタロック, race 1411)

The 04:20 case is a checkpoint (latch_onset_capture.checkpoint_bytes) of a fresh policy
that replayed the restarted process's snapshot lines through the CLI's consumption path and
choose_key (the scratch tool replay341c: every record in order, the last k boards of a turn
decided for its k decision rows), on main 8b9d247f31, before the board of turn 2480700:
its decisions from turn 2480300 to the stop match the recorded rows key for key.  Only this
extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import base64
import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge


EVIDENCE = Path("C:/Users/user/AppData/Local/Temp/claude/9e958c6758adbc4a/"
                "ef7d40aa-c4f0-4dea-a0f2-added5068e23/scratchpad/ev341")
GAME = Path("C:/hengband/lib/edit")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-341-loops-20261108.json.gz"


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def compact(decisions, turns):
    return [{"turn": row["turn"], "reason": row["reason"], "key": row["key"]}
            for row in decisions if row.get("turn") in turns and row.get("reason") != "loop-detected"]


def capture_case(name, last):
    capture = EVIDENCE / name
    boards = rows(capture / "state.jsonl.gz")[:last + 1]
    turns = {board["turn"] for board in boards}
    return {"boards": boards, "decisions": compact(rows(capture / "bot-decisions.jsonl.gz"), turns)}


def main():
    cases = {
        "0400": capture_case("20261108-040051-loop-detected", 62),
        "0418": capture_case("20261108-041846-loop-detected", 60),
    }
    state = json.loads((EVIDENCE / "inc041841/policy-state.json").read_text(encoding="utf-8"))["state"]
    cases["0418"]["avoid_cells"] = state["_engagement_avoid_cells"]
    cases["0418"]["deferred_loot"] = state["_nav_ledger_deferred_loot"]
    first = (EVIDENCE / "main-2480700.pkl.board.json").read_text(encoding="utf-8")
    later = {}
    for line in gzip.open(EVIDENCE / "proc0420-lines.jsonl.gz", "rt", encoding="utf-8"):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("type") == "player_turn" and 2480700 < record["turn"] <= 2481036:
            later[record["turn"]] = record  # the last board of a turn is the decided one
    boards = [json.loads(first), *(later[turn] for turn in sorted(later))]
    turns = {board["turn"] for board in boards}
    cases["0420"] = {
        "checkpoint": base64.b64encode((EVIDENCE / "main-2480700.pkl").read_bytes()).decode("ascii"),
        "boards": boards,
        "decisions": compact(rows(EVIDENCE / "tail1200.jsonl.gz"), turns),
    }
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    ids = {row["race_id"] for case in cases.values() for board in case["boards"]
           for field in ("visible_monsters", "detected_monsters") for row in board.get(field, [])}
    fixture = {
        "source": "n1-b life-341 captures (copied from the viewing server)",
        "cases": cases,
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, {name: len(case["boards"]) for name, case in cases.items()})


if __name__ == "__main__":
    main()
