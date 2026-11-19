"""n1-c life-217, Quest 33 after a bot restart (2026-11-19 22:46): 段2 never began.

The process restarted at 22:46 (tests/fixtures/n1c-217-q33-resume-1119.json.gz, extracted by
tests/extract_n1c_217_q33_resume_1119_fixture.py from C:/hengband-backups/pdca/captures/
n1c-217-q33-lure-1119) began the floor with no kills: the room sweep's kills of its tracked races
(quest_alignment_split ``split_kills``) lived in the previous processes only.  The three Its (18:30),
Dagons and Bokrugs (20:25-20:26) read dead by those processes were alive again by ``living``, so the
段2 lure (quest_lure_approach, ``after_races_dead`` [393, 595, 489]) did not run; the plan walked its
stands, stopped by name at [14,30] with quest:blocked:sweep-nothing-comes and answered '5' 35 times
until the loop detector halted it.

Now (quest_sweep_record): the kills each decision leaves are written beside the decision log and the
first decision of a restarted process restores them on the same floor; the sweep's
``quest:blocked:sweep-nothing-comes`` (and ``-nothing-left``) is a final stop of the bot
(policy_constants ``POLICY_FINAL_STOP_REASONS``), not a '5' repeated for the loop detector.

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival of the same day
(tests/fixtures/quest32-one-turn-kill-1119/n1c-217, tests/test_quest33_alignment_split ``recorded``) with
the recorded board's skill lists given (the restarted process read them first, periodic
skill-exp-knowledge, before its quest decisions); the record the previous process would have left is
written by quest_sweep_record itself from the earlier processes' kill lines and turns (the fixture's
``earlier_lines``, read from their decision logs), fed to the sweep's own kill reader board by board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import cli, quest_alignment_split, quest_lure_approach, quest_room_sweep, quest_sweep_record
from hengbot.model import parse_snapshot
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import BOKRUG, DAGON, IT, QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-q33-resume-1119.json.gz"
DEAD = {IT: 3, DAGON: 3, BOKRUG: 3}


class N1c217Q33ResumeTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            self.case = json.load(stream)

    def process(self):
        scratch, policy, _town = recorded("n1c-217")
        self.addCleanup(scratch.cleanup)
        board = parse_snapshot(self.case["board"], policy._monrace_knowledge)
        board = replace(board, player=replace(board.player, two_weapon_skill=0, shield_skill=0))
        policy._sweep_kill_record_path = Path(scratch.name) / "sweep-kills.json"
        return policy, board

    def previous_process_record(self, path):
        """The record the earlier processes leave: their kill lines read by the sweep's own reader."""
        policy, board = self.process()
        policy._sweep_kill_record_path = path
        plan = policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        navigator = _navigator(policy, board, QUEST)
        for message, turn in self.case["earlier_lines"]:
            seen = replace(board, turn=int(turn), messages=[message])
            quest_alignment_split.observe(policy, seen, navigator, plan)
        quest_sweep_record.record(policy, replace(board, turn=max(int(t) for _m, t in self.case["earlier_lines"])))
        return navigator

    def decide(self, policy, board):
        """The restarted process's first quest decision on the recorded board."""
        key = policy.choose_key(board)
        return [(key, policy.last_reason)]

    def test_the_restarted_run_never_began_the_lure(self):
        reasons = [run["reason"] for run in self.case["runs"]]
        self.assertNotIn(quest_lure_approach.LURE_WALK_REASON, reasons)
        self.assertEqual(reasons[-2:], [quest_room_sweep.NOTHING_COMES_REASON, "loop-detected"])
        self.assertEqual(self.case["runs"][-2]["decisions"], 35)

    def test_without_a_record_the_dead_are_alive_and_the_sweep_walks(self):
        policy, board = self.process()
        made = self.decide(policy, board)
        self.assertEqual({reason for _key, reason in made}, {quest_room_sweep.WALK_REASON})
        navigator = policy._quest_navigators[QUEST]
        self.assertEqual(navigator.split_kills, {})
        plan = policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        self.assertEqual(quest_alignment_split.living(policy, board, navigator, plan, IT), 3)
        self.assertFalse(quest_lure_approach.active(policy, board, navigator, plan))

    def test_with_the_record_the_restarted_process_begins_the_lure(self):
        policy, board = self.process()
        earlier = self.previous_process_record(policy._sweep_kill_record_path)
        self.assertEqual(earlier.split_kills, DEAD)
        made = self.decide(policy, board)
        self.assertEqual({reason for _key, reason in made}, {quest_lure_approach.LURE_WALK_REASON})
        navigator = policy._quest_navigators[QUEST]
        self.assertEqual(navigator.split_kills, DEAD)
        self.assertEqual(sorted(navigator.split_kill_turns), sorted(earlier.split_kill_turns))
        # The restarted process writes them on for the next restart.
        record = json.loads(policy._sweep_kill_record_path.read_text(encoding="utf-8"))
        self.assertEqual(len(record["kills"]), 9)
        self.assertEqual(record["turn"], board.turn)

    def test_an_older_save_keeps_the_kills_read_before_it(self):
        policy, board = self.process()
        self.previous_process_record(policy._sweep_kill_record_path)
        older = replace(board, turn=5015000)  # after the Its and a Dagon and the Bokrugs, before two Dagons
        quest_sweep_record.observe(policy, older)
        navigator = _navigator(policy, older, QUEST)
        quest_sweep_record.take(policy, older, navigator)
        self.assertEqual(navigator.split_kills, {IT: 3, DAGON: 1, BOKRUG: 3})

    def test_another_floor_restores_nothing(self):
        policy, board = self.process()
        self.previous_process_record(policy._sweep_kill_record_path)
        elsewhere = replace(board, floor_key=(1, 45, 0))
        quest_sweep_record.observe(policy, elsewhere)
        self.assertIsNone(getattr(policy, "_sweep_kills_restored", None))

    def test_nothing_comes_is_a_final_stop(self):
        policy, _board = self.process()
        for reason in (quest_room_sweep.NOTHING_COMES_REASON, quest_room_sweep.NOTHING_LEFT_REASON):
            policy.last_reason = reason
            self.assertTrue(cli._policy_final_stop_required(policy))
            self.assertIn("stopping the bot", cli._policy_final_stop_banner(reason))


if __name__ == "__main__":
    unittest.main()
