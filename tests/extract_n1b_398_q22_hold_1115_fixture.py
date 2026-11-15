"""Extract tests/fixtures/n1b-398-q22-hold-1115/.

Source: n1-b life-398's death (2026-11-15 11:26, Q22 Orc Camp, build 3b52c43f0),
copied read-only from the viewing server to C:/hengband-backups/pdca/n1b-398-399-1115/:

* the incident capture 20261115-112601-player-death's town-arrival checkpoint (the
  Angwil visit that took the quest; 89 journal rows, the last the quest entrance);
* the stop capture 20261115-112604-exit-no-marker's decision log and board log
  (state.jsonl.gz): every quest-floor decision up to ``LAST_TURN`` with the first
  quest-floor board of its turn, and the later landing board ``LANDING_TURN``.
  Grid maps are stored once and referenced by digest.

    PYTHONPATH="src;tests" python tests/extract_n1b_398_q22_hold_1115_fixture.py
"""
import gzip
import hashlib
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SOURCE = Path("C:/hengband-backups/pdca/n1b-398-399-1115")
VISIT = SOURCE / "life-398/incident-captures/20261115-112601-player-death/town-arrival"
STOP = SOURCE / "20261115-112604-exit-no-marker"
TARGET = Path(__file__).with_name("fixtures") / "n1b-398-q22-hold-1115"
ROWS = 89
QUEST = 22
LAST_TURN = 879190  # the first board after the first emergency teleport
LANDING_TURN = 879618  # a later emergency landing at (9,53)


def _rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    boards = [board for board in _rows(STOP / "state.jsonl.gz")
              if (board.get("floor") or {}).get("quest_id") == QUEST]
    first = {}
    for board in boards:
        first.setdefault(board["turn"], board)
    decisions = [
        {key: row[key] for key in ("decision_sequence", "turn", "key", "reason")}
        | {"position": [row["position"]["y"], row["position"]["x"]]}
        for row in _rows(STOP / "bot-decisions.jsonl.gz")
        if (row.get("floor") or {}).get("quest_id") == QUEST and row["turn"] <= LAST_TURN
    ]
    grid_maps = {}

    def stored(board):
        board = json.loads(json.dumps(board))
        text = json.dumps(board["grid_map"], sort_keys=True)
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        grid_maps.setdefault(digest, board["grid_map"])
        board["grid_map"] = digest
        return board

    payload = {
        "decisions": decisions,
        "boards": [stored(first[row["turn"]]) for row in decisions],
        "landing": stored(first[LANDING_TURN]),
        "grid_maps": grid_maps,
    }
    (TARGET / "quest-boards.json.xz").write_bytes(lzma.compress(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()),
          len(decisions), len(grid_maps))


if __name__ == "__main__":
    main()
