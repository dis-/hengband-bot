"""Extract tests/fixtures/n1c-217-store-full-all-sales-1119/.

Source: n1-c life-217's stop of 2026-11-19 17:16:29 (town:blocked:stage-deadline:sell, bot main
4c9fb4bdc6), its town-arrival directory 20261119-171621.681282472-turn4835668 (the live
capture's copy, read-only): the arrival checkpoint (policy.pkl, a Linux pickle), all 23 journal
rows (row 22 the stop) and the sidecar files the restored policy reads, xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1c_217_store_full_all_sales_1119_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-store-full-all-sales-1119"
ROWS = 23


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
