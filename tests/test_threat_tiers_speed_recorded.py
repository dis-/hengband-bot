"""Threat tiers plan step 8 (docs/threat-tiers-design.md 3.3, C-5; owner OQ-5): Speed in a T3 fight.

Owner 2026-11-07, OQ-5: in a fight the free attacks win (T3) only the Magic-Eater's absorbed haste of
11-04 (「取り込んだスピードが残10回以上なら、特にピンチでなくても戦闘時加速する」, >= 80% success)
remains; the 10-03 strong-fight Potion of Speed (``_strong_fight_speed_key``) does not fire there.

Acceptance: the recorded death lives (test_threat_tiers_leave_recorded's list) replayed with and
without the step: no board changes (the recorded strong-fight Speed boards, n1-c life-083's ogres
and n1-b life-279's cockroaches, are not T3 fights).

Boards (DECLARED CONSTRUCTED where a test edits them):
- the recorded troll board of test_melee_threat_p95_adjacency (闘トロル beside the HP 341 warrior,
  the 10-03 strong-fight Speed board: 3-turn p95 210 >= 170.5), the troll at 100 HP so that the
  free attacks win (T3).  Re-driven 2026-11-12 (t3-survival-1112 B: T3 is entered only at a free
  margin of the reserve; at 150 HP the margin is 37 against 79, read T2 and left);
- n1-c life-083's beetle board (ブラウン・キラービートル), its health band "wounded" (T3 for the
  absorbed Magic Missile) and the absorbed Speed listed at 10 charges (as
  test_me_speed_fight_1104_recorded shows it).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle
from hengbot import threat_tiers
from hengbot.cli import _PolicyObserverScope
from hengbot.model import SV_POTION_SPEED, parse_snapshot
from tests import test_melee_threat_p95_adjacency as troll_board
from tests import test_threat_tiers_supply_fight_recorded as supply

ME_HASTE = ("mAw", "me-power:fight-unhasted:speed")
STRONG = "item:strong-fight-speed"


def assessed(policy, board):
    with _PolicyObserverScope(policy):
        return threat_tiers.assess(policy, board, policy._strategic_hostiles(board))


class StrongFightSpeedInT3RecordedTest(troll_board.RecordedTrollBoardTest):
    """The recorded troll board (tests of the parent class are not re-run here)."""

    def board(self, troll_hp):
        policy, snapshot = self._fresh(troll_board.TROLL_DECISION)
        troll = self._troll(snapshot)
        weaker = replace(troll, hp=troll_hp)
        snapshot = replace(snapshot, visible_monsters=[
            weaker if monster.index == troll.index else monster
            for monster in snapshot.visible_monsters])
        return policy, snapshot

    def test_no_potion_of_speed_in_a_t3_strong_fight(self):
        policy, snapshot = self.board(100)
        hostiles = policy._strategic_hostiles(snapshot)
        self.assertEqual(assessed(policy, snapshot).tier, threat_tiers.T3)
        self.assertGreaterEqual(policy._corrected_predicted_damage(snapshot, hostiles, 3, observed_loss=0),
                                snapshot.player.hp * 0.5)  # a strong fight (10-03)
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("6", "melee"))
        # Before step 8 the 10-03 rung drank the potion on this board.
        policy, snapshot = self.board(100)
        with patch.object(threat_tiers, "tier_of", return_value=None):
            key = policy.choose_key(snapshot)
        speed = policy._find_exact_potion(snapshot, SV_POTION_SPEED)
        self.assertEqual((key, policy.last_reason), ("q" + speed.slot, STRONG))

    def test_a_strong_fight_that_is_not_t3_still_drinks(self):
        # DECLARED CONSTRUCTED tier: the same board taken as a selected T2; the 10-03 dose stays.
        policy, snapshot = self.board(100)
        with patch.object(threat_tiers, "tier_of", return_value=threat_tiers.T2):
            key = policy.choose_key(snapshot)
        speed = policy._find_exact_potion(snapshot, SV_POTION_SPEED)
        self.assertEqual((key, policy.last_reason), ("q" + speed.slot, STRONG))


for _name in [name for name in vars(troll_board.RecordedTrollBoardTest) if name.startswith("test_")]:
    setattr(StrongFightSpeedInT3RecordedTest, _name, None)


class AbsorbedHasteInT3RecordedTest(unittest.TestCase):
    def test_the_absorbed_haste_still_fires_in_a_t3_fight(self):
        from tests import test_me_speed_fight_1104_recorded as fight
        policy, raw = supply.beetle_board()
        for monster in raw["visible_monsters"]:
            monster["health"] = "wounded"
        fight.show(policy, raw, 10, 20)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(assessed(policy, board).tier, threat_tiers.T3)
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason), ME_HASTE)


if __name__ == "__main__":
    unittest.main()
