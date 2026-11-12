"""Extract tests/fixtures/unused-light-1111/<case>/ for test_unused_light_home_1111_recorded.

Source: hengband.net ~/hengbot-soak/n1-b/life-370/jsonlog/town-arrival (2026-11-11):
two town arrivals of n1-b life-370 wearing ★知識の石 and carrying
★ガラドリエルの玻璃瓶 and ★火消しライター.  Each case keeps the arrival's policy
and the first ``ROWS`` decisions of its journal, with xz.

    python tests/extract_unused_light_1111_fixture.py <town-arrival directory>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures") / "unused-light-1111"
# case: (arrival directory, journal rows kept)
CASES = {
    # The visit that shelved three items at Home (row 3) and left with both lights.
    "visit-233016": ("20261111-233016.391126641-turn8341895", 4),
    # The next arrival, 42 seconds later: both lights still carried.
    "next-233058": ("20261111-233058.063606212-turn8344531", 1),
}


def main() -> None:
    root = Path(sys.argv[1])
    preset = 9 | lzma.PRESET_EXTREME
    for name, (arrival, rows) in CASES.items():
        visit = root / arrival
        target = FIXTURES / name
        target.mkdir(parents=True, exist_ok=True)
        (target / "policy.pkl.xz").write_bytes(
            lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
        lines = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
        (target / "journal.jsonl.xz").write_bytes(lzma.compress(b"".join(lines[:rows]), preset=preset))


if __name__ == "__main__":
    main()
