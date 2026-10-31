"""Freeze the boards where fundraising swapped a burning lantern for a torch (#47).

Sources (read-only, C:/hengband-backups/pdca/captures):

- n1c-wander-1031 (n1-c life-053, 2026-10-31 03:57:41, 鉄獄1階 fundraising):
  state.jsonl player_turn boards 85521, 85529, 85534 and the decision rows
  of the same turns from jsonlog/bot-decisions.jsonl.  At 85529 the worn
  Brass Lantern {average} burns (light radius 2), one flask of oil and four
  known torches are carried; decision 847 posted fundraise:wield-light 'we'
  and 85534 shows the torch worn (radius 1).
- n1c-equip-loop-1031 (n1-c life-055): bot-decisions.jsonl rows 938/939 and
  2604/2605 (fundraise:refill-light then fundraise:wield-light 'wf', light
  radius 2 -> 1).  The capture holds no board of those turns, so only the
  decision rows are kept as evidence.

Only this extraction tool reads the captures; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures")
OUTPUT = Path(__file__).with_name("fixtures") / "light-no-torch-swap-1031.json.gz"
TURNS = (85521, 85529, 85534)
FIELDS = ("decision_sequence", "turn", "reason", "key", "light_radius")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path):
    with open(path, encoding="utf-8", errors="replace") as stream:
        for number, line in enumerate(stream):
            try:
                yield number, json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    wander = ROOT / "n1c-wander-1031"
    boards = {}
    for _, row in rows(wander / "state.jsonl"):
        if row.get("type") == "player_turn" and row.get("turn") in TURNS:
            boards.setdefault(row["turn"], row)
        if row.get("turn", 0) > max(TURNS):
            break
    decisions = {}
    for _, row in rows(wander / "jsonlog" / "bot-decisions.jsonl"):
        if row.get("turn") in TURNS and row.get("reason"):
            decisions.setdefault(row["turn"], {k: row.get(k) for k in FIELDS})
        if row.get("turn", 0) > max(TURNS):
            break
    loop = ROOT / "n1c-equip-loop-1031" / "bot-decisions.jsonl"
    life055 = {number: {k: row.get(k) for k in FIELDS}
               for number, row in rows(loop) if number in (938, 939, 2604, 2605)}
    cases = {
        "life-053": dict(sources={"state.jsonl": sha(wander / "state.jsonl")},
                         boards=[boards[turn] for turn in TURNS],
                         decisions=[decisions.get(turn) for turn in TURNS]),
        "life-055": dict(sources={"bot-decisions.jsonl": sha(loop)},
                         decisions=[life055[number] for number in (938, 939, 2604, 2605)]),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
