"""Extract tests/fixtures/town-stops-1104/ for test_town_stops_1104_recorded.

Source: C:/hengband-backups/pdca/captures/stops-1104-morning (builds
bot-2d4b7645d / bot-b044fd30f).  Each case keeps a capture's town-arrival
checkpoint (policy.pkl), the character calibration beside it and the journal
rows up to the stop's decision, recompressed with xz.

    python tests/extract_town_stops_1104_fixtures.py <captures/stops-1104-morning>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1104"
# Case name -> (instance/life, incident capture, journal rows kept).
CASES = {
    "merged-take": ("n1-a/life-475", "20261104-015340-town-blocked-survival-identify_staff_ready", 16),
    "stale-requests": ("n1-a/life-476", "20261104-025103-town-blocked-survival-identify_staff_ready", 2),
    "reserved-ring": ("n1-a/life-476", "20261104-023028-town-blocked-shop-required-operation-uncomposable", 9),
    "identification-wait": ("n1-a/life-476", "20261104-043627-departure-unsatisfiable", 20),
    "kit-latch": ("n1-b/life-306", "20261104-003239-town-blocked-owner-retired-burst", 28),
    "gold-pile": ("n1-c/life-123", "20261104-043315-town-blocked-owner-retired-burst", 51),
    "pack-identify": ("n1-a/life-476", "20261104-030834-town-blocked-survival-recall_departure_ready", 45),
}
CALIBRATION = "_character_calibration_path"


def main() -> None:
    root = Path(sys.argv[1])
    preset = 9 | lzma.PRESET_EXTREME
    for name, (life, capture, rows) in CASES.items():
        visit = root / life / "incident-captures" / capture / "town-arrival"
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
