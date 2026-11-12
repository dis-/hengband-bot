"""Extract tests/fixtures/n1b-378-1112/unseen-stairs-2114.json.gz.

Source, copied read-only from the viewing server: n1-b life-378 (Lv34, Angband 30F, build
bot-deeed02f5) ~/hengbot-soak/n1-b/life-378/incident-captures/20261112-211405-loop-detected/
snapshots/snapshots-current.jsonl.gz (the boards) and the decision rows of
captures/20261112-211407-loop-detected/bot-decisions.jsonl.gz with the decision tail of the
incident capture (decision-tail.jsonl).  The fixture holds the boards from the walk into the
floating orb's room ((58,50), turn 2191696) to the first rest after the detection (turn
2191970), their decision rows (turn, sequence, key, reason, position, messages) and the monster
knowledge of every race on the boards.

    python tests/extract_n1b_378_unseen_stairs_1112_fixture.py <incident dir> <capture dir>
"""
import dataclasses
import gzip
import json
import sys
from pathlib import Path

from extract_n1c_183_stairs_explore_loop_1109_fixtures import GAME, lines, ring_rows
from hengbot.monrace_knowledge import load_monrace_knowledge

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-378-1112"
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position", "messages")
FIRST, LAST = 2191696, 2191970


def decision_rows(path: Path) -> list:
    rows = []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass  # the tail's first line is cut
    return rows


def main(incident: Path, capture: Path) -> None:
    boards = [row for row in ring_rows((incident / "snapshots" / "snapshots-current.jsonl.gz")
                                       .read_bytes())
              if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST]
    turns = {row["turn"] for row in boards}
    decisions = {}
    for row in [*decision_rows(incident / "decision-tail.jsonl"),
                *lines(capture / "bot-decisions.jsonl.gz")]:
        if row.get("turn") in turns:
            decisions.setdefault((row["decision_sequence"], row["reason"]),
                                 {field: row.get(field) for field in DECISION_FIELDS})
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    ids = {monster["race_id"] for row in boards
           for field in ("visible_monsters", "detected_monsters") for monster in row.get(field, [])}
    fixture = {
        "rows": boards,
        "decisions": sorted(decisions.values(), key=lambda row: row["decision_sequence"]),
        "monraces": {key: dataclasses.asdict(races[key]) for key in sorted(ids)},
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(json.dumps(fixture, ensure_ascii=False, default=sorted,
                                       separators=(",", ":")).encode("utf-8"), mtime=0)
    (OUTPUT / "unseen-stairs-2114.json.gz").write_bytes(payload)
    print(len(boards), len(fixture["decisions"]), len(payload))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
