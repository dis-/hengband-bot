"""Freeze the n1-c life-098 Software bug swarm boards of 2026-11-02 (breeder-swarm-1102).

Source: the viewing Magic-Eater n1-c life-098 (Lv31, 412 max HP), 鉄獄24階
random quest 41, copied read-only to
C:/hengband-backups/pdca/captures/n1c-breeder-supplies-1102/:

  restart  the loop-detected stop of 00:10:35 (turn 2200908) and the restarted
           process (00:10:42, its skill row at turn 2200918): boards of turns
           2200874-2200901 (the stopped process, breakthrough-latched) and
           2200918-2201001 (the new one, firing bolts again).  They are in the
           ring generation snapshots-20261102-001207-473375 of the 00:13:16
           capture.
  engage   the same generation: boards of turns 2199675-2199905, the first
           ソフトウェア・バグ in view (00:10:09) and the fight that followed.
  swarm    the 00:13:16 capture's live ring: boards of turns 2207334-2207416,
           seven or eight ソフトウェア・バグ (race 246) beside the player while it
           searched (``search``).

The fixture keeps the boards, the last skill-proficiency and Home knowledge
rows of the generation, the monster knowledge of the boards' monsters and the
compact decision rows (life-098-dec.jsonl) of the same turns.  Only this
extraction tool reads the captures; the committed tests read the fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-breeder-supplies-1102")
CAPTURE = ROOT / "incident-captures/20261102-001316-loop-detected/snapshots"
GENERATION = CAPTURE / "snapshots-20261102-001207-473375.jsonl.gz"
RING = CAPTURE / "snapshots-current.jsonl.gz"
DECISIONS = ROOT / "life-098-dec.jsonl"
OUTPUT = Path(__file__).with_name("fixtures") / "breeder-swarm-20261102.json.gz"
SPANS = {
    "engage": (GENERATION, ((2199675, 2199905),)),
    "restart": (GENERATION, ((2200874, 2200901), (2200918, 2201001))),
    "swarm": (RING, ((2207334, 2207416),)),
}


def generation_rows(path: Path) -> list[dict]:
    rows = []
    with gzip.open(path, "rb") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a row cut by the rotation
    return rows


def boards(rows, spans):
    chosen, turns = [], set()
    for row in rows:
        if (row.get("type") == "player_turn" and row["turn"] not in turns
                and any(first <= row["turn"] <= last for first, last in spans)):
            turns.add(row["turn"])
            chosen.append(row)
    for first, last in spans:
        assert {first, last} <= turns, (first, last)
    return chosen


def last_knowledge(rows, category):
    return next(row for row in reversed(rows) if row.get("type") == "knowledge"
                and row["knowledge"]["category"] == category)


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    generation = generation_rows(GENERATION)
    sources = {GENERATION: generation, RING: ring_rows(RING)}
    fixture = {"source": f"{CAPTURE.parent} (copied from the viewing server)"}
    turns = set()
    for name, (path, spans) in SPANS.items():
        fixture[name] = boards(sources[path], spans)
        turns |= {raw["turn"] for raw in fixture[name]}
    fixture["skill"] = last_knowledge(generation, "skill_exp")
    fixture["home"] = last_knowledge(generation, "home")
    ids = {row["race_id"] for name in SPANS for raw in fixture[name]
           for field in ("visible_monsters", "detected_monsters")
           for row in raw.get(field, [])}
    fixture["monraces"] = {key: asdict(races[key]) for key in sorted(ids)}
    rows = []
    for line in DECISIONS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("turn") in turns:
            rows.append({"turn": row["turn"], "reason": row["r"], "key": row["k"]})
    fixture["decisions"] = rows
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
