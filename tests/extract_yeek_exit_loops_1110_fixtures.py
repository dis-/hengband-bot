"""Extract tests/fixtures/yeek-exit-loops-1110/.

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/stops-1110/:

- ``hellbeast-1937``: n1-c life-193 (Magic-Eater Lv8, Yeek cave 1F, build 180ea6743)
  captures/20261110-193659-loop-detected: every board of state.jsonl (turns 233895-235586)
  and the decision rows of those turns.
- ``depth-gate-1628``: n1-b life-365 (Magic-Eater Lv32, Outpost, build c6e2443b2)
  captures/20261110-162848-town-blocked-owner-retired-burst: the restarted process's rows
  of state.jsonl (from its first board, turn 4990125, to the stop at 4990244, boards and
  the knowledge / store / character responses in order) and the decision rows.

Each fixture holds its rows, the decision rows (turn, sequence, key, reason, position) and
the monster knowledge (lib/edit/MonraceDefinitions.jsonc) of every race on the boards.

    python tests/extract_yeek_exit_loops_1110_fixtures.py
"""
import gzip
import json
from dataclasses import asdict
from pathlib import Path

from extract_n1c_183_stairs_explore_loop_1109_fixtures import GAME, lines
from hengbot.monrace_knowledge import load_monrace_knowledge

ROOT = Path("C:/hengband-backups/pdca/captures/stops-1110")
OUTPUT = Path(__file__).with_name("fixtures") / "yeek-exit-loops-1110"
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position")
HELLBEAST = ROOT / "n1-c/life-193/captures/20261110-193659-loop-detected"
DEPTH_GATE = ROOT / "n1-b/life-365/captures/20261110-162848-town-blocked-owner-retired-burst"
RESTART_ROW = 85  # the restarted process's first board (decision sequence 0, turn 4990125)


def write(name, rows, decisions, races):
    turns = {row["turn"] for row in rows if row.get("type") == "player_turn"}
    ids = {monster["race_id"] for row in rows
           for field in ("visible_monsters", "detected_monsters") for monster in row.get(field, [])}
    fixture = {
        "rows": rows,
        "decisions": [{field: row.get(field) for field in DECISION_FIELDS}
                      for row in decisions if row.get("turn") in turns],
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(json.dumps(fixture, ensure_ascii=False, default=sorted,
                                       separators=(",", ":")).encode("utf-8"), mtime=0)
    (OUTPUT / f"{name}.json.gz").write_bytes(payload)
    print(name, len(rows), len(fixture["decisions"]), len(payload))


def main() -> None:
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    write("hellbeast-1937",
          [row for row in lines(HELLBEAST / "state.jsonl.gz") if row.get("type") == "player_turn"],
          lines(HELLBEAST / "bot-decisions.jsonl.gz"), races)
    rows = lines(DEPTH_GATE / "state.jsonl.gz")[RESTART_ROW:]
    decisions = [row for row in lines(DEPTH_GATE / "bot-decisions.jsonl.gz")
                 if row.get("turn", 0) >= rows[0]["turn"]]
    # The restarted process numbers its decisions from 0 (the stopped one's end at 4990125).
    restart = next(index for index, row in enumerate(decisions)
                   if row.get("decision_sequence") == 0)
    write("depth-gate-1628", rows, decisions[restart:], races)


if __name__ == "__main__":
    main()
