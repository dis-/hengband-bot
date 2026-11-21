"""Extract tests/fixtures/n1b-413-launcher-1121/ for test_n1b_413_launcher_1121_recorded.

Source: the town-arrival checkpoint copied to
C:/hengband-backups/pdca/captures/n1b-413-launcher/n1b413-ta.tgz: n1-b life-413 2026-11-21
23:12:21 (turn 1758715, decision 68135), 13 journal rows; the loadout report is left out.

    python tests/extract_n1b_413_launcher_1121_fixture.py <town-arrival/20261121-231221.061169000-turn1758715>
"""
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import extract  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-launcher-1121"


def main() -> None:
    visit = Path(sys.argv[1])
    rows = len(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines())
    extract(visit, FIXTURE, rows, frozenset({"_loadout_report_path"}))


if __name__ == "__main__":
    main()
