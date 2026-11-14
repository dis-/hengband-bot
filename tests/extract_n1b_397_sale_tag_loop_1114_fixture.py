"""Extract tests/fixtures/n1b-397-sale-tag-loop-1114/.

Source: n1-b life-397's incident capture 20261114-192441-livelock-exhausted
(build f8c14ff0d2), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-397-loop-1114/livelock/: the
town-arrival checkpoint of the 19:24:15 Outpost visit and its first 51
journal rows (row 47 tags the broken dagger @0 and row 48 sells it at the
Weaponsmith; row 49 tags the (トランプ) トライデント @0 over its '.', row 50
leaves to write the '.' back - the start of the loop that the stop capture
20261114-192446-loop-detected ended).

    PYTHONPATH="src;tests" python tests/extract_n1b_397_sale_tag_loop_1114_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-397-loop-1114/livelock")
TARGET = Path(__file__).with_name("fixtures") / "n1b-397-sale-tag-loop-1114"


if __name__ == "__main__":
    extract(CAPTURE / "town-arrival", TARGET, 51, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
