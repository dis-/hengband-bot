"""Extract tests/fixtures/spare-gear-1104/ for test_spare_gear_recorded.

Source: C:/hengband-backups/pdca/captures/carry-gear-1104/ (build bot-28e3790a6,
2026-11-04).  Each case keeps a town-arrival checkpoint (policy.pkl), the
character calibration beside it and the journal rows named here, with xz.

    python tests/extract_spare_gear_fixtures.py <captures/carry-gear-1104>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures") / "spare-gear-1104"
# Case name -> (life directory, arrival checkpoint, journal rows kept).
CASES = {
    # n1-c life-130: sheet rejected, four unworn items left town from here.
    "rejected-sheet": ("n1-c/life-130", "20261104-152713.007536043-turn1861337", 4),
    # n1-a life-479: a Shovel in the pack, another tool at Home, not mining.
    "carried-shovel": ("n1-a/life-479", "20261104-152443.977045578-turn2098353", 1),
}
CALIBRATION = "_character_calibration_path"


def main() -> None:
    root = Path(sys.argv[1])
    preset = 9 | lzma.PRESET_EXTREME
    for name, (life, arrival, rows) in CASES.items():
        visit = root / life / "jsonlog" / "town-arrival" / arrival
        target = FIXTURES / name
        target.mkdir(parents=True, exist_ok=True)
        (target / "policy.pkl.xz").write_bytes(
            lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
        journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes())
        kept = b"".join(journal.splitlines(keepends=True)[:rows])
        (target / "journal.jsonl.xz").write_bytes(lzma.compress(kept, preset=preset))
        (target / "calibration.json").write_bytes((visit / "sidecars" / CALIBRATION).read_bytes())


if __name__ == "__main__":
    main()
