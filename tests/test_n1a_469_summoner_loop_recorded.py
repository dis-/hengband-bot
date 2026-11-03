"""Recorded replay of the n1-a life-469 loop of 2026-11-03 09:30 (鉄獄30階).

Source: tests/fixtures/loop-n1a-469-1103.json.gz
(tests/extract_n1a_469_summoner_loop_fixture.py): the Lv29 warrior's boards (724 max HP) of
turns 938634-939207 (build 96a499308) and the recorded decision rows.

Beside a ミミック(箱) (NEVER_MOVE, summons, curses and Stinking Cloud from out
of sight) the unseen-attacker retreat was armed on the floor.  The immobile
summoner owner stepped out of the mimic's line of fire
(``explore:avoid-immobile-summoner`` '6', (3, 80) -> (3, 81)); outside the
zone it yields to every other owner, and the unseen retreat's reverse walk
(``unseen:reverse-choke`` '4') stepped straight back in.  The two alternated
for 30 decisions up to the loop detector (the same pair stopped life-469 on
26F at 09:24).

The reverse walk now refuses the shared avoid set like every other route
(policy_observation._refresh_warning_avoidance), so the cell the summoner
owner left is not walked back into.  Every decision is the public
``choose_key``; the keys of the out-of-zone boards go through the production
executor port.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position
from hengbot.policy_constants import DIRECTION_KEYS
from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "loop-n1a-469-1103.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

FIRST_ALTERNATION = 938872      # the first reverse-choke '4' after the zone step
OUTSIDE, INSIDE = (3, 81), (3, 80)
OFFSETS = {key: offset for offset, key in DIRECTION_KEYS.items()}


class SummonerZoneReverseWalkRecordedTest(d57.PostedDeathKey):
    def test_recorded_rows(self):
        recorded = d57.recorded(CASE)
        rows = {raw["turn"]: raw for raw in CASE["boards"]}
        alternation = [turn for turn in sorted(recorded) if turn >= FIRST_ALTERNATION]
        reasons = {recorded[turn] for turn in alternation
                   if (rows[turn]["player"]["y"], rows[turn]["player"]["x"]) == OUTSIDE
                   and recorded[turn][0] != "melee"}
        self.assertEqual(reasons, {("unseen:reverse-choke", "4"), ("loop-detected", "")})

    def test_reverse_walk_does_not_reenter_the_summoner_zone(self):
        policy = d57.loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])
        checked = 0
        for raw in CASE["boards"]:
            raw = copy.deepcopy(raw)
            key = d57.loops.decide(policy, raw)
            here = raw["player"]["y"], raw["player"]["x"]
            if raw["turn"] >= FIRST_ALTERNATION and here == OUTSIDE:
                self.assertNotEqual(policy.last_reason, "unseen:reverse-choke", raw["turn"])
                offset = OFFSETS.get(key)
                # 939023: a summoned よろめき歩く塊 stood on the zone cell; that
                # key is the melee blow, not a step.
                if offset is not None and policy.last_reason != "melee":
                    target = Position(here[0] + offset[0], here[1] + offset[1])
                    self.assertNotIn(target, policy._immobile_summoner_avoid_cells, raw["turn"])
                    self.assertNotEqual((target.y, target.x), INSIDE, raw["turn"])
                self.post(policy, raw, key)
                checked += 1
            policy.confirm_key_posted(key)
        self.assertGreaterEqual(checked, 15)


if __name__ == "__main__":
    unittest.main()
