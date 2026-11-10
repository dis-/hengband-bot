"""n1-c life-193 2026-11-10 19:37: the mining run the Greater Hell-Beast ended leaves.

Recorded: tests/fixtures/yeek-exit-loops-1110/hellbeast-1937.json.gz
(tests/extract_yeek_exit_loops_1110_fixtures.py), the loop-detected capture of n1-c
life-193 (Magic-Eater Lv8, Yeek cave 1F, build 180ea6743).  The unique Greater Hell-Beast
(race 39) slept 17-18 cells away.  The owner's abort (2026-10-31 「採掘を切り上げて地上に
戻る」, _mining_unbeatable_unique_abort_key) latched the return, yet:

* the fruitless-disengage release (_fruitless_disengage_key, the mining-preemption branch
  reached through _unprofitable_unique_disengage_key) cleared that return on every board, so
  the run went back to ``fundraise:seek-loot`` (row 234133; at 235128, one step after the
  abort's only ``seek-upstairs``, it walked past the up stairs at [33,12]);
* the flight (owner 2026-11-07 「眠っている敵でも強い敵からは離れる」) found no cell farther
  from it at two dead ends and, with no escape scroll (Recall is not one), waited: 92 times
  at [36,14] (from 234177) and 194 times at [37,16] (from 235456) until the loop detector,
  5 cells from the up stairs with 9 Recall scrolls.

Every decision is the public ``choose_key`` of one fresh policy fed the recorded boards in
order (the abort latch is made by the real abort on the boards that show the beast).
DECLARED RECONSTRUCTED: the mining-run state the departure sets (mode "mine"), as in
tests/test_hellbeast_abort_mining.py.  DECLARED: once a decision differs from the recorded
one, the following recorded boards are still fed in order (the game moved as recorded).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import SV_SCROLL_WORD_OF_RECALL, TVAL_SCROLL, Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.test_dungeon_1031_recorded import skill
from tests.test_n1b_348_stops_1108_recorded import knowledge

FIXTURE = Path(__file__).with_name("fixtures") / "yeek-exit-loops-1110" / "hellbeast-1937.json.gz"
HELL_BEAST = 39
RECALL = (TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL)
UPSTAIRS = Position(33, 12)
RELEASED_RETURN_BOARD = 234133  # [33,15]: recorded fundraise:seek-loot
FIRST_WAIT_BOARD = 234177  # [36,14]: recorded flee:wait (92 in a row)
LAST_WAIT_BOARD = 235456  # [37,16]: recorded flee:wait (194 in a row)
ABORT = "fundraise:abort-unbeatable-unique:"


with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
BOARDS = CASE["rows"]


def recorded():
    rows = {}
    for row in CASE["decisions"]:
        rows.setdefault(row["turn"], (row["key"], row["reason"]))
    return rows


def replay(until):
    """The decisions of one fresh policy on the recorded boards up to ``until``."""
    races = knowledge(CASE)
    policy = HengbotPolicy(monrace_knowledge=races)
    first = copy.deepcopy(BOARDS[0])
    policy.prime(parse_snapshot(first, races))
    skill(policy, first)
    policy._fundraising_mode = "mine"  # DECLARED RECONSTRUCTED (module docstring)
    decisions = {}
    for raw in BOARDS:
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), races))
        key = "" if key is None else str(key)
        if key:
            policy.confirm_key_posted(key)
        decisions.setdefault(raw["turn"], (key, policy.last_reason))
        if raw["turn"] == until:
            return policy, raw, decisions
    raise AssertionError(f"board {until} not recorded")


class RecordedRowsTest(unittest.TestCase):
    def test_recorded_scene(self):
        rows = recorded()
        self.assertEqual(rows[RELEASED_RETURN_BOARD], ("6", "fundraise:seek-loot"))
        self.assertEqual(rows[FIRST_WAIT_BOARD], ("5", "flee:wait"))
        self.assertEqual(rows[LAST_WAIT_BOARD], ("5", "flee:wait"))
        self.assertEqual(rows[235123], ("7", ABORT + "seek-upstairs"))
        # The ring holds the last 167 boards: 105 of their decisions waited.
        waits = sum(1 for row in CASE["decisions"] if row["reason"] == "flee:wait")
        self.assertEqual(waits, 105)
        for raw in BOARDS:
            if raw["turn"] in (FIRST_WAIT_BOARD, LAST_WAIT_BOARD):
                self.assertEqual([(m["race_id"], m["asleep"]) for m in raw["visible_monsters"]],
                                 [(HELL_BEAST, True)])
                self.assertTrue(any((item["tval"], item["sval"]) == RECALL and item["count"] >= 9
                                    for item in raw["inventory"]), "9 Word of Recall carried")


class AbortedRunLeavesTest(unittest.TestCase):
    def test_the_abort_keeps_its_return(self):
        policy, _raw, decisions = replay(RELEASED_RETURN_BOARD)
        # Unfixed: ('6', 'fundraise:seek-loot'), the return cleared by the disengage release.
        self.assertEqual(decisions[RELEASED_RETURN_BOARD], ("7", "fundraise:seek-upstairs"))
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._mining_abort_floor, tuple(BOARDS[0]["floor"][k] for k in
                                                           ("dungeon_id", "level", "quest_id")))

    def test_a_dead_end_flight_steps_toward_the_stairs(self):
        _policy, _raw, decisions = replay(FIRST_WAIT_BOARD)
        # Unfixed: ('5', 'flee:wait').  The step to [35,13] comes no nearer the beast.
        self.assertEqual(decisions[FIRST_WAIT_BOARD], ("7", ABORT + "seek-upstairs"))

    def test_a_dead_end_flight_reads_recall_when_the_stairs_step_nears_it(self):
        policy, raw, decisions = replay(LAST_WAIT_BOARD)
        key, reason = decisions[LAST_WAIT_BOARD]
        # Unfixed: ('5', 'flee:wait').  The step toward the stairs from [37,16] is one
        # cell nearer the sleeping beast (the flight would walk it back): Recall instead.
        self.assertEqual(reason, ABORT + "recall")
        recall = next(item for item in raw["inventory"]
                      if (item["tval"], item["sval"]) == RECALL)
        self.assertEqual(key, "r" + recall["slot"])


if __name__ == "__main__":
    unittest.main()
