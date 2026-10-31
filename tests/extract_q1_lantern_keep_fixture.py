"""Freeze the D48 board where the Q1 opening swapped a worn lantern for a torch.

Source (read-only copy of the viewing machine's n1-c life-069, 2026-10-31):
C:/hengband-backups/pdca/captures/d48-q1-light-1031/life-069/

- state.jsonl player_turn 83151 (19:42:02, Outpost, Lv6 zombie Magic-Eater,
  4 gold): worn 真鍮のランタン {並, Q34} (unidentified, light radius 2), no
  oil, 21 known torches.  The next board, 83163, shows a torch worn and the
  lantern in the pack (light radius 1).
- jsonlog/bot-decisions.jsonl decisions 806-810: the Q1 shop purchases and
  in-store-done (83144), then opening-q1:equip-light 'we' (83151), then
  fixedquest:request:approach.
- The knowledge rows (skill_exp, home) and character rows logged before the
  board, and the monster races the board shows or Q1's roster names.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge

ROOT = Path("C:/hengband-backups/pdca/captures/d48-q1-light-1031/life-069")
OUTPUT = Path(__file__).with_name("fixtures") / "q1-lantern-keep-1031.json.gz"
TURN, NEXT_TURN = 83151, 83163
SEQUENCES = range(806, 811)
FIELDS = ("decision_sequence", "turn", "reason", "key", "light_radius")


def rows(path: Path):
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    state = ROOT / "state.jsonl"
    boards, knowledge = {}, []
    for row in rows(state):
        if row.get("turn", 0) > NEXT_TURN:
            break
        if row.get("type") == "player_turn" and row["turn"] in (TURN, NEXT_TURN):
            boards.setdefault(row["turn"], row)
        if row.get("type") == "knowledge" and row.get("turn", 0) <= TURN:
            knowledge.append(row)
    decisions = []
    log = ROOT / "jsonlog" / "bot-decisions.jsonl"
    for row in rows(log):
        if row.get("decision_sequence") in SEQUENCES:
            decisions.append({key: row.get(key) for key in FIELDS})
        if row.get("decision_sequence", 0) > max(SEQUENCES):
            break
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    q1 = load_quest_knowledge(find_quest_definitions(Path.cwd()))[1]
    ids = {race for race, _ in q1.threat_roster}
    board = boards[TURN]
    ids.update(row["race_id"] for field in ("visible_monsters", "detected_monsters")
               for row in board.get(field, []))
    after = boards[NEXT_TURN]
    case = dict(
        snapshot=board,
        next_light=[item for item in after["equipment"] if item["slot"] == "light"],
        decisions=decisions,
        knowledge=knowledge,
        monraces={key: asdict(races[key]) for key in sorted(ids)},
        state={"modes_and_latches": {}},
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (state, log)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
