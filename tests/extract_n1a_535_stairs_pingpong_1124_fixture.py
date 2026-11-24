"""Extract tests/fixtures/n1a-535-stairs-pingpong-1124/.

Source: n1-a life-535's loop-detected incident of 2026-11-24 09:39:24 (Warrior Lv50, Castle 42F,
build b1e6a70ca), copied read-only from the viewing server's
incident-captures/20261124-093923-loop-detected/ (its town-arrival checkpoint of 09:36:00,
turn 10156592) and captures/20261124-093926-loop-detected/state.jsonl.gz to
C:/hengband-backups/pdca/n1a-535-loop-1124/{incident,capture}/.

The fixture keeps the checkpoint (``policy.pkl``), the visit's 139 journal rows (the town visit
up to the Recall wait) and the sidecar files (tests/support/town_arrival_fixture.extract), and
``boards.jsonl.xz``: lines 24-30 of the capture's state.jsonl, the 42F up stair (18,37) at turn
10163895 to the first return to it at turn 10163903 (via 40F's down stair (6,125)).

    python tests/extract_n1a_535_stairs_pingpong_1124_fixture.py
"""
import gzip
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SOURCE = Path("C:/hengband-backups/pdca/n1a-535-loop-1124")
VISIT = SOURCE / "incident" / "town-arrival"
STATES = SOURCE / "capture" / "state.jsonl.gz"
TARGET = Path(__file__).with_name("fixtures") / "n1a-535-stairs-pingpong-1124"
ROWS = 139
BOARDS = slice(24, 31)


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    lines = gzip.decompress(STATES.read_bytes()).decode("utf-8").splitlines()
    (TARGET / "boards.jsonl.xz").write_bytes(
        lzma.compress(("\n".join(lines[BOARDS]) + "\n").encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
