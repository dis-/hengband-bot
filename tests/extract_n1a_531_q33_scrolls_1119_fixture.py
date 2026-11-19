"""Extract tests/fixtures/n1a-531-q33-scrolls-1119/.

Source: n1-a life-531's stop of 2026-11-19 16:05:49
(town:blocked:survival:inventory_weight_ready), the capture's town-arrival checkpoint
20261119-160427.784519955-turn6177515/ (policy.pkl, turn 6177515): all 178 journal rows (row 177
the stop) and the sidecar files the restored policy reads, xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_531_q33_scrolls_1119_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-q33-scrolls-1119"
ROWS = 178


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
