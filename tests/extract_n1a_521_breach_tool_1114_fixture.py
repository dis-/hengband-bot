"""Extract tests/fixtures/n1a-521-breach-tool-1114/.

Source: n1-a life-521's town-arrival checkpoint of the visit that began
2026-11-14 03:18:11 (turn 650561, build bot-00391d445), whose Q2 the bot
then stopped in at 03:18:30, 03:18:42 and 03:18:54
(captures/20261114-0318*-quest-blocked-q-breach-tool), copied read-only from
the viewing server to
C:/hengband-backups/pdca/captures/n1a-521-breach-tool-1114/: journal rows
0-42 (row 41 takes Q2, row 42 walks Home to shelve the Dwarven Shovel).  The
loadout report (an append-only log the policy only writes) is left out.

    PYTHONPATH="src;tests" python tests/extract_n1a_521_breach_tool_1114_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/captures/n1a-521-breach-tool-1114/jsonlog/town-arrival/"
             "20261114-031811.389537364-turn650561")
TARGET = Path(__file__).with_name("fixtures") / "n1a-521-breach-tool-1114"


if __name__ == "__main__":
    extract(VISIT, TARGET, 43, frozenset({"_loadout_report_path"}))
    print(sorted(path.name for path in TARGET.iterdir()))
