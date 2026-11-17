"""The danger judgements read the danger line of fire (owner 2026-11-17 Q5).

Owner 2026-11-17 (whole-bot maintainability review, question Q5, answer verbatim 「危険の判定は
危険用に揃える」): the recall-wait 「射線の通る T1」 (recall_wait_teleport ``_t1_in_fire``) and the
Amberites' "can this shot hit it" (amberite_curse ``struck``) read line_of_fire.counting, the escape
count's reading (an unknown grid is a wall).  They now read line_of_fire ``danger``, the
damage estimate's (an awake monster does not see an unknown grid as a wall), as deep_teleport
``fire_p95`` does since 2026-11-15.  The escape count and the summon count keep line_of_fire.

Recorded: n1-a life-525's 49F boards while Recall counted down (tests/fixtures/n1a-525-death-1115,
the harness of test_n1a_525_recall_wait_teleport_1115_recorded: every board decided by the
restored policy's ``choose_key``, the recorded key posted).  On turn 12041184 the awake monster
index 38 has a line of fire only through grids the board does not know: line_of_fire.counting reads
it blocked, the danger reading open.  ``_t1_in_fire`` is observed by a pass-through spy on the
tier reading it asks (the hostiles it judged; the reading itself is the real one).

Recorded: n1-b life-410's Angband 80F board of decision #17762 (tests/fixtures/n1b-410-amberite-
1117.pkl.xz, the harness of test_n1b_410_amberite_curse_1117_recorded).  DECLARED CONSTRUCTED: the
grid (8,71) between the player (9,70) and the awake Brand (7,72) taken off the board (unknown), and
Brand shown by detection only (not in view): the count's reading stops at the unknown grid, the
danger reading does not, so a Rocket fired now may hit it.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot import amberite_curse, line_of_fire, threat_tiers
from hengbot.model import Position, parse_snapshot
import hengbot.recall_wait_teleport as recall_wait_teleport
from tests import test_destruction_use_1104_recorded as destruction_case
from tests import test_n1a_525_recall_wait_teleport_1115_recorded as recall_case
from tests import test_n1b_410_amberite_curse_1117_recorded as amberite_case

THROUGH_UNKNOWN_TURN = 12041184
THROUGH_UNKNOWN_INDEX = 38


class DangerLineOfFireTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.judged = {}
        cls.readings = {}
        real_t1_in_fire, real_assess = recall_wait_teleport._t1_in_fire, threat_tiers.assess

        def spy(policy, snapshot, hostiles):
            def assess(policy_, snapshot_, judged=None, **kwargs):
                cls.judged[snapshot.turn] = sorted(m.index for m in judged or ())
                return real_assess(policy_, snapshot_, judged, **kwargs)
            cls.readings[snapshot.turn] = {
                m.index: (line_of_fire.counting(policy, snapshot, m),
                          line_of_fire.danger(policy, snapshot, m), m.asleep)
                for m in hostiles}
            threat_tiers.assess = assess
            try:
                return real_t1_in_fire(policy, snapshot, hostiles)
            finally:
                threat_tiers.assess = real_assess

        recall_wait_teleport._t1_in_fire = spy
        try:
            recall_case.N1a525RecallWaitTeleport1115RecordedTest.setUpClass()
        finally:
            recall_wait_teleport._t1_in_fire = real_t1_in_fire

    @classmethod
    def tearDownClass(cls):
        recall_case.N1a525RecallWaitTeleport1115RecordedTest.tearDownClass()

    def test_the_monster_is_blocked_for_the_count_and_open_for_the_danger(self):
        in_fire, danger, asleep = self.readings[THROUGH_UNKNOWN_TURN][THROUGH_UNKNOWN_INDEX]
        self.assertFalse(asleep)
        self.assertFalse(in_fire)
        self.assertTrue(danger)

    def test_the_recall_wait_t1_judges_it_with_the_danger_reading(self):
        self.assertIn(THROUGH_UNKNOWN_INDEX, self.judged[THROUGH_UNKNOWN_TURN])

    def test_every_judged_set_is_the_danger_reading(self):
        for turn, judged in self.judged.items():
            danger = sorted(index for index, (_count, open_, _asleep)
                            in self.readings[turn].items() if open_)
            self.assertEqual(judged, danger, turn)



class AmberiteStrikeLineOfFireTest(unittest.TestCase):
    def test_a_shot_may_hit_an_amberite_beyond_an_unknown_grid(self):
        policy, _board = amberite_case.restored()
        raw = copy.deepcopy(amberite_case.CASE["board"])
        brand = next(m for m in raw["visible_monsters"] if m["race_id"] == amberite_case.BRAND)
        self.assertEqual((raw["player"]["y"], raw["player"]["x"], brand["y"], brand["x"]),
                         (9, 70, 7, 72))
        raw["grid_map"] = destruction_case.destroyed_map(raw["grid_map"], Position(8, 71), 0)
        raw["visible_monsters"].remove(brand)
        raw["detected_monsters"].append(dict(brand))
        board = parse_snapshot(raw, policy._monrace_knowledge)
        detected = next(m for m in board.detected_monsters if m.race_id == amberite_case.BRAND)
        self.assertIsNone(board.grid_at(Position(8, 71)))
        self.assertFalse(line_of_fire.counting(policy, board, detected))
        self.assertTrue(line_of_fire.danger(policy, board, detected))
        policy.last_reason = "ranged:magic-eater-device"
        self.assertEqual([m.index for m in amberite_curse.struck(policy, board, "mB39")],
                         [detected.index])


if __name__ == "__main__":
    unittest.main()
