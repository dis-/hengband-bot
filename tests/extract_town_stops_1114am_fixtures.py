"""Extract the fixtures of the 2026-11-14 morning town stops.

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/town-stops-1114am: an incident capture's
``town-arrival`` directory (policy.pkl, journal.jsonl.gz and, with ``--calibration``,
sidecars/_character_calibration_path), recompressed with xz into
tests/fixtures/town-stops-1114am/<name>/:

  digger-rearm-207   n1-c life-207 20261114-062940-town-blocked-survival-combat_weapon_ready
                     (no calibration: the live process had none, partial-stat-table)
  filed-take-522     n1-a life-522 20261114-063149-town-blocked-owner-retired-burst-after-
                     town-blocked-repetition, --calibration --rows=56
  renamed-sale-395   n1-b life-395 20261114-063747-town-blocked-owner-retired-burst, --rows=85

    python tests/extract_town_stops_1114am_fixtures.py <town-arrival directory> <name> [--calibration] [--rows=N]
"""
import lzma
import sys
from pathlib import Path

from extract_viewing_stops_1113_fixtures import PRESET, _journal

FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1114am"


def arrival(source: Path, name: str, calibration: bool, rows: int | None) -> None:
    target = FIXTURES / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "policy.pkl.xz").write_bytes(
        lzma.compress((source / "policy.pkl").read_bytes(), preset=PRESET))
    (target / "journal.jsonl.xz").write_bytes(
        lzma.compress(_journal(source, rows), preset=PRESET))
    if calibration:
        (target / "calibration.json").write_bytes(
            (source / "sidecars" / "_character_calibration_path").read_bytes())


if __name__ == "__main__":
    options = sys.argv[3:]
    rows = next((int(option.split("=", 1)[1]) for option in options
                 if option.startswith("--rows=")), None)
    arrival(Path(sys.argv[1]), sys.argv[2], "--calibration" in options, rows)
