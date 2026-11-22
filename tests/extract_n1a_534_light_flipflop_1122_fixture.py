"""Extract tests/fixtures/n1a-534-light-flipflop-1122/.

n1-a life-534 (Lv20 warrior, build bot-411807c7d) stopped three times in town on 2026-11-22 with
``town:blocked:equipment-slot-flipflop:light`` (15:48:19, 15:48:31, 15:48:44) and retired.  The
light slot alternated between the visit target's transaction (the 灼熱の真鍮のランタン) and the
light ranker's ``wield-light`` (the identified 不朽の眼のフェアノールのランプ).

Source: the second stop's town-arrival checkpoint (jsonlog/town-arrival/
20261122-154824.093008527-turn483239, the visit of the 15:48:31 stop), copied read-only from the
viewing server to C:/hengband-backups/pdca/n1a-534-light-flipflop/.  The fixture keeps the
arrival policy, the sidecars and the journal's rows 0-18: the visit up to the ranker's second
wield (row 18), after the transaction wore the target's lantern (rows 14-15).

    python tests/extract_n1a_534_light_flipflop_1122_fixture.py
    (PYTHONPATH: src, tests and the root)
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1a-534-light-flipflop/jsonlog/town-arrival/"
             "20261122-154824.093008527-turn483239")
TARGET = Path(__file__).with_name("fixtures") / "n1a-534-light-flipflop-1122"
ROWS = 19


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    print(TARGET, sum(path.stat().st_size for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
