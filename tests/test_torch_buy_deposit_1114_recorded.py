"""A burnt-out torch no longer splits the quest torch carry (torch-buy-deposit-1114).

n1-b life-396 (Lv8 Magic-Eater, a Brass Lantern worn, a Long Sword, no launcher) stopped on
2026-11-14 11:05 with town:blocked:stage-deadline:home.  The visit's carry plan (Q14's
required_force merged with the opening's, ``throwing_items.lit_torch`` 20) bought twenty
torches at the General Store (row 62 ``pi20``) beside a burnt-out torch already in the pack
(slot i, 松明(0ターンの寿命), before the new stack j in pack order).  The two sides of that one
carry then disagreed:

* the count (``_quest_named_item_count``, read by ``_torch_carry_requirement`` for the
  purchase and the Home take) counts torches with light left: 20 of 20;
* the item match (``_quest_carry_target_for_item``) matched every torch, so the retention's
  ``carry-strategy:lit_torch`` allocation (policy_home ``_retention_reservation_baseline_detail``,
  in pack order) gave the burnt-out torch one of the twenty and kept nineteen of stack j.

The twentieth was surplus (``reserved_stack_surplus``): Home took one ('dj1'), the count then
read 19 and the General Store sold one more ('pi1'), 41 buys and 47 deposits until the stage
deadline.  In the game only a torch with fuel is a lit torch (specific-object/torch.cpp
is_active_torch, read by torch_flags and throw-execution.cpp), so the carry's match and its
count now read that one predicate (``_is_lit_torch``): the burnt-out torch is no carry item,
stack j keeps all twenty, and the visit goes on to its errand plan's next stop, the Magic shop
sale (store 5, organization-sale / device-sale), which the recorded visit only reached at row
126 after the loop.

Owner 2026-11-15 「Q1 の後は松明20本をやめる」: Q1 completed, its twenty torches ride on no later
carry; rows 0-61 are compared with the record, 62-64 post the recorded keys, and the predicate
is pinned on Q1's own force.

Recorded: the town-arrival checkpoint, its first 67 journal rows and the arrival's character
calibration (tests/extract_torch_buy_deposit_1114_fixture.py), decided through the public
choose_key.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import adopt_calibration, decisions, restore
from tests.support import recorded as harness

FIXTURE = Path(__file__).with_name("fixtures") / "torch-buy-deposit-1114"
BUY_ROW = 62          # 'pi20' at the General Store: twenty torches bought
OUTSIDE_ROW = 65      # the first board outside the General Store (recorded: travel to Home)
HOME_ROW = 66         # the recorded Home page (recorded: 'dj1', one torch deposited)
LIT_TORCHES = 20
HOME_TRAVEL = "\x1b`n(."


class TorchBuyDeposit1114RecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.journal = lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes())

    def load(self):
        scratch_dir = TemporaryDirectory()
        self.addCleanup(scratch_dir.cleanup)
        root = Path(scratch_dir.name)
        visit, scratch = root / "town-arrival", root / "scratch"
        visit.mkdir()
        scratch.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(self.journal))
        policy = restore(visit, scratch)
        policy._home_disposal.history_path = scratch / "home-history.jsonc"
        adopt_calibration(policy, FIXTURE / "calibration.json", scratch)
        return policy, list(decisions(policy, visit, scratch))

    def raw(self, row):
        entry = json.loads(self.journal.decode("utf-8").splitlines()[row])
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def replay_to_outside(self):
        """Rows 0-61 replay as recorded, 62-64 post the record; row 65's board is returned."""
        policy, rows = self.load()
        for recorded, supply in rows[:OUTSIDE_ROW]:
            key = policy.choose_key(supply())
            if recorded["row"] < BUY_ROW:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                                 recorded["row"])
            # Owner 2026-11-15 「Q1 の後は松明20本をやめる」: Q1 done, the chooser no longer buys
            # Q1's twenty (row 62); from there the recorded keys are posted (DECLARED CONSTRUCTED).
            policy.confirm_key_posted(recorded["key"])
        self.assertEqual(rows[BUY_ROW][0]["key"], "pi20\r\r")
        # The recorded loop: to Home with the twenty, one torch deposited.
        self.assertEqual((rows[OUTSIDE_ROW][0]["key"], rows[HOME_ROW][0]["key"]),
                         (HOME_TRAVEL, "dj1\r\x1b"))
        return policy, rows[OUTSIDE_ROW][1]()

    def test_the_whole_bought_stack_is_the_carry(self):
        policy, board = self.replay_to_outside()
        burnt = next(item for item in board.inventory if item.slot == "i")
        bought = next(item for item in board.inventory if item.slot == "j")
        self.assertEqual((burnt.is_torch, burnt.fuel, bought.is_torch, bought.count),
                         (True, 0, True, LIT_TORCHES))
        # The carry's match and count on Q1's own force (class 16: twenty lit torches).  Owner
        # 2026-11-15 「Q1 の後は松明20本をやめる」: Q1 done, that force no longer rides on Q14's
        # carry, so the merged-carry retention of the twenty is dropped from this pin.
        q1 = policy.approved_quest_strategy(1)
        force = policy._strategy_force_for_snapshot(board, q1)
        self.assertEqual(force["throwing_items"]["lit_torch"], LIT_TORCHES)
        self.assertIsNone(
            policy._carry_procurement_strategy(board).required_force
            .get("throwing_items", {}).get("lit_torch"))
        # One reading of the carry: the item match and the count agree on the lit torches.
        self.assertIsNone(policy._quest_carry_target_for_item(board, burnt, force))
        self.assertEqual(policy._quest_carry_target_for_item(board, bought, force),
                         ("lit_torch", LIT_TORCHES, LIT_TORCHES))

    # Dropped: test_the_visit_goes_on_to_the_magic_shop_through_the_executor.  It went on with
    # the twenty bought for Q1's carry merged below Lv10, which owner 2026-11-15
    # 「Q1 の後は松明20本をやめる」 removed (the chooser no longer buys them, row 62).


if __name__ == "__main__":
    unittest.main()
