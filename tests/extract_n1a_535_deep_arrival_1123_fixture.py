"""Extract tests/fixtures/n1a-535-deep-arrival-1123/.

Source: n1-a life-535's dungeon:blocked:deep-arrival-without-destruction stop of 2026-11-23
00:59:50 (Warrior Lv40, the Castle's 48F trap door onto 50F, build 29a7c9be3), copied read-only
from the viewing server's incident-captures/20261123-005950-dungeon-blocked-deep-arrival-without-
destruction/ (its town-arrival checkpoint of 00:58:36, turn 5119089; the snapshots left out) and
captures/20261123-005954-dungeon-blocked-deep-arrival-without-destruction/state.jsonl.gz to the
worktree's untracked .pdca-n1a-535/{incident-captures,captures}/.

The fixture keeps the checkpoint (``policy.pkl``), the visit's 148 journal rows (the town visit
up to the Recall to the Castle's 48F, waited for) and the sidecar files (tests/support/
town_arrival_fixture.extract), and ``boards.jsonl.xz``: the capture's state.jsonl lines of the
48F walk east, from (38,136) at turn 5123328 to the 50F arrival board at turn 5123386.

    python tests/extract_n1a_535_deep_arrival_1123_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SOURCE = Path(__file__).resolve().parents[1] / ".pdca-n1a-535"
VISIT = next((SOURCE / "incident-captures").glob("20261123-005950-*")) / "town-arrival"
STATES = next((SOURCE / "captures").glob("20261123-005954-*")) / "state.jsonl.gz"
TARGET = Path(__file__).with_name("fixtures") / "n1a-535-deep-arrival-1123"
ROWS = 148
FIRST_TURN, LAST_TURN = 5123328, 5123386


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    lines = gzip.decompress(STATES.read_bytes()).decode("utf-8").splitlines()
    kept = [line for line in lines if FIRST_TURN <= json.loads(line)["turn"] <= LAST_TURN]
    (TARGET / "boards.jsonl.xz").write_bytes(
        lzma.compress(("\n".join(kept) + "\n").encode("utf-8"), preset=PRESET))
    print(len(kept), sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
