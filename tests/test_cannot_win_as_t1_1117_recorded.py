"""The recall-wait T1 and the Q25 "T1 alone" read ``cannot_win`` (owner 2026-11-17 Q6).

Owner 2026-11-08 (question 1 of the n1-c life-171 report, verbatim 「勝てないと分かれば離脱」): a
tier the projection's cost cap left undecided whose no-supply damage lower bound reaches the HP is
T1 (threat_tiers ``cannot_win``; 皇帝『レイザーク』 on 城65階 read None with bounds (1345, 19270)
against HP 993).  The recall-wait 「射線の通る T1」 (recall_wait_teleport ``_t1_in_fire``) and Q25's
"a mover that alone is T1" (quest25_battle ``_shunned``) asked ``tier == T1`` only.  Owner
2026-11-17 (whole-bot maintainability review, question Q6, answer verbatim 「含める」): both read
``cannot_win`` (Q25 through threat_tiers ``alone_t1``, the one reader of "T1 alone").

Recorded boards:
 * RECALL: n1-a life-525's 49F board of decision 23999 while Recall counted down (a T1 group in the
   line of fire; tests/fixtures/n1a-525-death-1115, test_n1a_525_recall_wait_teleport_1115_recorded).
 * Q25: n1-a life-529's Q25 board of decision 36516 (the pack in view; tests/fixtures/n1a-529-q25-
   recall-wait-1117.json.gz, test_n1a_529_q25_recall_wait_1117_recorded's ``decide``).
DECLARED CONSTRUCTED: the tier reading replaced by the cost-capped one 11-08 names (``capped``:
tier None, skipped "cost", lower bound the HP) -- no capture holds such a reading on these boards.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from types import SimpleNamespace
import unittest
from unittest import mock

from hengbot import recall_wait_teleport, threat_tiers
from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle
from tests import test_n1a_525_recall_wait_teleport_1115_recorded as recall_case
from tests import test_n1a_529_q25_recall_wait_1117_recorded as q25_case

RECALL_SEQUENCE = 23999
Q25_SEQUENCE = 36516


def capped(hp):
    """The cost-capped reading whose lower bound reaches ``hp`` (owner 2026-11-08)."""
    return threat_tiers.Assessment(tier=None, skipped="cost", free_incoming_bounds=(hp, hp * 10))


class CannotWinAsT1Test(unittest.TestCase):
    def test_the_capped_reading_is_cannot_win_but_not_tier_t1(self):
        reading = capped(500)
        self.assertNotEqual(reading.tier, threat_tiers.T1)
        self.assertTrue(threat_tiers.cannot_win(reading, 500))


class RecallWaitCannotWinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        recall_case.N1a525RecallWaitTeleport1115RecordedTest.setUpClass()
        cls.case = recall_case.N1a525RecallWaitTeleport1115RecordedTest

    @classmethod
    def tearDownClass(cls):
        cls.case.tearDownClass()

    def test_a_capped_reading_in_the_line_of_fire_counts_as_t1(self):
        _recorded, board, *_rest = self.case.decided[RECALL_SEQUENCE]
        policy = self.case.policy
        hostiles = threat_tiers.engagement(policy, board)
        self.assertTrue(any(policy._monster_in_line_of_fire(board, m) for m in hostiles))
        with mock.patch.object(threat_tiers, "assess",
                               lambda *_args, **_kwargs: capped(board.player.hp)):
            self.assertTrue(recall_wait_teleport._t1_in_fire(policy, board, hostiles))


class Q25ShunnedCannotWinTest(unittest.TestCase):
    def shunned(self, tiered):
        def answer(policy, snapshot):
            ctx = SimpleNamespace(policy=policy, snapshot=snapshot,
                                  battle=SimpleNamespace(strong=()))
            ctx.hostiles = lambda: battle._Ctx.hostiles(ctx)
            with mock.patch.object(threat_tiers, "tiered", tiered):
                return [monster.index for monster in battle._shunned(ctx)], snapshot
        (shunned, snapshot), _reason, _board = q25_case.decide(Q25_SEQUENCE, answer=answer)
        return shunned, snapshot

    def test_a_mover_with_a_capped_reading_is_shunned(self):
        """Against the control (every mover read T3: only the packs are shunned), the capped
        reading adds movers that alone cannot be won against."""
        beatable, _snapshot = self.shunned(
            lambda *_args, **_kwargs: threat_tiers.Assessment(tier=threat_tiers.T3))
        shunned, snapshot = self.shunned(
            lambda _policy, snapshot, *_args, **_kwargs: capped(snapshot.player.hp))
        movers = {monster.index for monster in snapshot.visible_monsters
                  if monster.hostile and not monster.asleep}
        self.assertTrue((set(shunned) - set(beatable)) & movers)

if __name__ == "__main__":
    unittest.main()
