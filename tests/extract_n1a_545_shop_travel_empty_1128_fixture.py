"""Extract tests/fixtures/n1a-545-shop-travel-empty-1128/ (tests/test_n1a_545_shop_travel_empty_1128_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL38, Sorcery), the incident capture
``incident-captures/20261128-084317-no-key-exhausted`` copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1a-545-shop-travel-empty-1128/:

  town-arrival/           200 rows (arrival turn 7149782, build bot-b3b1efe59): row 197 stepped
                          off the entrance at the town end, row 198 travelled to the General
                          Store to shed 3 reserved Hard Biscuits for the weight, and row 199
                          decided the empty key (no-key-exhausted)

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_shop_travel_empty_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-shop-travel-empty-1128")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-shop-travel-empty-1128"
ROWS = 200


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
