"""#95 slices 1b-3a and 1b-2: {good} plain gear and the one-time Home junk sweep.

Owner Q-A (2026-10-22, 「壊す」): identified {good} non-ego gear worse than the
selected loadout is plain-gear.  Design chapter 3 (supervisor 2026-10-22):
on a Home page the town plan opened anyway, with no Home work left, the
existing full-Home relief takes one junk ware (leave, then the entrance's
atomic entry-take-exit) and destroys it with reason home:junk-sweep:<class>;
at most HOME_BATCH_RESERVED_SLOTS wares per town stay, no retry batch, no
release of the Home visit bound.

Recorded board R1: tests/fixtures/teleport-items-safe-c4a-20261021.jsonl.gz
through test_junk_plain_gear_recorded (rows 0-6, its DECLARED CONSTRUCTED
calibration).  Row 3 is the recorded Home page, row 6 the outside board at
the Home entrance (123, 45).

DECLARED CONSTRUCTED: the settled atomic deposit of row 6 (its pending
state cleared and the anti-teleport amulet gone from the pack), the Rod of
Illumination left out of the pack (the recorded pack is 1646 of 1650 weight,
so no Home ware fits; the weight control keeps the recorded pack), the taken
cloak in the pack after the take, the per-stay counts, the Home approach
failure count and the unreachable entrance.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import copy
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

import test_junk_plain_gear_recorded as plain
from hengbot.claim_goal_typing import GOAL_OBSERVE, goal_typing
from hengbot.claim_ladder import rung_of
from hengbot.model import STORE_HOME
from hengbot.policy_constants import HOME_BATCH_RESERVED_SLOTS


HOME_PAGE_ROW = 3
ENTRANCE_ROW = 6
CLOAK = "クローク [1,-1]"


class JunkHomeSweepRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plain.JunkPlainGearRecordedTest.setUpClass()
        cls.recorded = plain.JunkPlainGearRecordedTest

    @classmethod
    def tearDownClass(cls):
        plain.JunkPlainGearRecordedTest.tearDownClass()

    def _policy(self):
        policy = copy.deepcopy(self.recorded.policy)
        # DECLARED CONSTRUCTED: row 6's atomic deposit has settled.
        policy._home_atomic_deposit_pending = None
        policy._store_visit = None
        return policy

    def _row(self, index, *, drop=("反テレポート", "イルミネーション")):
        row = json.loads(self.recorded.lines[index])
        row["inventory"] = [item for item in row["inventory"]
                            if not any(name in item.get("name", "") for name in drop)]
        return json.dumps(row, ensure_ascii=False)

    def _decide(self, policy, index, **kwargs):
        board = self.recorded._feed(policy, self._row(index, **kwargs))
        return board, policy.choose_key(board)

    def test_recorded_home_plain_gear_classes(self):
        # Q-A: the recorded Home board's identified {good} plain gear.
        policy = copy.deepcopy(self.recorded.policy)
        board = self.recorded.board
        names = {item.name: policy._junk_class(board, item)
                 for item in policy._home_knowledge_items}
        self.assertEqual(names["汚れたボロ服 [1,+4]"], "plain-gear")
        self.assertEqual(names["革製ラージ・シールド [6,+4]"], "plain-gear")
        self.assertIsNone(names["金属製ラージ・シールド [8,+2]"])
        self.assertIsNone(names["鋼鉄ヘルメット [6,+5]"])

    def test_sweep_takes_one_ware_at_the_entrance(self):
        policy = self._policy()
        policy._town_visit_ledger.approach_fails[STORE_HOME] = 1
        _board, key = self._decide(policy, HOME_PAGE_ROW)
        relief = policy._home_full_relief
        self.assertEqual(key, "\x1b")
        self.assertTrue(relief["sweep"])
        self.assertEqual(relief["sweep_class"], "plain-gear")
        self.assertEqual(policy._home_junk_sweep_count,
                         (policy._town_visit_epoch, 1))
        _board, key = self._decide(policy, ENTRANCE_ROW)
        self.assertEqual(policy.last_reason,
                         "home-errand:atomic-withdraw:full-home-discard")
        self.assertEqual(policy._home_full_relief["sale"][0], (CLOAK, 35, 1))
        self.assertTrue(key.startswith("5"))
        # The sweep keeps the Home visit bound (no release_visit_bound).
        self.assertEqual(policy._town_visit_ledger.approach_fails[STORE_HOME], 1)

    def test_sweep_destroys_with_its_reason_and_ends(self):
        policy = self._policy()
        self._decide(policy, HOME_PAGE_ROW)
        self._decide(policy, ENTRANCE_ROW)
        cloak = next(item for item in policy._home_knowledge_items
                     if item.name == CLOAK)
        outside = self.recorded._feed(policy, self._row(ENTRANCE_ROW))
        # DECLARED CONSTRUCTED: the take settled; the cloak is carried.
        policy._home_atomic_withdraw_pending = None
        policy._store_visit = None
        carried = replace(outside, inventory=(*outside.inventory,
                                              replace(cloak, slot="l")))
        reasons = []
        for _ in range(3):
            policy._decision_sequence += 1
            policy.choose_key(carried)
            reasons.append(policy.last_reason)
        self.assertIn("home:junk-sweep:plain-gear", reasons)
        self.assertNotIn("home:full-destroy-surplus", reasons)
        self.assertNotIn("home:full-queue-surplus-withdraw", reasons)
        policy._decision_sequence += 1
        policy.choose_key(outside)
        self.assertIsNone(policy._home_full_relief)
        self.assertIsNone(policy._home_full_retry_deposits)
        self.assertEqual(rung_of("home-visit", "home:junk-sweep:plain-gear").producer,
                         "_home_full_relief_key")
        self.assertEqual(goal_typing("home-visit", "home:junk-sweep:plain-gear").kind,
                         GOAL_OBSERVE)

    def test_per_stay_limit(self):
        policy = self._policy()
        policy._home_junk_sweep_count = (policy._town_visit_epoch,
                                         HOME_BATCH_RESERVED_SLOTS)
        self._decide(policy, HOME_PAGE_ROW)
        self.assertIsNone(policy._home_full_relief)
        self.assertEqual(policy.last_reason, "home:route-claim-unfulfilled")
        # A new town stay starts from zero.
        policy = self._policy()
        policy._home_junk_sweep_count = (policy._town_visit_epoch - 1,
                                         HOME_BATCH_RESERVED_SLOTS)
        self._decide(policy, HOME_PAGE_ROW)
        self.assertTrue(policy._home_full_relief["sweep"])

    def test_recorded_pack_weight_keeps_every_ware(self):
        # The recorded pack (1646 of 1650) cannot carry any junk ware.
        policy = self._policy()
        self._decide(policy, HOME_PAGE_ROW, drop=("反テレポート",))
        self.assertIsNone(policy._home_full_relief)
        self.assertEqual(policy._home_junk_sweep_count,
                         (policy._town_visit_epoch, HOME_BATCH_RESERVED_SLOTS))

    def test_no_sweep_step_outside_a_home_visit(self):
        policy = self._policy()
        board = self.recorded._feed(policy, self._row(ENTRANCE_ROW))
        self.assertFalse(policy._begin_home_junk_sweep(board))
        self.assertIsNone(policy._home_full_relief)
        self.assertIsNone(getattr(policy, "_home_junk_sweep_count", None))

    def test_unreachable_entrance_ends_the_sweep(self):
        policy = self._policy()
        self._decide(policy, HOME_PAGE_ROW)
        with patch.object(policy, "_shopping_approach_step", return_value=None):
            self._decide(policy, ENTRANCE_ROW)
        self.assertIsNone(policy._home_full_relief)
        self.assertNotEqual(policy._town_blocked_reason,
                            "home-full-surplus-store-unreachable")
        self.assertEqual(policy._home_junk_sweep_count,
                         (policy._town_visit_epoch, HOME_BATCH_RESERVED_SLOTS))

    def test_skipped_ware_ends_the_sweep(self):
        policy = self._policy()
        self._decide(policy, HOME_PAGE_ROW)
        self._decide(policy, ENTRANCE_ROW)
        policy._home_full_skip_key("surplus-withdraw-failed")
        self.assertIsNone(policy._home_full_relief)
        self.assertIsNone(policy._home_pending_item)
        self.assertEqual(policy._home_junk_sweep_count,
                         (policy._town_visit_epoch, HOME_BATCH_RESERVED_SLOTS))


if __name__ == "__main__":
    unittest.main()
