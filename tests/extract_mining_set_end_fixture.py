"""Extract tests/fixtures/mining-set-end-20261103/.

Source: n1-c life-118, 2026-11-03 14:34:10
town:blocked:survival:cure_critical_ready (build bot-e99eaacc8).  The
capture's town-arrival checkpoint (policy.pkl) and visit journal (3 rows),
recompressed with xz.

    python tests/extract_mining_set_end_fixture.py <incident-capture-dir>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "mining-set-end-20261103"


def main() -> None:
    visit = Path(sys.argv[1]) / "town-arrival"
    FIXTURE.mkdir(exist_ok=True)
    preset = 9 | lzma.PRESET_EXTREME
    (FIXTURE / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    (FIXTURE / "journal.jsonl.xz").write_bytes(
        lzma.compress(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()), preset=preset))


if __name__ == "__main__":
    main()
