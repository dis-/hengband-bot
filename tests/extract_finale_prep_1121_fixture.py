"""Extract tests/fixtures/n1b-finale-prep-1121/ and n1c-finale-prep-1121/ for
test_finale_prep_1121_recorded.

Source: the town-arrival checkpoints copied to C:/hengband-backups/pdca/captures/finale-prep-phase-1121/:
n1-b life-411 2026-11-21 05:50:19 (turn 11279683, the checkpoint after the arrival's first decision,
267 journal rows) and n1-c life-217 05:55:10 (turn 7273502, 143 rows).

    python tests/extract_finale_prep_1121_fixture.py <C:/hengband-backups/pdca/captures/finale-prep-phase-1121>
"""
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import extract  # noqa: E402

FIXTURES = Path(__file__).with_name("fixtures")
VISITS = (("n1-b", "20261121-055019.992594560-turn11279683", "n1b-finale-prep-1121"),
          ("n1-c", "20261121-055510.739723826-turn7273502", "n1c-finale-prep-1121"))


def main() -> None:
    root = Path(sys.argv[1])
    for who, name, fixture in VISITS:
        visit = root / who / name
        rows = len(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines())
        extract(visit, FIXTURES / fixture, rows)


if __name__ == "__main__":
    main()
