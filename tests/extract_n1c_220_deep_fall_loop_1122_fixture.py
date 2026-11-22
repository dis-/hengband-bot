"""Extract tests/fixtures/n1c-220-deep-fall-loop-1122/.

Source: n1-c life-220's loop-detected incident of 2026-11-22 10:24:25 (Magic-Eater Lv32,
Angband 49F, build 001f59bd3), copied read-only from the viewing server's
incident-captures/20261122-102425-loop-detected/ (its town-arrival checkpoint of 10:23:55,
turn 1825376) and captures/20261122-102427-loop-detected/state.jsonl.gz to
C:/hengband-backups/pdca/n1c-220-loop-1122/{incident,capture}/.

The fixture keeps the checkpoint (``policy.pkl``), the visit's 62 journal rows (the town visit
up to the Recall to Angband 48F) and the sidecar files (tests/support/town_arrival_fixture
.extract), and ``boards.jsonl.xz``: lines 36-48 of the capture's state.jsonl, the 48F down
stair (29,93) at turn 1826818 to the second 49F arrival at turn 1826849.

    python tests/extract_n1c_220_deep_fall_loop_1122_fixture.py
"""
import gzip
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SOURCE = Path("C:/hengband-backups/pdca/n1c-220-loop-1122")
VISIT = SOURCE / "incident" / "town-arrival"
STATES = SOURCE / "capture" / "state.jsonl.gz"
TARGET = Path(__file__).with_name("fixtures") / "n1c-220-deep-fall-loop-1122"
ROWS = 62
BOARDS = slice(36, 49)


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    lines = gzip.decompress(STATES.read_bytes()).decode("utf-8").splitlines()
    (TARGET / "boards.jsonl.xz").write_bytes(
        lzma.compress(("\n".join(lines[BOARDS]) + "\n").encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
