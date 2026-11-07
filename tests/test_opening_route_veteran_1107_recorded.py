"""A town hostile beaten by the Magic-Eater's ranged answer never stops the opening route.

Recorded n1-b life-336, Lv7 Magic-Eater walking to the Q1 entrance (owner 2026-10-26: Q34
-> mining kit -> Q1), 2026-11-07 09:05:49-09:05:51: its Magic Missile ('mBp')
answered a 戦傷兵士 (Battle-scarred veteran, race 18) beside it, the veteran fled in fear
to 2 cells, HP 111 -> 84, and the next board stopped as quest:blocked:opening-route
(recovery-hostile-unreachable); every board after the restart stopped the same way.
``_town_monster_unbeatable`` projected melee alone (the Q34 halberd, 0.3 an action: more
than UNIQUE_COMBAT_MAX_ATTACKS attacks), so the hunt refused the veteran the missile had
just routed, and the recovery branch stopped with nothing adjacent.

Visit: tests/fixtures/opening-route-336-1107 (tests/extract_detected_hunt_1107_fixtures.py),
the town arrival to the stop, every decision through choose_key.
DECLARED CONSTRUCTED: the last test makes the hunt refuse the veteran, to reach the
recovery branch's own answer.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from pathlib import Path
import unittest

from test_me_stops_1103_recorded import Visit

FIXTURE = Path(__file__).with_name("fixtures") / "opening-route-336-1107"
VETERAN = 18
STOP = "quest:blocked:opening-route"


class OpeningRouteVeteranRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.visit = Visit(FIXTURE.resolve())
        policy = cls.visit.policy
        policy._home_disposal.history_path = cls.visit.scratch / "home-history.jsonc"
        rows = list(cls.visit.rows)
        for _recorded, supply in rows[:-1]:
            cls.visit.post(policy.choose_key(supply()))
        cls.recorded, supply = rows[-1]
        cls.board = supply()
        cls.arrived = policy

    @classmethod
    def tearDownClass(cls):
        cls.visit.close()

    def setUp(self):
        self.policy = copy.deepcopy(self.arrived)

    def veteran(self):
        return next(m for m in self.board.visible_monsters if m.race_id == VETERAN)

    def test_the_recorded_board(self):
        self.assertEqual(self.recorded["reason"], STOP)
        veteran = self.veteran()
        self.assertEqual((veteran.distance, veteran.fearful), (2, True))
        self.assertLess(self.board.player.hp, self.board.player.max_hp)

    def test_the_ranged_answer_beats_the_veteran(self):
        self.assertFalse(self.policy._town_monster_unbeatable(self.board, self.veteran()))

    def test_the_route_goes_on_after_the_fleeing_veteran(self):
        key = self.policy.choose_key(self.board)
        self.assertNotEqual(self.policy.last_reason, STOP)
        self.assertIsNone(getattr(self.policy, "_opening_q1_failure", None))
        self.assertTrue(key)

    def test_a_hostile_the_hunt_refuses_does_not_stop_the_route(self):
        self.policy._town_monster_unbeatable = lambda snapshot, monster: True  # DECLARED
        key = self.policy.choose_key(self.board)
        self.assertNotEqual(self.policy.last_reason, STOP)
        self.assertIsNone(getattr(self.policy, "_opening_q1_failure", None))
        self.assertTrue(key)


if __name__ == "__main__":
    unittest.main()
