"""Extract tests/fixtures/burst-1104/<stop>/.

Source: the owner-retired-burst captures of 2026-11-04 night, build bot-6120e77fd
(n1-a life-480 21:09, n1-c life-133 21:10 and 21:12).  Each capture's town-arrival
checkpoint and visit journal, recompressed with xz, and the character dump.

    python tests/extract_burst_1104_fixture.py <stop-name> <incident-capture-dir>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures") / "burst-1104"


def main() -> None:
    target = FIXTURES / sys.argv[1]
    visit = Path(sys.argv[2]) / "town-arrival"
    target.mkdir(parents=True, exist_ok=True)
    preset = 9 | lzma.PRESET_EXTREME
    (target / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    (target / "journal.jsonl.xz").write_bytes(
        lzma.compress(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()), preset=preset))
    (target / "character-dump.txt").write_bytes(
        (visit / "sidecars" / "_character_dump_path").read_bytes())


if __name__ == "__main__":
    main()
