"""Extract tests/fixtures/n1c-207-wait-recall-1114/.

Source: n1-c life-207's town-arrival checkpoint of the visit that began
2026-11-14 05:50:38 (turn 5570551, build bot-3eef22a25, the process started
by that deploy), copied with the incident capture
20261114-055048-town-blocked-owner-retired-burst read-only from the viewing
server to C:/hengband-backups/pdca/captures/n1c-207-wait-recall-burst-1114/:
journal rows 0-34 (row 24 reads the recall, row 32 steps onto the Home
entrance under it, rows 33-34 leave the page and await its entry again).

    PYTHONPATH="src;tests" python tests/extract_n1c_207_wait_recall_1114_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/captures/n1c-207-wait-recall-burst-1114/incident-captures/"
             "20261114-055048-town-blocked-owner-retired-burst/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1c-207-wait-recall-1114"


if __name__ == "__main__":
    extract(VISIT, TARGET, 35, frozenset({"_loadout_report_path"}))
    print(sorted(path.name for path in TARGET.iterdir()))
