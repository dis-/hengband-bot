"""Extract tests/fixtures/n1a-545-shop-uncomposable-1127/ (tests/test_n1a_545_shop_uncomposable_1127_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL34, Sorcery, gold 1571 at the stop), the incident capture
``incident-captures/20261127-125505-town-blocked-stage-deadline-buy`` copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1a-545-shop-uncomposable-1127/:

  town-arrival/           88 rows (arrival turn 4682890, decision sequence 24038 on): rows 25-33
                          bought iron shots, a Cure Critical Wounds potion and six Hard Biscuits,
                          row 34 ate, row 35 walked to the Magic shop to sell the 15-charge
                          Identify staff, row 36 observed its page and left, and rows 37-86
                          re-entered and left it 17 times until row 87 stopped under
                          town:blocked:stage-deadline:buy

Kept: the first 42 journal rows (two of the re-entries; the replay of the CLI's owner retirement
diverges at row 41), the loadout report left out as the other town-arrival fixtures.

    python tests/extract_n1a_545_shop_uncomposable_1127_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-shop-uncomposable-1127/incident-captures/"
            "20261127-125505-town-blocked-stage-deadline-buy")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-shop-uncomposable-1127"
ROWS = 42


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
