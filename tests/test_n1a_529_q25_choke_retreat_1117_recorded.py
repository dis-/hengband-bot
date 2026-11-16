"""Quest 25 phase 2 on n1-a life-529 (2026-11-17 00:10): the walk back to a choke two steps away, recorded.

The chain (bot-decisions of ~/hengbot-soak/n1-a/life-529/captures/20261117-001053-exit-no-marker,
build bot-945ab02d2; battle phase 2, Ipsissimus, rallying):

 * From the choke [7,1] the walk to the pen's sight went by [6,1] to the look-out [5,2]
   (36482-36483).  At 36485 and 36486 a summons stood beside the player; the chokes (cells no
   summons reaches) nearest were [7,1] by [6,1] and [3,1] by the door [4,1], each two steps, the
   way free; ``_choke_step_back`` only stepped to a choke beside the player, so the plan fought
   on [5,2] (``quest-strategy:melee``) until the pack closed round it and it died at 36547.

The rule (owner 2026-11-17, 「隘路が2歩以上先の時はどうしますか？」 → 「空いている道で一番近い隘路まで
下がる」): with one beside, the step along a free way toward the nearest choke (among equals the
phase's own stand [7,1]); with the way closed, the fight where the player stands.

Recorded: tests/fixtures/n1a-529-q25-recall-wait-1117.json.gz (its module note), decided by a fresh
policy through the public ``choose_key`` (tests/test_n1a_529_q25_recall_wait_1117_recorded
``decide``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle
from tests import test_n1a_529_q25_recall_wait_1117_recorded as recorded

LOOKOUT = (5, 2)
FREE_WAY = (36485, 36486)
CLOSED_WAY = (36489, 36490)   # [6,1] and [6,2] taken (36489), [7,1] too (36490)


def _cells(board):
    return {(monster["y"], monster["x"]) for monster in board["visible_monsters"]}


class TheRecordingTest(unittest.TestCase):

    def test_fought_on_the_lookout_with_the_way_free(self):
        for sequence in FREE_WAY:
            index = recorded._index(sequence)
            board, row = recorded.CASE["second"]["boards"][index], recorded.CASE["second"]["recorded"][index]
            self.assertEqual((board["player"]["y"], board["player"]["x"]), LOOKOUT)
            self.assertEqual(row["reason"], "quest-strategy:melee")
            self.assertTrue(_cells(board).isdisjoint({(6, 1), (7, 1)}), sequence)
        for sequence in CLOSED_WAY:
            board = recorded.CASE["second"]["boards"][recorded._index(sequence)]
            self.assertTrue({(6, 1), (6, 2)} <= _cells(board), sequence)


class ChokeRetreatTest(unittest.TestCase):

    def test_with_the_way_free_the_step_toward_7_1_by_6_1(self):
        for sequence in FREE_WAY:
            key, reason, snapshot = recorded.decide(sequence)
            self.assertEqual((snapshot.player.position.y, snapshot.player.position.x), LOOKOUT)
            self.assertEqual((key, reason), ("1", battle.CHOKE_BACK_REASON), sequence)   # to [6,1]

    def test_with_the_way_closed_the_fight_in_place(self):
        for sequence in CLOSED_WAY:
            key, reason, _snapshot = recorded.decide(sequence)
            self.assertNotEqual(reason, battle.CHOKE_BACK_REASON, sequence)
            self.assertEqual(reason, "quest-strategy:melee", (sequence, key))
            self.assertIn(key, recorded.DIRECTIONS, sequence)


if __name__ == "__main__":
    unittest.main()
