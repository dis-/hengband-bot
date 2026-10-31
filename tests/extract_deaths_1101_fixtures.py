"""Freeze the D55 death boards of 2026-10-31/11-01 (#47, fix-deaths-1101).

Sources: the automatic player-death captures of the viewing bots, copied
read-only to C:/hengband-backups/pdca/captures/fix-deaths-1101/ (one row of
``CASES`` per frozen case):

  n1c-077  n1-c life-077 (Lv8 zombie Magic-Eater, Outpost, build 577cd246b,
           2026-11-01 03:25): cornered by 見習戦士 after its last teleport
           scroll, emergency:cornered-attack meleed six times at to-hit -63
           and died; ring boards of turns 442464-442533.
  n1a-450  n1-a life-450 (Lv24 warrior without Free Action, Labyrinth 16F,
           build 2f1c0a886, 2026-10-31 14:47): waiting on Word of Recall
           with 12 Teleportation scrolls it meleed an adjacent アイス・コボルド
           while a ランゴスタ (speed +10, PARALYZE blows) stood two cells away,
           and died paralyzed; ring boards of turns 1268495-1268509.

Each case keeps its player boards (one per turn), the last skill-proficiency
and Home knowledge rows before them, the policy-state ``_me_staff_sequence``
record, the monster knowledge of their monsters and the recorded decision
rows of the same turns.  The snapshot ring copy is the tail of a multi-member
gzip (``ring_rows`` keeps whole members only).  Only this extraction tool
reads the captures; the committed tests read the frozen fixtures alone.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/fix-deaths-1101")
FIXTURES = Path(__file__).with_name("fixtures")
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "player",
                   "position", "threat_prediction")
# name: (incident capture, first turn, last turn)
CASES = {
    "n1c-077": (
        "n1-c/life-077/incident-captures/20261101-032514-player-death",
        442464, 442533),
    "n1a-450": (
        "n1-a/life-450/incident-captures/20261031-144723-player-death",
        1268495, 1268509),
}


def decision_rows(path: Path, turns: set[int]) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a record.
        if row.get("turn") in turns and "reason" in row:
            rows.append({field: row.get(field) for field in DECISION_FIELDS})
    return rows


def freeze(name: str, capture: str, first: int, last: int, races) -> Path:
    incident = ROOT / capture
    rows = ring_rows(incident / "snapshots" / "snapshots-current.jsonl.gz")
    boards, turns, start = [], set(), None
    for index, row in enumerate(rows):
        if (row["type"] == "player_turn" and first <= row["turn"] <= last
                and row["turn"] not in turns):
            start = index if start is None else start
            turns.add(row["turn"])
            boards.append(row)
    assert (boards[0]["turn"], boards[-1]["turn"]) == (first, last), name
    state = json.loads((incident / "policy-state.json").read_text(encoding="utf-8"))
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    fixture = dict(
        source=f"{capture} (copied from the viewing server)",
        boards=boards,
        decisions=decision_rows(incident / "decision-tail.jsonl", turns),
        skill=knowledge(rows, start, "skill_exp"),
        home=knowledge(rows, start, "home"),
        sequence=state["state"].get("_me_staff_sequence"),
        monraces={key: asdict(races[key]) for key in sorted(ids)},
    )
    output = FIXTURES / f"death-{name}-1101.json.gz"
    with gzip.open(output, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    return output


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    for name, (capture, first, last) in CASES.items():
        output = freeze(name, capture, first, last, races)
        print(output, output.stat().st_size)


if __name__ == "__main__":
    main()
