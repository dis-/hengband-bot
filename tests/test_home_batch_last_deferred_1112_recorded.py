"""A Home batch whose last entry is deferred leaves no bare candidate latch (2026-11-12).

Recorded: n1-a life-508's town visit (tests/fixtures/town-retired-burst-1110/n1a-508), rows 50-54:
the catalogue shortage binds a Home batch (Treasure Detection, the dwarven shovel, the pickaxe, a
Potion of Speed), two atomic takes run, and on row 54 the town item processing finds the next
entries not carried and defers them (``town-item-processing-missing-pending``).  The live row 54
is ``5`` shop:travel:await-entry.

DECLARED CONSTRUCTED: the Home's two Potions of Heroism join that batch as its last entry, as the
Heroism carry (owner 2026-11-11) binds them.  The deferral then empties the batch on an uncarried
stack, and ``_home_candidate_waiting = not batch`` left the latch set with no owner; the Home
entrance read it as an observed operation that cannot be composed, marked Home attempted and
stepped off (``town:entrance-step-off:shop:observed-operation-uncomposable``).  The latch is now
released when no owner holds it (``_release_stale_home_candidate_waiting``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from unittest import mock

from hengbot.model import STORE_HOME, TVAL_POTION
from hengbot.policy import HengbotPolicy
from tests import test_town_retired_burst_1110_recorded as burst

SV_HEROISM = 32
LAST_ROW = 54


def _heroism_joins_the_batch(original):
    def member(self, snapshot, item, strategy=None):
        if item.tval == TVAL_POTION and item.sval == SV_HEROISM:
            return True
        return original(self, snapshot, item, strategy)
    return member


class HomeBatchLastDeferredTest(unittest.TestCase):
    def load(self, stop):
        """The n1-a stop's arrival policy, journal and boards, by that module's loader."""
        loader = burst.TownRetiredBurst1110RecordedTest("test_n1a_home_scan_runs_inside_the_router_s_home_visit")
        loader.setUp()
        self.addCleanup(loader.doCleanups)
        return loader.load(stop)

    def replay_to(self, last, *, constructed):
        member = _heroism_joins_the_batch(HengbotPolicy._home_procurement_batch_member)
        patch = (mock.patch.object(HengbotPolicy, "_home_procurement_batch_member", member)
                 if constructed else mock.patch.object(HengbotPolicy, "_home_procurement_batch_member",
                                                       HengbotPolicy._home_procurement_batch_member))
        with patch:
            policy, recorded, steps = self.load("n1a-508")
            batches = []
            for index, (row, supply) in enumerate(steps[:last + 1]):
                key = policy.choose_key(supply())
                batches.append([signature[0] for signature in policy._home_pending_batch])
                if index < last:
                    self.assertEqual((key, policy.last_reason),
                                     (recorded[row["row"]]["key"], recorded[row["row"]]["reason"]), index)
                    policy.confirm_key_posted(key)
            return policy, recorded, key, batches

    def test_the_recorded_batch_walks_on_to_home(self):
        policy, recorded, key, batches = self.replay_to(LAST_ROW, constructed=False)
        self.assertEqual((key, policy.last_reason), ("5", "shop:travel:await-entry"))
        # Owner 2026-11-12 「自宅にあれば先に取り出す」: without a lasting fear resistance the
        # Home's two Potions of Heroism join the recorded catalogue-shortage batch (row 50).
        self.assertTrue(any("ヒーロー" in name for name in batches[50]), batches[50])
        self.assertFalse(policy._home_candidate_waiting)

    def test_a_deferred_last_entry_leaves_no_latch_and_no_step_off(self):
        policy, recorded, key, batches = self.replay_to(LAST_ROW, constructed=True)
        self.assertTrue(any(any("ヒーロー" in name for name in batch) for batch in batches[50:54]))
        self.assertEqual((key, policy.last_reason), ("5", "shop:travel:await-entry"))
        self.assertFalse(policy._home_candidate_waiting)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)


if __name__ == "__main__":
    unittest.main()
