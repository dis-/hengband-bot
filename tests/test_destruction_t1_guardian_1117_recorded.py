"""*Destruction* erases a floor guardian that is T1 alone (owner 2026-11-17 Q3).

Owner 2026-11-17 (whole-bot maintainability review, question Q3, answer verbatim 「守護者が T1
なら守護者ごと消してよい」): destruction_use refused every use with the floor's guardian within
``WORST_RADIUS`` (17) -- the 11-04 words did not cover it -- and the approaches and the 50F+
concerned set left it out (they named its race).  The 11-04 reading stays for a guardian the
character can beat; a guardian that is T1 alone (threat_tiers ``alone_t1`` from contact) is now
used on with the circle (deleted, its conquest and reward given up), and destruction_use ``spares``
is the one reader of the set the approaches leave out.

Recorded: the n1-c life-216 62F landing board (tests/fixtures/route-veto-sealed-20261117.json.gz,
turn 3897141), decided by a fresh policy's ``choose_key`` (the harness of
test_sleeping_t1_destruction_1117_recorded).  DECLARED RECONSTRUCTED (as that module): the absorbed
*Destruction* list row (22 charges at 95%).  DECLARED CONSTRUCTED: the visible スリング・ハーフリング
(index 101, 9 cells off) made a sleeping パワー・ワイアーム (race 847, T1 alone on this board), and the
floor made the dungeon's last with that race its guardian (DungeonInfo); for the beatable guardian,
the race of the halflings (539) made the guardian instead.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import deep_teleport, destruction_use, me_capability, threat_tiers
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.model import SV_STAFF_DESTRUCTION, game_distance, parse_snapshot
from tests import test_sleeping_t1_destruction_1117_recorded as sleeping_case
from tests.support.recorded import _policy

HALFLING = 539


class T1GuardianDestructionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sleeping_case.SleepingT1DestructionTest.setUpClass()
        cls.landing = sleeping_case.SleepingT1DestructionTest.landing
        cls.monrace = sleeping_case.SleepingT1DestructionTest.monrace

    def decide(self, guardian):
        raw = copy.deepcopy(self.landing)
        for monster in raw["visible_monsters"]:
            if monster["index"] == sleeping_case.IN_VIEW_INDEX:
                monster["race_id"] = sleeping_case.POWER_WYRM
                monster["asleep"] = True
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        board = parse_snapshot(raw, self.monrace)
        policy.prime(board)
        floor = raw["floor"]
        policy._dungeon_knowledge[floor["dungeon_id"]] = DungeonInfo(
            floor["dungeon_id"], "", 1, floor["level"], 1, guardian_id=guardian)
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (board.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        board = policy.with_known_skill_exp(board)
        key = policy.choose_key(board)
        wyrm = next(m for m in board.visible_monsters if m.race_id == sleeping_case.POWER_WYRM)
        return key, policy.last_reason, policy, board, wyrm

    def test_a_t1_guardian_in_the_circle_is_used_on(self):
        key, reason, policy, board, wyrm = self.decide(sleeping_case.POWER_WYRM)
        # Before Q3 the guardian in the circle refused the use and the leave read Recall ("rf").
        self.assertEqual(key, "mA3")
        self.assertTrue(reason.startswith(destruction_use.REASON), reason)
        self.assertEqual(destruction_use._guardian_race(policy, board), sleeping_case.POWER_WYRM)
        self.assertLessEqual(game_distance(board.player.position, wyrm.position),
                             destruction_use.WORST_RADIUS)
        self.assertTrue(threat_tiers.alone_t1(policy, board, wyrm, contact=True))
        self.assertFalse(destruction_use.spares(policy, board, wyrm))
        self.assertFalse(destruction_use._spared_in_circle(policy, board, None))

    def test_the_t1_guardian_is_an_approach_target_and_concerned(self):
        _key, _reason, policy, board, wyrm = self.decide(sleeping_case.POWER_WYRM)
        strong = threat_tiers._sensed_strong(policy, board)[1]
        self.assertIn(wyrm, strong)
        self.assertNotIn(wyrm, [m for m in strong if destruction_use.spares(policy, board, m)])

    def test_a_beatable_guardian_in_the_circle_still_refuses_the_use(self):
        """The 11-04 reading for a guardian the character beats: the halflings' race."""
        key, reason, policy, board, _wyrm = self.decide(HALFLING)
        halfling = next(m for m in board.detected_monsters if m.race_id == HALFLING
                        and game_distance(board.player.position, m.position)
                        <= destruction_use.WORST_RADIUS)
        self.assertFalse(threat_tiers.alone_t1(policy, board, halfling, contact=True))
        self.assertTrue(destruction_use.spares(policy, board, halfling))
        self.assertTrue(destruction_use._spared_in_circle(policy, board, None))
        self.assertFalse(reason.startswith(destruction_use.REASON), reason)
        self.assertNotIn(halfling, deep_teleport.concerned(policy, board))


if __name__ == "__main__":
    unittest.main()
