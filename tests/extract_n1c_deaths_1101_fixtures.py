"""Freeze the D57 n1-c death boards of 2026-11-01 (#47, fix-n1c-deaths-1101).

Sources: the automatic player-death captures of the viewing Magic-Eater n1-c
(build c326f0fd6), copied read-only to
C:/hengband-backups/pdca/captures/fix-n1c-deaths-1101/ (one row of ``CASES``
per frozen case):

  n1c-084  life-084 (Lv12, 迷宮14階, 07:49): blinded again and again by a
           充血アイ's gaze, its Cure Critical Wounds spent on the blindness,
           then bitten blind by a ジャイアント・サラマンダー; the emergency
           ladder waited to death.  Ring boards of turns 1287920-1288008.
  n1c-085  life-085 (Lv18, 迷宮11階, 09:24): 『スーパー・グレート・シルバー・
           ゼリー』 ate the worn lantern's light; the refill was refused and
           the jelly, in view by infravision, was dropped from the board.
           Ring boards of turns 1445315-1445339 and 1445613-1445625.

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
from tests.extract_deaths_1101_fixtures import decision_rows
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/fix-n1c-deaths-1101")
FIXTURES = Path(__file__).with_name("fixtures")
# name: (incident capture, ((first turn, last turn), ...))
CASES = {
    "n1c-084": (
        "life-084/incident-captures/20261101-074922-player-death",
        ((1287920, 1288008),)),
    "n1c-085": (
        "life-085/incident-captures/20261101-092407-player-death",
        ((1445315, 1445339), (1445613, 1445625))),
}


def freeze(name: str, capture: str, spans, races, root: Path = ROOT) -> Path:
    incident = root / capture
    rows = ring_rows(incident / "snapshots" / "snapshots-current.jsonl.gz")
    boards, turns, start = [], set(), None
    for index, row in enumerate(rows):
        if (row["type"] == "player_turn" and row["turn"] not in turns
                and any(first <= row["turn"] <= last for first, last in spans)):
            start = index if start is None else start
            turns.add(row["turn"])
            boards.append(row)
    for first, last in spans:
        assert {first, last} <= turns, (name, first, last)
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
    for name, (capture, spans) in CASES.items():
        output = freeze(name, capture, spans, races)
        print(output, output.stat().st_size)


if __name__ == "__main__":
    main()
