"""Quest 25's phase battle across a bot restart (quest25_battle_record).

n1-a life-494 (2026-11-07 20:06-20:09): six kills read in the ambush (phase 1), then a restart
began the floor at phase 0, no kills, the 5000-action quiet count at 0.  These tests replay the
recorded n1-c life-159 floor (tests/fixtures/q25-mass-n1c-159-1107.json.gz, the same ambush:
seven kills, the quiet count, the Potion of Enlightenment drunk) with one process, then decide the
next recorded board with a second process that shares only the record beside the decision log.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_geometry as geo
from hengbot.model import parse_snapshot
from tests import test_q25_n1c_159_1107_recorded as n1c

BOARDS = n1c.CASE["boards"]
INDEX = {row["sequence"]: index for index, row in enumerate(n1c.CASE["recorded"])}
# 2891258 [melee into the dreadmaster]; the next board prints 「ドリードマスターを倒した。」.
BEFORE_KILL = 386
KILL_BOARD = 387
# Deep in the ambush's quiet wait after the kills (the quiet count at 20 on the recording's replay).
QUIET_BOARD = 411
DREADMASTER = 690


def _state(battle):
    """Every carried field (``observed`` names the process's own snapshot object)."""
    return {field.name: getattr(battle, field.name) for field in dataclasses.fields(battle)
            if field.name != "observed"}


def _decide(policy, raw):
    key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
    policy.confirm_key_posted(key)
    return key, policy.last_reason


def _battle(policy):
    navigator = policy._quest_navigators.get(geo.QUEST_ID)
    return None if navigator is None else navigator.phase_battle


class Q25BattleRecordTest(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "q25-battle.json"

    def tearDown(self):
        self.directory.cleanup()

    def _process(self, first):
        policy = n1c.new_policy(first)
        policy._q25_battle_record_path = self.path
        return policy

    def _run(self, through):
        """One process deciding every recorded board up to ``through`` (inclusive)."""
        policy = self._process(BOARDS[0])
        for raw in BOARDS[:INDEX[through] + 1]:
            _decide(policy, raw)
        return policy

    def test_a_restart_mid_ambush_resumes_phase_kills_and_quiet(self):
        before = self._run(QUIET_BOARD - 1)
        carried = _state(_battle(before))
        self.assertEqual(carried["phase"], 0)                     # the ambush
        self.assertEqual(carried["kills"].get(DREADMASTER), 1)
        self.assertGreater(sum(carried["kills"].values()), 5)
        self.assertGreater(carried["quiet"], 10)
        self.assertTrue(carried["enlightened"])
        # The process that kept running decides the next board ...
        continued = copy.deepcopy(before)
        continued._q25_battle_record_path = None   # the record stays the one ``before`` left
        expected_answer = _decide(continued, BOARDS[INDEX[QUIET_BOARD]])
        expected = _state(_battle(continued))
        # ... and a restarted one, sharing only the record, decides it the same way.
        restarted = self._process(BOARDS[INDEX[QUIET_BOARD]])
        self.assertEqual(_decide(restarted, BOARDS[INDEX[QUIET_BOARD]]), expected_answer)
        self.assertEqual(_state(_battle(restarted)), expected)
        self.assertEqual(expected["quiet"], carried["quiet"] + 1)

    def test_the_board_already_decided_is_not_counted_twice(self):
        before = self._run(KILL_BOARD)
        carried = _state(_battle(before))
        self.assertEqual(carried["kills"].get(DREADMASTER), 1)
        # The restarted process is shown the kill board its predecessor already read.
        restarted = self._process(BOARDS[INDEX[KILL_BOARD]])
        _decide(restarted, BOARDS[INDEX[KILL_BOARD]])
        resumed = _state(_battle(restarted))
        self.assertEqual(resumed["kills"].get(DREADMASTER), 1)
        self.assertEqual(resumed["quiet"], carried["quiet"])
        self.assertEqual(resumed["kills"], carried["kills"])

    def test_a_decision_off_the_floor_ends_the_visit_s_record(self):
        self._run(QUIET_BOARD - 1)
        self.assertIsNotNone(json.loads(self.path.read_text(encoding="utf-8"))["battle"])
        # A restarted process decides a board on another floor (the town after the quest).
        town = copy.deepcopy(BOARDS[INDEX[QUIET_BOARD]])
        town["floor"] = dict(town["floor"], dungeon_id=0, level=0, quest_id=0)
        elsewhere = self._process(town)
        _decide(elsewhere, town)
        self.assertIsNone(json.loads(self.path.read_text(encoding="utf-8"))["battle"])
        # A later visit to the Q25 floor starts clean.
        visit = self._process(BOARDS[INDEX[QUIET_BOARD]])
        _decide(visit, BOARDS[INDEX[QUIET_BOARD]])
        fresh = _state(_battle(visit))
        self.assertEqual(fresh["kills"], {})
        self.assertFalse(fresh["enlightened"])

    def test_an_earlier_turn_is_not_the_recorded_visit(self):
        self._run(QUIET_BOARD - 1)
        earlier = self._process(BOARDS[INDEX[BEFORE_KILL]])
        _decide(earlier, BOARDS[INDEX[BEFORE_KILL]])
        self.assertNotIn(DREADMASTER, _battle(earlier).kills)


if __name__ == "__main__":
    unittest.main()
