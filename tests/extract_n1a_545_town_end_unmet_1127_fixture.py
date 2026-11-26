"""Extract tests/fixtures/n1a-545-town-end-unmet-1127/ (tests/test_n1a_545_town_end_unmet_1127_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL24, Sorcery, an anti-magic shield worn), the incident
capture ``incident-captures/20261127-043922-town-blocked-unmet-home_candidate_resolved`` copied
read-only from the viewing server to C:/hengband-backups/pdca/captures/n1a-545-town-end-unmet-1127/:

  town-arrival/20261127-043914.586645314-turn1749480/
                          41 rows: row 12 took a Home candidate for identification, rows 13-15
                          cast 鑑定 three times (「反魔法バリアが魔法を邪魔した！」), row 16 deposited it
                          back as weight overload, rows 18-37 bought four Identify scrolls and the
                          rest, row 40 stopped under town:blocked:unmet:home_candidate_resolved

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_town_end_unmet_1127_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-town-end-unmet-1127/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-town-end-unmet-1127"
ROWS = 41


def main():
    extract(ROOT / "20261127-043914.586645314-turn1749480", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
