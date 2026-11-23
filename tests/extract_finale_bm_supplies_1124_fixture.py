"""Extract tests/fixtures/n1c-221-finale-bm-supplies-1124/ (tests/test_finale_bm_supplies_1124_recorded.py).

Source: n1-c life-221 (Magic-Eater Lv50, Angband's recall depth 96F or deeper, preparing the
99F/100F finale), a read-only copy in C:/hengband-backups/pdca/captures/finale-bm-supplies-1124/
of the life's ``jsonlog/town-arrival/``:

  town-arrival/20261124-030117.979460365-turn5552811/
                          the town-arrival checkpoint of 03:01:17 (decision 16943): the visit's
                          sales and purchases (rows 0-83), then from row 84 the town stopped
                          under ``town:blocked:finale-not-in-town:healing`` (2 of the 30 Potions
                          of Healing owned) and spun on key '5' until the loop detector halted
                          the driver at 03:02:17

Kept: the checkpoint's journal rows up to the third spin (the loadout report left out, as the
other town-arrival fixtures).

    python tests/extract_finale_bm_supplies_1124_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/finale-bm-supplies-1124/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-finale-bm-supplies-1124"
ROWS = 88


def main():
    extract(ROOT / "20261124-030117.979460365-turn5552811", FIXTURE, ROWS,
            frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
