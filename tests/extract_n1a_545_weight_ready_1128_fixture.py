"""Extract tests/fixtures/n1a-545-weight-ready-1128/ (tests/test_n1a_545_weight_ready_1128_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL39, Sorcery), the incident capture
``incident-captures/20261128-050648-town-blocked-survival-inventory_weight_ready`` copied read-only
from the viewing server to C:/hengband-backups/pdca/captures/n1a-545-weight-ready-1128/:

  town-arrival/           16 rows (arrival turn 6841644, the resume on build bot-3d71cd43b): a Home
                          withdrawal (row 6), two purchases (rows 9 and 12), the town-end step-off
                          (row 14) and row 15 stopped under
                          town:blocked:survival:inventory_weight_ready

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_weight_ready_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-weight-ready-1128")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-weight-ready-1128"
ROWS = 16


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
