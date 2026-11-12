"""Freeze n1-b life-378's Quest 25 boards 01:44:57-01:45:48 (2026-11-13) for the spent-balls and sweep tests.

Source: n1-b life-378 (now resumed as life-382) on hengband.net,
~/hengbot-soak/n1-b/life-382/incident-captures/20261113-014655-loop-detected/ (decision-tail.jsonl
and snapshots/snapshots-current.jsonl.gz), copied to the implementer's scratch: decisions 5540-5900
of the process that stopped at 01:46:55 -- the quylthulgs' balls from [5,2] at [7,14] (5551-5618),
the list reads and recharge rests that followed (5619-5645), the walk to the tome, and the sweep's
detections (5833, 5840 and the failed 5884).  The absorbed powers are the character dump the
bot read at 01:33 (town-arrival sidecar ``_character_dump_path``): name and count per kind.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import collections
import gzip
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_174_q25_loops_1109_fixture import ring_rows

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-378-q25-spent-balls-1113.json.gz"
FIRST, LAST = 5540, 5900
KINDS = {"[杖]": "staff", "[魔法棒]": "wand", "[ロッド]": "rod"}


def absorbed(dump: str) -> dict:
    """{kind: [[name, count], ...]} of the dump's 『取り込んだ魔法道具』."""
    found, kind = {}, None
    for line in dump.splitlines():
        stripped = line.strip()
        if stripped in KINDS:
            kind = KINDS[stripped]
            found[kind] = []
            continue
        if kind is None:
            continue
        if not stripped or stripped.startswith("["):
            if found.get(kind):
                kind = None
            continue
        found[kind] += [[name.strip(), int(count)] for name, count in
                        re.findall(r"(\S[^()]*?)\s*\(\s*(\d+)\)", line)]
    return found


def main():
    rows = ring_rows(ROOT / "snapshots-current.jsonl.gz")
    decisions = []
    with (ROOT / "decision-tail.jsonl").open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if FIRST <= row.get("decision_sequence", -1) <= LAST and "reason" in row:
                decisions.append(row)
    by_turn = collections.defaultdict(list)
    for row in rows:
        if row.get("type") == "player_turn":
            by_turn[row["turn"]].append(row)
    need = collections.Counter(row["turn"] for row in decisions)
    used = collections.Counter()
    boards, recorded = [], []
    for row in decisions:
        same = by_turn[row["turn"]]
        board = same[len(same) - need[row["turn"]] + used[row["turn"]]]
        used[row["turn"]] += 1
        assert (board["player"]["y"], board["player"]["x"]) == (row["position"]["y"], row["position"]["x"])
        boards.append(dict(board, messages=row["messages"]))
        recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                         "reason": row["reason"], "key": row["key"]})
    dump = (ROOT / "dump-0133.txt").read_bytes().decode("euc-jp", "replace")
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1b-378-q25-spent-balls-1113", boards=boards, recorded=recorded,
                absorbed=absorbed(dump),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races})
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} "
                     f"{recorded[0]['sequence']}-{recorded[-1]['sequence']} {sorted(case['absorbed'])}\n")


if __name__ == "__main__":
    main()
