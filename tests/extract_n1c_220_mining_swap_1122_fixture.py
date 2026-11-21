"""Freeze the n1-c life-220 mining-loop records (2026-11-22, build bot-56fa91268).

Source, copied read-only from the viewing server (~/hengbot-soak/n1-c/life-220) to
C:/hengband-backups/pdca/captures/n1c-220-mining-swap-1122/n1-c/life-220/:

  jsonlog/town-arrival/20261122-060756.460511661-turn293876/: a town visit the Magic-Eater's
      staff stock-out run came back to with シャベル in both hands (its 39 journal rows: the
      visit's swap took both off, wore ロング・ソード, deposited the shovels, and the next set's
      kit withdrew one again);
  jsonlog/town-arrival/20261122-062642.341510616-turn630950/: a later visit with no digger
      (追加攻撃のカタナ in hand), its first 12 rows;
  incident-captures/20261122-060404-town-blocked-stage-deadline-equipment/snapshots/
      snapshots-current.jsonl.gz: three boards of the ring -- town turn 158542 (ロング・ソード
      in the main hand after the town re-arm), Yeek cave 1F turn 161614 (シャベル in both hands)
      and town turn 170386 (ロング・ソード again).

Only this extraction tool reads the captures; the committed tests read the fixtures.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from support.town_arrival_fixture import extract
from tests.extract_me_staff_loops_1031 import ring_rows

LIFE = Path("C:/hengband-backups/pdca/captures/n1c-220-mining-swap-1122/n1-c/life-220")
ARRIVALS = LIFE / "jsonlog" / "town-arrival"
RING = (LIFE / "incident-captures" / "20261122-060404-town-blocked-stage-deadline-equipment"
        / "snapshots" / "snapshots-current.jsonl.gz")
FIXTURES = Path(__file__).with_name("fixtures")
VISITS = (("20261122-060756.460511661-turn293876", "n1c-220-mining-visit-1122", 39),
          ("20261122-062642.341510616-turn630950", "n1c-220-katana-visit-1122", 12))
RING_TURNS = (158542, 161614, 170386)
RING_OUTPUT = FIXTURES / "n1c-220-hand-trail-1122.json.gz"


def main():
    for visit, name, rows in VISITS:
        extract(ARRIVALS / visit, FIXTURES / name, rows)
    boards = {}
    for row in ring_rows(RING):
        if row.get("type") == "player_turn" and row.get("turn") in RING_TURNS:
            boards.setdefault(row["turn"], row)
    with gzip.open(RING_OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump({"source": "n1-c life-220 incident 20261122-060404 snapshot ring",
                   "boards": [boards[turn] for turn in RING_TURNS]}, stream, ensure_ascii=False)


if __name__ == "__main__":
    main()
