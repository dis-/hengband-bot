"""Extract tests/fixtures/town-stops-1103/<stop>/.

Source: stops-1103-night captures of build bot-91357d2d0 (n1-b life-306 and
n1-a life-474).  Each capture's town-arrival checkpoint (policy.pkl) and visit
journal, recompressed with xz.

    python tests/extract_town_stops_1103_fixture.py <stop-name> <incident-capture-dir>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1103"


def main() -> None:
    target = FIXTURES / sys.argv[1]
    visit = Path(sys.argv[2]) / "town-arrival"
    target.mkdir(parents=True, exist_ok=True)
    preset = 9 | lzma.PRESET_EXTREME
    (target / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    (target / "journal.jsonl.xz").write_bytes(
        lzma.compress(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()), preset=preset))


if __name__ == "__main__":
    main()
