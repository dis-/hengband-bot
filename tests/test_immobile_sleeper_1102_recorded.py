"""shoot-immobile-sleeper-1102: the recorded n1-c life-103 Silver jelly (2026-11-02).

n1-c life-103 (Magic-Eater, Lv9, 131 HP) on 鉄獄5階, turns 412539-412823
(decision sequences 4279-4306): a sleeping シルバー・ゼリー (race 73,
NEVER_MOVE, two TOUCH:EAT_LITE blows) lay seven cells east of the player on a
clear row.  The player wielded a Short Bow (x2) and carried 94 matching
arrows, yet never shot: ``RANGED_SLEEPER_MAX_DISTANCE`` (4) dropped every
sleeper beyond four cells from the ranged targets ("approach it quietly
instead" -- the hunt path), and ``threat:avoid-engagement`` vetoed that
approach.  The bot stepped back, explored back towards the jelly, stepped
back again and boxed itself in with its own vetoed cells (loop-detected
05:31:45).

A monster that never moves cannot close in when a shot wakes it, so it
stays a ranged target up to the ranged range (owner 2026-11-01
「遠隔で倒せるなら離れて撃つのは可」).  The retreat gate itself
(``_material_melee_engagement``) is unchanged (owner 2026-11-02).

Fixture: tests/fixtures/immobile-sleeper-20261102.json.gz
(tests/extract_immobile_sleeper_1102_fixture.py).  Every decision is the
public ``choose_key``; posted keys go through the production executor port
(test_me_nokey_1031_recorded.PostedKey).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "immobile-sleeper-20261102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
SILVER_JELLY = 73
FIRST_SIGHT = 412539


def recorded():
    return {row["turn"]: (row["reason"], row["key"]) for row in CASE["decisions"]}


def new_policy():
    return loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])


def board(turn):
    return next(raw for raw in CASE["boards"] if raw["turn"] == turn)


class ImmobileSleeperRecordedTest(nokey.PostedKey):
    def test_recorded_board_retreated_from_the_sleeping_jelly(self):
        self.assertEqual(recorded()[FIRST_SIGHT], ("threat:avoid-engagement", "4"))
        policy = new_policy()
        snapshot = parse_snapshot(board(FIRST_SIGHT), policy._monrace_knowledge)
        (jelly,) = snapshot.visible_monsters
        self.assertEqual(jelly.race_id, SILVER_JELLY)
        self.assertTrue(jelly.asleep)
        self.assertEqual(snapshot.player.position.distance_to(jelly.position), 7)
        self.assertEqual(jelly.position.y, snapshot.player.position.y)

    def test_sleeping_never_moving_jelly_is_shot_from_seven_cells(self):
        policy = new_policy()
        raw = board(FIRST_SIGHT)
        key = loops.decide(policy, raw)
        self.assertEqual((policy.last_reason, key), ("ranged:fire", "fn6"))
        self.post(policy, raw, key)
        policy.confirm_key_posted(key)


if __name__ == "__main__":
    import unittest
    unittest.main()
