"""*Destruction* is used when any one of its threats is in the sure radius (owner 2026-11-17 Q1).

Owner 2026-11-17 (whole-bot maintainability review, question Q1, answer verbatim 「脅威のどれか1体が
半径13以内なら使う」): destruction_use asked only whether the single most dangerous threat was
within ``GUARANTEED_RADIUS`` -- the most dangerous visible hostile for a rung without a ``leaving``
set (``_threat_in_range``), the most dangerous of the set from contact for one with it
(``_threat_in_reach`` through ``reach_subject``) -- so a more dangerous threat 14 or more cells off
kept the use from a T1 inside the circle.  Now any one of them in the radius, seen or sensed, is
enough: the ``leaving`` set's members, and without one a monster that is T1 alone (threat_tiers
``alone_t1`` from contact) or the most dangerous visible hostile (the 11-04 reading, kept).

Recorded: tests/fixtures/approach-subject-20261117.json.gz (n1-c life-216, Magic-Eater Lv50,
Angband 80F, 2026-11-17 08:46-08:47; see test_approach_subject_1117_recorded), the 43 player-turn
boards decided in order through one policy's ``choose_key``.  On turn 4552002 at (36,77) the awake
ファナティック・ウォーモンガー (race 1227) at (27,69) is 13 cells off and the sleeping 1188 (the more
dangerous from contact) 20 off: the recorded build, and this one before Q1, explored there; now the
absorbed *Destruction* is cast.  DECLARED RECONSTRUCTED (as that module): the absorbed *Destruction*
list row (22 charges at 95%).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import destruction_use, me_capability, threat_tiers
from hengbot.model import SV_STAFF_DESTRUCTION, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests import test_approach_subject_1117_recorded as subject_case
from tests import test_sleeping_t1_destruction_1117_recorded as sleeping_case
from tests.support.recorded import EDIT, _policy

SLEEPER, WARMONGER = subject_case.SLEEPER, subject_case.WARMONGER
FAR_AWAKE = 62   # the detected race 715 at (16,26) on the 62F landing board

USED_TURN = 4552002


class AnyThreatInRadiusRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(subject_case.FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.directory = TemporaryDirectory()
        cls.rows = {}
        sleeping_case.SleepingT1DestructionTest.setUpClass()
        cls.landing = sleeping_case.SleepingT1DestructionTest.landing
        policy = _policy(Path(cls.directory.name), cls.monrace)
        first = parse_snapshot(copy.deepcopy(cls.data["boards"][0]), cls.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        for raw in cls.data["boards"]:
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), cls.monrace))
            key = policy.choose_key(board)
            cls.rows[board.turn] = (board.player.position, key, policy.last_reason)
            if key:
                policy.confirm_key_posted(key)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def board(self, turn):
        raw = next(raw for raw in self.data["boards"] if raw["turn"] == turn)
        return parse_snapshot(copy.deepcopy(raw), self.monrace)

    def test_the_warmonger_is_in_the_radius_and_the_sleeper_beyond(self):
        board = self.board(USED_TURN)
        here = board.player.position
        shown = {monster.race_id: monster
                 for monster in (*board.visible_monsters, *board.detected_monsters)}
        self.assertLessEqual(game_distance(here, shown[WARMONGER].position),
                             destruction_use.GUARANTEED_RADIUS)
        self.assertGreater(game_distance(here, shown[SLEEPER].position),
                           destruction_use.GUARANTEED_RADIUS)

    def test_the_use_is_cast_with_the_warmonger_in_the_radius(self):
        """The sensed T1 rung's use with both T1s as its ``leaving`` set (the recorded build
        and this one before Q1 explored here)."""
        _cell, _key, reason = self.rows[USED_TURN]
        self.assertTrue(reason.startswith(destruction_use.REASON), self.rows[USED_TURN])

    def test_any_member_of_the_leaving_set_in_the_radius_is_enough(self):
        board = self.board(USED_TURN)
        both = [monster for monster in (*board.visible_monsters, *board.detected_monsters)
                if monster.race_id in (WARMONGER, SLEEPER)]
        policy = type("P", (), {})()
        self.assertTrue(destruction_use._threat_in_reach(policy, board, None, hostiles=both))
        sleeper = [monster for monster in both if monster.race_id == SLEEPER]
        self.assertFalse(destruction_use._threat_in_reach(policy, board, None, hostiles=sleeper))

    def test_without_a_leaving_set_a_t1_alone_in_the_radius_is_enough(self):
        """The rung without a ``leaving`` set (``_threat_in_range``) on the n1-c life-216 62F
        landing board (tests/fixtures/route-veto-sealed-20261117.json.gz, turn 3897141; the
        harness of test_sleeping_t1_destruction_1117_recorded).  DECLARED CONSTRUCTED: the
        visible スリング・ハーフリング (index 101, 9 cells off) made a sleeping パワー・ワイアーム
        (T1 alone), and the detected 715 at (16,26), 14 cells off, shown awake in view: its
        next-turn damage makes it the most dangerous visible hostile, beyond the radius, which
        before Q1 refused the use with the T1 inside it."""
        raw = copy.deepcopy(sleeping_case.SleepingT1DestructionTest.landing)
        far = next(monster for monster in raw["detected_monsters"] if monster["index"] == FAR_AWAKE)
        raw["detected_monsters"].remove(far)
        raw["visible_monsters"].append(dict(far, asleep=False))
        sleeping_case.SleepingT1DestructionTest.landing = raw
        try:
            case = sleeping_case.SleepingT1DestructionTest()
            case.addCleanup = self.addCleanup
            _key, _reason, policy, board, wyrm = case.decide(
                lambda field, m: field == "visible_monsters" and m["index"] == sleeping_case.IN_VIEW_INDEX)
        finally:
            sleeping_case.SleepingT1DestructionTest.landing = self.landing
        here = board.player.position
        awake = next(monster for monster in board.visible_monsters if monster.index == FAR_AWAKE)
        self.assertGreater(game_distance(here, awake.position), destruction_use.GUARANTEED_RADIUS)
        self.assertGreater(policy._predicted_damage(board, [awake], turns=1),
                           policy._predicted_damage(board, [wyrm], turns=1))
        self.assertLessEqual(game_distance(here, wyrm.position), destruction_use.GUARANTEED_RADIUS)
        self.assertTrue(threat_tiers.alone_t1(policy, board, wyrm, contact=True))
        # (``usable`` itself answers False now: the decision just cast the use on this turn.)
        self.assertTrue(destruction_use._threat_in_range(policy, board, None))
        self.assertTrue(destruction_use._scene_holds(policy, board))

if __name__ == "__main__":
    unittest.main()
