"""Extract tests/fixtures/depth-cumulative-1104/ for test_depth_cumulative_recorded.

Source: C:/hengband-backups/pdca/captures/stops-1104-morning/n1-a/life-475/
incident-captures/20261104-022543-player-death/town-arrival: the arrival
checkpoint, the character calibration beside it and the journal rows up to row 12,
the visit's recall to the alternate dungeon's 49F, recompressed with xz.

    python tests/extract_depth_cumulative_1104_fixture.py <town-arrival visit directory>
"""
import gzip
import lzma
import sys
from pathlib import Path

TARGET = Path(__file__).with_name("fixtures") / "depth-cumulative-1104"
ROWS_KEPT = 13
CALIBRATION = "_character_calibration_path"


def main() -> None:
    visit = Path(sys.argv[1])
    preset = 9 | lzma.PRESET_EXTREME
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes())
    kept = b"".join(journal.splitlines(keepends=True)[:ROWS_KEPT])
    (TARGET / "journal.jsonl.xz").write_bytes(lzma.compress(kept, preset=preset))
    (TARGET / "calibration.json").write_bytes((visit / "sidecars" / CALIBRATION).read_bytes())


if __name__ == "__main__":
    main()
