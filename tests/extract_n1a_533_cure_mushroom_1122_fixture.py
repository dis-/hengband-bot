"""Extract tests/fixtures/n1a-533-cure-mushroom-1122/ (n1-a life-533's death on Orc Cave 19F).

Source: n1-a life-533 (Warrior Lv22, build 53f7a340e), copied read-only from the viewing server to
C:/hengband-backups/pdca/n1a-532-533/life-533/:

 - ``incident-captures/20261122-151509-player-death/town-arrival/`` -- the town-arrival checkpoint
   of 15:13:47 (turn 435628, ``policy.pkl``), the visit's 53 journal rows (to the Recall wait) and
   the sidecar files (tests/support/town_arrival_fixture.extract; the loadout report left out);
 - ``captures/20261122-151510-exit-no-marker/`` -- state.jsonl.gz's player-turn boards of Orc Cave
   19F from turn 443605 (the capture's first, blind and confused, no curing potion left) to 443865
   (the first emergency:blind-strike), and bot-decisions.jsonl.gz's rows of those turns, kept as
   ``floor.json.xz``.

    python tests/extract_n1a_533_cure_mushroom_1122_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

ROOT = Path("C:/hengband-backups/pdca/n1a-532-533/life-533")
VISIT = ROOT / "incident-captures" / "20261122-151509-player-death" / "town-arrival"
CAPTURE = ROOT / "captures" / "20261122-151510-exit-no-marker"
TARGET = Path(__file__).with_name("fixtures") / "n1a-533-cure-mushroom-1122"
ROWS = 53
FIRST, LAST = 443605, 443865


def _rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    boards = [row for row in _rows(CAPTURE / "state.jsonl.gz")
              if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST]
    turns = {row["turn"] for row in boards}
    decisions = [{"decision_sequence": row["decision_sequence"], "turn": row["turn"],
                  "key": row["key"], "reason": row["reason"]}
                 for row in _rows(CAPTURE / "bot-decisions.jsonl.gz")
                 if "reason" in row and row.get("turn") in turns]
    assert len(boards) == len(decisions), (len(boards), len(decisions))
    (TARGET / "floor.json.xz").write_bytes(lzma.compress(json.dumps(
        {"boards": boards, "decisions": decisions}, ensure_ascii=False).encode(
            "utf-8", "surrogateescape"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
