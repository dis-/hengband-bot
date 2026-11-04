"""Extract tests/fixtures/spare-gear-1104/home-full-stop/ for test_home_full_gear_recorded.

Source: the incident capture of n1-c life-130, 2026-11-04 20:40:46
(C:/hengband-backups/pdca/captures/home-full-1104, stop
town:blocked:overweight-home-full-no-legal-relief).  Keeps the town-arrival
checkpoint, its whole journal and the character calibration, with xz.

    python tests/extract_home_full_gear_fixture.py <incident-capture-dir>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "spare-gear-1104" / "home-full-stop"


def main() -> None:
    visit = Path(sys.argv[1]) / "town-arrival"
    preset = 9 | lzma.PRESET_EXTREME
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    (FIXTURE / "journal.jsonl.xz").write_bytes(
        lzma.compress(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()), preset=preset))
    (FIXTURE / "calibration.json").write_bytes(
        (visit / "sidecars" / "_character_calibration_path").read_bytes())


if __name__ == "__main__":
    main()
