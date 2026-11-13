"""Extract the fixtures of the 2026-11-13 morning viewing stops.

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/viewing-stops-1113am:

 - ``arrival`` -- an incident capture's ``town-arrival`` directory (policy.pkl,
   journal.jsonl.gz, sidecars/_character_calibration_path), recompressed with xz into
   tests/fixtures/viewing-stops-1113/<name>/:
     opening-385  n1-b life-385 20261113-084413-quest-blocked-opening-route
     opening-387  n1-b life-387 20261113-123022-quest-blocked-opening-route

    python tests/extract_viewing_stops_1113_fixtures.py arrival <town-arrival directory> <name>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures") / "viewing-stops-1113"
PRESET = 9 | lzma.PRESET_EXTREME


def arrival(source: Path, name: str) -> None:
    target = FIXTURES / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "policy.pkl.xz").write_bytes(
        lzma.compress((source / "policy.pkl").read_bytes(), preset=PRESET))
    (target / "journal.jsonl.xz").write_bytes(
        lzma.compress(gzip.decompress((source / "journal.jsonl.gz").read_bytes()), preset=PRESET))
    (target / "calibration.json").write_bytes(
        (source / "sidecars" / "_character_calibration_path").read_bytes())


def main() -> None:
    kind = sys.argv[1]
    if kind == "arrival":
        arrival(Path(sys.argv[2]), sys.argv[3])
    else:
        raise SystemExit(f"unknown kind {kind}")


if __name__ == "__main__":
    main()
