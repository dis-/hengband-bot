"""Extract tests/fixtures/n1a-536-home-weapon-loop-1124/.

Source: n1-a life-536's town:blocked:stage-deadline:home stop of 2026-11-24 19:15:31 (Warrior
Lv35, the mining fundraise "mine", two diggers in the hands), copied read-only from the viewing
server's incident-captures/20261124-191531-town-blocked-stage-deadline-home/town-arrival/ (the
checkpoint of 19:15:06, turn 2201664; the snapshots left out) to the worktree's untracked
.pdca-n1a-536/incident-captures/.

The fixture keeps the checkpoint (``policy.pkl``), the visit's first 37 journal rows (up to and
including the arrival's Home weight deposit, row 36) and the sidecar files
(tests/support/town_arrival_fixture.extract).

    python tests/extract_n1a_536_home_weapon_loop_1124_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

SOURCE = Path(__file__).resolve().parents[1] / ".pdca-n1a-536"
VISIT = next((SOURCE / "incident-captures").glob("20261124-191531-*")) / "town-arrival"
TARGET = Path(__file__).with_name("fixtures") / "n1a-536-home-weapon-loop-1124"
ROWS = 37


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
