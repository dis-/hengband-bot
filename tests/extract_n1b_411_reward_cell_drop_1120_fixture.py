"""Extract tests/fixtures/n1b-411-reward-cell-drop-1120/.

Source: n1-b life-411's stop of 2026-11-20 06:35:49 (town:blocked:stage-deadline:quest, bot main
d6b6f0251e), its town-arrival directory 20261120-063452.520186658-turn9939091 (the live capture's
copy, read-only): the arrival checkpoint (policy.pkl, a Linux pickle), all 270 journal rows (row
269 the stop) and the sidecar files the restored policy reads, xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1b_411_reward_cell_drop_1120_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-reward-cell-drop-1120"
ROWS = 270


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
