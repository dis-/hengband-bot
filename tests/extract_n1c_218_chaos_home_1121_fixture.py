"""Extract tests/fixtures/n1c-218-chaos-home-1121/ for test_n1c_218_chaos_home_1121_recorded.

Source: the town-arrival checkpoint copied to
C:/hengband-backups/pdca/captures/n1c-218-20261121-chaos-home/n1c218-ta.tgz: n1-c life-218
2026-11-21 21:00:41 (turn 2945098, decision 20791), 37 journal rows; the loadout report is left
out (the optimizer appends to its own).

    python tests/extract_n1c_218_chaos_home_1121_fixture.py <town-arrival/20261121-210041.672274447-turn2945098>
"""
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tests  # noqa: F401,E402 -- isolate live runtime files
from support.town_arrival_fixture import extract  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-218-chaos-home-1121"


def main() -> None:
    visit = Path(sys.argv[1])
    rows = len(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines())
    extract(visit, FIXTURE, rows, frozenset({"_loadout_report_path"}))


if __name__ == "__main__":
    main()
