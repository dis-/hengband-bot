"""Extract tests/fixtures/n1b-416-finale-bm-entry-1124/ (tests/test_finale_bm_entry_1124_recorded.py).

Source: n1-b life-416 (Magic-Eater, Oberon killed on 99F at 2026-11-24 02:20, then a Scroll of
Reset Recall read in town at 02:21:00 set Angband's recall depth to 95), a read-only copy in
C:/hengband-backups/pdca/captures/finale-bm-entry-1124/ of the life's
``jsonlog/town-arrival/``:

  town-arrival/20261124-024234.119152272-turn4601311/
                          the town-arrival checkpoint of the return from 95F at 02:42:34
                          (decision 19275): 76 of the 84 Restore Mana owned and every other
                          finale supply owned once the Teleportation was bought (rows 13-14);
                          the ordinary Black Market tour (bm_tour) lapped once and row 82 read
                          the Word of Recall to Angband 95F (``town:recall-to-angband``)

Kept: the checkpoint's journal rows up to the recall's countdown (the loadout report left out, as
the other town-arrival fixtures).

    python tests/extract_finale_bm_entry_1124_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/finale-bm-entry-1124/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-finale-bm-entry-1124"
ROWS = 84


def main():
    extract(ROOT / "20261124-024234.119152272-turn4601311", FIXTURE, ROWS,
            frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
