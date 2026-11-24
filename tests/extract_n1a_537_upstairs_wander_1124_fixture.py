"""Extract tests/fixtures/n1a-537-upstairs-wander-1124/.

Source: n1-a life-537's livelock-exhausted incident of 2026-11-24 21:03:11 (Warrior Lv8, Yeek
cave 3F), copied read-only from the viewing server's
incident-captures/20261124-210311-livelock-exhausted/ (its town-arrival checkpoint of 20:54:40,
turn 84161, and snapshots/snapshots-current.jsonl.gz) and the life's jsonlog/bot-decisions.jsonl
(turns 85900-126100) to C:/hengband-backups/pdca/n1a-537-upstairs-wander-1124/.

The fixture keeps the checkpoint (``policy.pkl``), the visit's 100 journal rows (the town visit
up to the stairs into Yeek cave 1F) and the sidecar files (tests/support/town_arrival_fixture),
``boards.jsonl.xz``: the snapshot lines of turns 85917-86600 (Yeek cave 1F, the trap door to 3F
at turn 86085, the walled-in rooms there), and ``decisions.jsonl.xz``: the recorded (turn, key,
reason) of the same turns.

    python tests/extract_n1a_537_upstairs_wander_1124_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SOURCE = Path("C:/hengband-backups/pdca/n1a-537-upstairs-wander-1124")
VISIT = SOURCE / "incident" / "town-arrival"
SNAPSHOTS = SOURCE / "incident" / "snapshots" / "snapshots-current.jsonl.gz"
DECISIONS = SOURCE / "decisions-85900-126100.jsonl"
TARGET = Path(__file__).with_name("fixtures") / "n1a-537-upstairs-wander-1124"
ROWS = 100
FIRST_TURN, LAST_TURN = 85917, 86600


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    boards = [line for line in gzip.decompress(SNAPSHOTS.read_bytes()).decode("utf-8").splitlines()
              if line.strip() and FIRST_TURN <= json.loads(line)["turn"] <= LAST_TURN]
    (TARGET / "boards.jsonl.xz").write_bytes(
        lzma.compress(("\n".join(boards) + "\n").encode("utf-8"), preset=PRESET))
    decisions = []
    for line in DECISIONS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if FIRST_TURN <= row["turn"] <= LAST_TURN:
            decisions.append(json.dumps(
                {name: row[name] for name in ("turn", "key", "reason")}, ensure_ascii=False))
    (TARGET / "decisions.jsonl.xz").write_bytes(
        lzma.compress(("\n".join(decisions) + "\n").encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
