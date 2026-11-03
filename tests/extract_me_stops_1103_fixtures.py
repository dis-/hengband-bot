"""Extract tests/fixtures/me-stops-1103/ for test_me_stops_1103_recorded.

Source: C:/hengband-backups/pdca/captures/stops-1103-night/n1-c/ (builds
bot-e9e2c1262 / bot-91357d2d0).  Each case keeps a capture's town-arrival
checkpoint (policy.pkl), the character calibration beside it and the journal
rows up to the stop's decision, recompressed with xz.

    python tests/extract_me_stops_1103_fixtures.py <captures/stops-1103-night/n1-c>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures") / "me-stops-1103"
# Case name -> (life, incident capture, journal rows kept).
CASES = {
    "shovel-deposit": ("life-121", "20261103-211529-quest-blocked-me-staff", 67),
    "stuck-browse": ("life-122", "20261103-212306-stuck-prompt", 25),
    "staple-hold": ("life-120", "20261103-210824-town-blocked-survival-depth_abilities", 1),
    "sparrow-travel": ("life-122", "20261103-213134-quest-blocked-me-staff", 152),
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
