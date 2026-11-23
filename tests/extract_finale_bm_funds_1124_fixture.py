"""Extract tests/fixtures/n1b-416-finale-bm-funds-1124/ (tests/test_finale_bm_funds_1124_recorded.py).

Source: n1-b life-416 (Magic-Eater, Angband recall depth 99), 2026-11-24, a read-only copy in
C:/hengband-backups/pdca/captures/finale-bm-funds-1124/ of the incident capture
``incident-captures/20261124-004940-loop-detected``:

  town-arrival-4317991/   the town-arrival checkpoint ``20261124-004902.816590440-turn4317991``
                          (the restarted process in Angwil, decision 0): the Black Markets'
                          circuit of the Restore Mana (finale_bm_tour) lapped, stayed the night
                          (row 44), bought one potion and closed for its funds at row 66;
                          from row 73 the town repeated
                          ``town:blocked:finale-not-in-town:restore_mana:funds`` until the loop
                          detector (row 96)

Kept: the checkpoint's journal rows up to the stop (the loadout report left out, as the other
town-arrival fixtures).

    python tests/extract_finale_bm_funds_1124_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/finale-bm-funds-1124")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-finale-bm-funds-1124"
ROWS = 97


def main():
    extract(ROOT / "town-arrival-4317991", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
