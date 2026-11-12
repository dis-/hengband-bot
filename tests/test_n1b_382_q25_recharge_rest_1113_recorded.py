"""Quest 25 on n1-b life-382 (2026-11-13 04:42:47-04:42:57): the between-phases rest, recorded.

n1-b life-382 (Magic-Eater Lv37, INT 15) shot the pen [7,17] from [5,1] ten times (5133-5142)
and then rested to refill its attack devices before the next phase (quest25_battle._recharge_key,
owner 2026-11-06 「各段階の間に、魔道具術師の使用回数のうち、攻撃に使うものを全快させる」): three
list reads ('bC', 'bA', 'bB', no game time) and one 'R100' (about 77 game ticks), eleven times,
the game turn rising each time (2983657 -> 2990091), HP full, nothing in view.  The rest was the
plan's, and progressing; the driver's cell loop guard counted its 44 decisions on one cell and
stopped the bot (loop-detected, 04:42:57).  It was not the spent-ball rest of the quylthulgs'
phase (that phase stands on [5,2]); the 01:47 stops (blocked:execute on [12,24]) were another shape.

Now ``quest25:rest-recharge`` is one of the driver's stationary-by-design reasons
(cli.STATIONARY_EXEMPT_REASONS), and a phase takes at most ``RECHARGE_REST_LIMIT`` such rests
(twice the slowest refill regenmagic gives), then goes on with what is charged.

Recorded: tests/fixtures/n1b-382-q25-recharge-rest-1113.json.gz
(tests/extract_n1b_382_q25_recharge_rest_1113_fixture.py): decisions 5124-5182 with their boards.
The guard is fed the recorded reasons as cli.main feeds them (``guard_stop``).  The cap is read on
the CONSTRUCTED Q25 board of tests/support/q25_house.py with one attack wand short (DECLARED).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import cli, me_capability, quest25_battle as battle
from hengbot.model import parse_snapshot
from tests.support import q25_house as q25

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-382-q25-recharge-rest-1113.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

STOPPED_AT = 5182


def guard_stop(exempt=None):
    """The decision the driver's cell loop guard stops at, fed as cli.main feeds it; else None."""
    recent, last_position, last_player = [], None, None
    with patch.object(cli, "STATIONARY_EXEMPT_REASONS", exempt or cli.STATIONARY_EXEMPT_REASONS):
        for raw, row in zip(CASE["boards"], CASE["recorded"]):
            snapshot = parse_snapshot(copy.deepcopy(raw), q25.RACES)
            previous_position, last_position = last_position, snapshot.player.position
            previous_player, last_player = last_player, snapshot.player
            if not cli._cell_loop_guard_applies(snapshot, row["reason"], previous_position, previous_player):
                recent.clear()
                continue
            position = snapshot.player.position
            recent.append((snapshot.floor_key, position.y, position.x))
            if cli._is_looping(recent):
                return row["sequence"]
    return None


class RechargeRestRecordedTest(unittest.TestCase):

    def test_the_recording(self):
        rows = [row for row in CASE["recorded"] if row["sequence"] >= 5146]
        self.assertEqual([row["reason"] for row in rows if row["key"] == battle.RECHARGE_REST_KEY],
                         [battle.RECHARGE_REASON] * 10)
        turns = [row["turn"] for row in rows if row["key"] == battle.RECHARGE_REST_KEY]
        self.assertEqual(turns, sorted(set(turns)))          # every rest spent game time
        self.assertEqual({(board["player"]["y"], board["player"]["x"])
                          for board in CASE["boards"][-40:]}, {(5, 1)})

    def test_the_rest_is_stationary_by_design(self):
        self.assertIn(battle.RECHARGE_REASON, cli.STATIONARY_EXEMPT_REASONS)
        self.assertIsNone(guard_stop())

    def test_control_without_it_the_guard_stops_where_it_stopped(self):
        exempt = cli.STATIONARY_EXEMPT_REASONS - {battle.RECHARGE_REASON}
        self.assertEqual(guard_stop(exempt), STOPPED_AT)


class RechargeRestLimitTest(unittest.TestCase):
    """DECLARED CONSTRUCTED: the house board, one absorbed attack wand short of full."""

    def _ctx(self):
        raw = q25.board((5, 1))
        policy = q25.new_policy(raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), q25.RACES)
        policy._me_device_lists = {"wand": (0, ({"name": me_capability.names("wand", 21)[0],
                                                 "fail": 5, "success": 95, "current": 3, "max": 21},))}
        ctx = battle._ctx(policy, snapshot)
        ctx.battle.browsed = frozenset({"wand"})
        return ctx

    def test_rests_up_to_the_limit_then_goes_on(self):
        ctx = self._ctx()
        keys = []
        for _ in range(battle.RECHARGE_REST_LIMIT + 2):
            keys.append(battle._recharge_key(ctx))
            ctx.battle.browsed = frozenset({"wand"})   # the reads between the rests
        self.assertEqual(keys[:battle.RECHARGE_REST_LIMIT],
                         [battle.RECHARGE_REST_KEY] * battle.RECHARGE_REST_LIMIT)
        self.assertEqual(keys[battle.RECHARGE_REST_LIMIT:], [None, None])

    def test_a_new_phase_rests_again(self):
        ctx = self._ctx()
        ctx.battle.recharge_rests = battle.RECHARGE_REST_LIMIT
        battle._next_phase(ctx.battle)
        ctx.battle.browsed = frozenset({"wand"})   # the new phase's list read
        self.assertEqual(battle._recharge_key(ctx), battle.RECHARGE_REST_KEY)


if __name__ == "__main__":
    unittest.main()
