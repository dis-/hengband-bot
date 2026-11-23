"""Extract tests/fixtures/n1a-535-teleport-ready-1123/.

Source: n1-a life-535's town:blocked:survival:teleport_ready stop of 2026-11-23 13:12:41
(Warrior Lv48, turn 7391125, main 57a80bc0a), copied read-only from the viewing server's
incident-captures/20261123-131241-town-blocked-survival-teleport_ready/ to the worktree's
untracked .cap535/inc/ (its town-arrival checkpoint of 13:12:22, turn 7389552).

The fixture keeps the checkpoint (``policy.pkl``), the visit's first 25 journal rows (up to the
Alchemist's re-entry page of decision 9604 and the Home board after it) and the sidecar files
(tests/support/town_arrival_fixture.extract).

    python tests/extract_n1a_535_teleport_ready_1123_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path(__file__).resolve().parents[1] / ".cap535" / "inc" / "town-arrival"
TARGET = Path(__file__).with_name("fixtures") / "n1a-535-teleport-ready-1123"
ROWS = 25


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
