"""Extract tests/fixtures/n1a-508-1111/.

Sources, copied read-only from the viewing server:

- ``empty-wand-1857``: n1-a life-507 (Zombie Warrior Lv27, Angband 12F, RANDOM quest 43, build
  c6e2443b2) C:/hengband-backups/pdca/captures/stops-1110/n1-a/life-507/captures/
  20261110-185704-loop-detected: the last boards of state.jsonl (the hungry ``E j`` of
  「ブリキの魔法棒 {空}」) and the decision rows.
- ``search-12f-1852``: n1-a life-507 (Angband 12F, RANDOM quest 43) .../life-507/captures/
  20261110-185212-stall-floor-dwell-search: every board and the decision rows.
- ``search-44f-0824``: n1-a life-508 (Zombie Warrior Lv37, Angband 44F, RANDOM quest 47)
  C:/hengband-backups/pdca/captures/n1a-508-1111/20261111-082454-stall-floor-dwell-search:
  every board of state.jsonl and the decision rows (``search`` / ``quest-search:seek-door``).
- ``unseen-descent-0845``: n1-a life-508 (Lv38, Mountain 43F) C:/hengband-backups/pdca/captures/
  n1a-508-1111/20261111-084537-loop-detected: every board and the decision rows, with the
  remembered terrain of its incident twin incident-captures/20261111-084536-loop-detected/
  policy-state.json.

Each fixture holds its rows, the decision rows (turn, sequence, key, reason, position, messages)
and the monster knowledge (lib/edit/MonraceDefinitions.jsonc) of every race on the boards.

    python tests/extract_n1a_508_1111_fixtures.py
"""
import gzip
import json
from dataclasses import asdict
from pathlib import Path

from extract_n1c_183_stairs_explore_loop_1109_fixtures import GAME, TERRAIN, lines
from hengbot.monrace_knowledge import load_monrace_knowledge

CAPTURES = Path("C:/hengband-backups/pdca/captures")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-508-1111"
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position", "messages")
EMPTY_WAND = CAPTURES / "stops-1110/n1-a/life-507/captures/20261110-185704-loop-detected"
SEARCH_12F = CAPTURES / "stops-1110/n1-a/life-507/captures/20261110-185212-stall-floor-dwell-search"
SEARCH = CAPTURES / "n1a-508-1111/20261111-082454-stall-floor-dwell-search"
DESCENT = CAPTURES / "n1a-508-1111/20261111-084537-loop-detected"
DESCENT_STATE = (CAPTURES / "n1a-508-1111/incident-captures/20261111-084536-loop-detected"
                 / "policy-state.json")
EMPTY_WAND_BOARDS = 4  # the last boards: E j answered 「もう魔力が残っていない」 on each


def write(name, rows, decisions, races, terrain=None):
    turns = {row["turn"] for row in rows}
    ids = {monster["race_id"] for row in rows
           for field in ("visible_monsters", "detected_monsters") for monster in row.get(field, [])}
    fixture = {
        "rows": rows,
        "decisions": [{field: row.get(field) for field in DECISION_FIELDS}
                      for row in decisions if row.get("turn") in turns],
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    if terrain is not None:
        fixture["terrain"] = terrain
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(json.dumps(fixture, ensure_ascii=False, default=sorted,
                                       separators=(",", ":")).encode("utf-8"), mtime=0)
    (OUTPUT / f"{name}.json.gz").write_bytes(payload)
    print(name, len(rows), len(fixture["decisions"]), len(payload))


def boards(capture: Path) -> list:
    return [row for row in lines(capture / "state.jsonl.gz") if row.get("type") == "player_turn"]


def main() -> None:
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    write("empty-wand-1857", boards(EMPTY_WAND)[-EMPTY_WAND_BOARDS:],
          lines(EMPTY_WAND / "bot-decisions.jsonl.gz"), races)
    write("search-12f-1852", boards(SEARCH_12F), lines(SEARCH_12F / "bot-decisions.jsonl.gz"), races)
    write("search-44f-0824", boards(SEARCH), lines(SEARCH / "bot-decisions.jsonl.gz"), races)
    state = json.loads(DESCENT_STATE.read_text(encoding="utf-8"))
    write("unseen-descent-0845", boards(DESCENT), lines(DESCENT / "bot-decisions.jsonl.gz"), races,
          {name: state["terrain"][name] for name in TERRAIN})


if __name__ == "__main__":
    main()
