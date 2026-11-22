"""Extract tests/fixtures/n1a-535-identify-staff-buy-1122/.

n1-a life-535 (Lv25 warrior, build bot-8e57c07f2) stopped in town on 2026-11-22 16:44:10 with
``town:blocked:stage-deadline:buy``: the planner walked to the Magic shop for the Identify staff
(15 of 20 charges) and the shop page's selector saw nothing wanted, 17 times.

Source: the stop's incident capture (incident-captures/20261122-164409-town-blocked-stage-
deadline-buy/town-arrival, the arrival at turn 724290), copied read-only from the viewing server
to C:/hengband-backups/pdca/n1a-535-buy/.  The fixture keeps the arrival policy, the sidecars and
the journal's rows 0-29: the visit up to the first Magic shop page after the fundraising set
opened (row 29, recorded ``shop:observe-and-leave``).

    python tests/extract_n1a_535_identify_staff_buy_1122_fixture.py
    (PYTHONPATH: src, tests and the root)
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1a-535-buy/20261122-164409-town-blocked-stage-deadline-buy/"
             "town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1a-535-identify-staff-buy-1122"
ROWS = 30


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    print(TARGET, sum(path.stat().st_size for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
