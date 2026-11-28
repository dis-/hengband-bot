"""Extract tests/fixtures/n1b-420-klackon-start-1128/ (tests/test_n1b_420_klackon_start_1128_recorded.py).

Source: n1-b life-420 (Klackon Magic-Eater Lv1, the first Klackon and the first ordinary eater of
the n1-b instance), the incident capture
``incident-captures/20261128-083131-town-blocked-unmet-food_ready`` copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1b-420-klackon-start-1128/life-420/:

  town-arrival/           26 rows (arrival turn 1, the new character's first board): row 13 bought
                          16 torches at the General Store, row 18 3 Treasure Detection at the
                          Alchemist, row 24 stepped off the Temple entrance
                          (fundraise:departure-blocked-step-off) and row 25 stopped under
                          town:blocked:unmet:food_ready with 34 gold

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1b_420_klackon_start_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-420-klackon-start-1128/life-420/incident-captures/"
            "20261128-083131-town-blocked-unmet-food_ready")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-420-klackon-start-1128"
ROWS = 26


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
