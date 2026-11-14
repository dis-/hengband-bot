"""Extract tests/fixtures/n1b-397-q25-gate-1114/.

Source: n1-b life-397's town-arrival checkpoint of the visit that began 2026-11-14 15:56:00
(turn 4259464), copied read-only from the viewing server to
C:/hengband-backups/pdca/q25-why-1114/data/n1-b/life-397/: the Lv45 Magic-Eater whose Q25
(『幽霊屋敷』) acceptance gate read its absorbed attack powers.  Journal rows 0-84 (row 84
reads the recall to the alternate dungeon).  The Home disposal history (an append-only log
the policy only writes) is left out.

    PYTHONPATH="src;tests" python tests/extract_n1b_397_q25_gate_1114_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/q25-why-1114/data/n1-b/life-397/jsonlog/town-arrival/"
             "20261114-155600.631511796-turn4259464")
TARGET = Path(__file__).with_name("fixtures") / "n1b-397-q25-gate-1114"


if __name__ == "__main__":
    extract(VISIT, TARGET, 85, frozenset({"_home_disposal.history_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
