"""Owner 2026-11-08: inside an awake T1 hostile's sensing radius, leave now; never rest there.

Question: 「感知で、起きている強い敵（倒しきれない段階の敵）が見えている時に休みますか？」  Answer
(verbatim): 「その敵の感知範囲内なら早急に離脱する」.

Game (C:/hengband/src): the race's ``vision`` is monrace.aaf (info-reader/race-reader.cpp:131); a
monster acts toward the player whenever ``cdis <= aaf`` (monster-processor.cpp:708-710,
decide_process_continue) and wakes there (monster-status.cpp:124-127); ``cdis`` is max(dy, dx) +
min(dy, dx) / 2 (monster-update.cpp:193-204).  The rung (threat_tiers.sensed_t1_leave_key) stands
after the flee rung on the shared ladder: an awake hostile, in view or detected, T1 on its own from
contact, with the player inside its radius: stairs underfoot, *Destruction*, a relocation scroll,
Word of Recall, a walk only when none is faster and none reaches at range.  Quest plans keep their
order (only 即死 pre-empts it); outside the radius nothing changes.

Recorded: n1-c life-168 (Lv32), Angband 49F (tests/fixtures/n1c-168-judge-death-1108.json.gz):
decisions 3426-3433 replayed in order (a fresh policy at 3426, the recorded keys posted); at 3433
闇の審判『デス』 is awake and detected 21 cells away (inside its vision 90) and the recorded
decision was ``rest`` at HP 370/514.  Constructed boards are DECLARED CONSTRUCTED
(test_threat_tiers' open lit room).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.policy import HengbotPolicy  # first: threat_tiers' modules import through it
from hengbot import threat_tiers
from hengbot.model import TVAL_SCROLL, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from policy_fixtures import item
from test_esp_threat_rest_recorded import EDIT, _policy
from tests import test_threat_tiers as tt

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-168-judge-death-1108.json.gz"
REST_TURN = 3202920  # decision 3433
OFF = patch.object(threat_tiers, "sensed_t1_leave_key", lambda *args, **kwargs: None)


class JudgeDeathRestRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.recorded = {row["turn"]: row for row in cls.case["decisions"]}

    def replay(self, *patches):
        """The decisions on the trajectory boards, the recorded key posted after each."""
        boards = self.case["trajectory"]
        answers = {}
        with tempfile.TemporaryDirectory() as directory:
            for each in patches:
                each.start()
            try:
                policy = _policy(Path(directory), self.monrace)
                policy.prime(parse_snapshot(copy.deepcopy(boards[0]), self.monrace))
                policy._skill_exp_cache = (0, 0, boards[0]["player"]["level"], None)
                for raw in boards:
                    board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
                    key = str(policy.choose_key(board))
                    answers[raw["turn"]] = (key, policy.last_reason, board)
                    row = self.recorded.get(raw["turn"])
                    policy.confirm_key_posted(row["key"] if row else key)
            finally:
                for each in patches:
                    each.stop()
        return answers

    def test_the_recorded_rest(self):
        row = self.recorded[REST_TURN]
        self.assertEqual((row["decision_sequence"], row["reason"]), (3433, "rest"))

    def test_inside_judge_deaths_radius_it_leaves_instead_of_resting(self):
        key, reason, board = self.replay()[REST_TURN]
        death = next(m for m in board.detected_monsters if m.hostile)
        self.assertFalse(death.asleep)
        self.assertEqual(threat_tiers.sensing_distance(board, death), 21)
        self.assertEqual(self.monrace[death.race_id].vision, 90)
        self.assertTrue(threat_tiers.inside_sensing(HengbotPolicy(monrace_knowledge=self.monrace),
                                                    board, death))
        self.assertEqual((key, reason), ("re", threat_tiers.SENSED_LEAVE_PREFIX + "teleport"))

    def test_without_the_rule_it_stays(self):
        key, reason, _board = self.replay(OFF)[REST_TURN]
        self.assertFalse(reason.startswith(("sensed", "flee", "emergency")), (key, reason))

    def test_boards_before_death_is_known_are_unchanged(self):
        on, off = self.replay(), self.replay(OFF)
        for turn in [turn for turn in on if turn != REST_TURN]:
            self.assertEqual(on[turn][:2], off[turn][:2], turn)


class SensedLeaveTest(unittest.TestCase):
    """DECLARED CONSTRUCTED: test_threat_tiers' room, a BRUTE (T1 from contact) detected far off."""

    def setUp(self):
        self.races = {**tt.RACES, tt.BRUTE: replace(tt.RACES[tt.BRUTE], vision=20)}
        self.policy = HengbotPolicy(monrace_knowledge=dict(self.races))
        self.scroll = item("a", TVAL_SCROLL, 9, count=3, name="Teleportation")

    def board(self, x, *, race=tt.BRUTE, asleep=False):
        brute = replace(tt.monster(1, race, 10, x, asleep=asleep), position=tt.Position(10, x))
        snapshot = tt.board([], inventory=[self.scroll])
        return replace(snapshot, detected_monsters=[brute])

    def test_inside_the_radius_it_leaves(self):
        snapshot = self.board(18)  # cdis 8 <= vision 20
        self.assertEqual(threat_tiers.sensed_t1_leave_key(self.policy, snapshot), "ra")
        self.assertEqual(self.policy.last_reason, threat_tiers.SENSED_LEAVE_PREFIX + "teleport")

    def test_outside_the_radius_nothing_changes(self):
        races = {**self.races, tt.BRUTE: replace(self.races[tt.BRUTE], vision=5)}
        policy = HengbotPolicy(monrace_knowledge=races)
        self.assertIsNone(threat_tiers.sensed_t1_leave_key(policy, self.board(18)))

    def test_asleep_or_beatable_nothing_changes(self):
        self.assertIsNone(threat_tiers.sensed_t1_leave_key(self.policy, self.board(18, asleep=True)))
        # A sleeper in view (the engagement keeps it; only an awake one is left from).
        sleeper = tt.board([tt.monster(1, tt.BRUTE, 10, 18, asleep=True)], inventory=[self.scroll])
        self.assertIsNone(threat_tiers.sensed_t1_leave_key(self.policy, sleeper))
        awake = tt.board([tt.monster(1, tt.BRUTE, 10, 18)], inventory=[self.scroll])
        self.assertEqual(threat_tiers.sensed_t1_leave_key(self.policy, awake), "ra")
        weak = {**self.races, tt.WEAK: replace(self.races[tt.WEAK], vision=20)}
        policy = HengbotPolicy(monrace_knowledge=weak)
        self.assertIsNone(threat_tiers.sensed_t1_leave_key(policy, self.board(18, race=tt.WEAK)))

    def test_a_plan_floor_keeps_its_order(self):
        with patch.object(HengbotPolicy, "approved_quest_strategy", return_value=object()):
            self.assertIsNone(threat_tiers.sensed_t1_leave_key(self.policy, self.board(18)))

    def test_the_game_distance(self):
        snapshot = tt.board([])
        far = replace(tt.monster(1, tt.WEAK, 13, 18), position=tt.Position(13, 18))
        self.assertEqual(threat_tiers.sensing_distance(snapshot, far), 8 + 3 // 2)

    def test_the_vision_is_loaded(self):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        self.assertTrue(any(knowledge.vision > 0 for knowledge in monrace.values()))


if __name__ == "__main__":
    unittest.main()
