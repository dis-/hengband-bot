"""Extract tests/fixtures/q1-explored-recall-1118.jsonl.xz (tests/test_explored_floor_1118_recorded.py).

Source: the viewing server's snapshot logs (``jsonlog/snapshots/*.jsonl.gz``, one board a player
turn) and decision logs (``jsonlog/bot-decisions.jsonl*``), cut read-only on 2026-11-18 to
C:/hengband-backups/pdca/captures/q1-explored-recall-1118:

  n1c-0256.jsonl.gz              n1-c life-216, dungeon 14 50F (its last floor): the visit from its
                                 first board (turn 6204711) to the Word of Recall read at 02:56:01
                                 (turn 6204776, explored-dead-end-floor)
  n1b-0347.jsonl.gz              n1-b life-411, Angband 80F: the visit from its first board (turn
                                 6470581) to the read at 03:47:07 (turn 6471499)
  n1c-glass-visit.jsonl.gz       n1-c life-216, Glass castle (dungeon 20) 60F: the visit from the
                                 bot's restart at 04:13:10 (turn 6294855, the game reloaded) on
  n1c-glass-decisions.jsonl      the live decisions of 03:53-04:24 (time, sequence, turn, reason,
                                 dungeon, level, known cells, marked cells, open frontiers, trigger)

Roles: ``n1c-0256`` and ``n1b-0347`` (the boards), ``glass`` (the Glass castle boards up to turn
6297323, the board the explore window measured on the known map stalls on), ``glass-explore``
(the turns of that stretch the live bot decided ``explore`` on).  xz: consecutive boards repeat
the floor, so the 550 Glass castle boards (73 MB of JSON) compress to well under 1 MB.

    python tests/extract_q1_explored_recall_1118_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/q1-explored-recall-1118")
TARGET = Path(__file__).with_name("fixtures") / "q1-explored-recall-1118.jsonl.xz"
WINDOWS = {
    "n1c-0256": ("n1c-0256.jsonl.gz", 6204711, 6204776),
    "n1b-0347": ("n1b-0347.jsonl.gz", 6470581, 6471499),
    "glass": ("n1c-glass-visit.jsonl.gz", 6294855, 6297323),
}


def _boards(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                board = json.loads(line)
                if board.get("type") == "player_turn":
                    yield board


def main() -> None:
    rows = []
    for role, (name, first, last) in WINDOWS.items():
        rows.extend({"role": role, "board": board} for board in _boards(ROOT / name)
                    if first <= board["turn"] <= last)
    decisions = [json.loads(line) for line in (ROOT / "n1c-glass-decisions.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    restart = next(index for index, row in enumerate(decisions) if row[1] is None)
    first, last = WINDOWS["glass"][1:]
    rows.append({"role": "glass-explore", "turns": sorted({
        row[2] for row in decisions[restart + 1:]
        if row[1] is not None and row[3] == "explore" and first <= row[2] <= last})})
    with lzma.open(TARGET, "wb", preset=9 | lzma.PRESET_EXTREME) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(TARGET, TARGET.stat().st_size, len(rows))


if __name__ == "__main__":
    main()
