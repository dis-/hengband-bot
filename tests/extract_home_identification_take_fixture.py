"""Extract tests/fixtures/home-identification-take-20261103/.

Source: n1-a life-472, 2026-11-03 12:05 town:blocked:unmet:home_candidate_resolved
(build bot-00d3a3726).  The capture's town-arrival checkpoint (policy.pkl)
and visit journal, recompressed with xz; the replay replays all 145 rows.

    python tests/extract_home_identification_take_fixture.py <incident-capture-dir>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "home-identification-take-20261103"


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
