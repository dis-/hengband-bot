"""The Magic-Eater's Home devices go by its device table (owner 2026-11-19).

Owner (verbatim): 「魔法道具を自宅にため込んでいる。魔道具術師の処理ルールに従って処分」.  n1-b
life-411 and n1-c life-217 kept every identified ``absorb_now`` device at Home: item_use_route
counts the absorption as a use, me_device_policy.absorb_candidate absorbs only on a dungeon floor,
and nothing took a Home copy out.  Now item_fate.fate (the one gate) reads the table for a Home
device (me_device_policy.home_fate):

* ``absorb``: a copy the table absorbs below the cap of 99 (``absorb_now`` charged and usable,
  or ``charge_first``) is taken out (policy_home ``_bind_home_absorb_device_withdrawal``) and
  absorbed in town (magic_eater.absorb_key, me_device_policy.town_absorb_candidate); the carried
  copy is retained until then (``me-device:absorb-in-town``);
* ``destroy``: the Staff of *Destruction* at the cap (owner 2026-11-16 「取り込み回数99なら杖を
  拾わず壊す」);
* otherwise the table's other answers stand: a ``never`` kind no rule uses is sold
  (item_use_route), the zombie's Wand of Wonder food stays; an empty ``absorb_now`` copy is
  absorbed when its kind is already absorbed (tests/test_me_empty_absorb_1119_recorded).

The Home ledger counts the absorbed stacks as leaving the Home.

Recorded: the town arrivals of 2026-11-19, n1-b life-411 (tests/fixtures/quest32-one-turn-kill-1119/
n1b-411, a 239-stack Home with 16 device stacks) and n1-c life-217 (tests/fixtures/
n1c-217-angband-hold-1119, a 204-stack Home with 14 device stacks), both zombie Magic-Eaters with
their displayed absorbed lists.

On the decision path (choose_key) the cap tidy begins on n1-b's arrival with 39 stacks to shed
and takes a clearly dominated ware first.

DECLARED CONSTRUCTED: the arrival board at full HP for the cap tidy; the taken device added to the pack (the game's take); a Staff of
*Destruction* on n1-b's shelf with the absorbed count at 99 or below it (me_capability.count
patched).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot import home_ledger, item_fate, magic_eater, me_capability, me_device_policy
from support.town_arrival_fixture import load
from test_n1a_531_overweight_1119_recorded import post

FIXTURES = Path(__file__).with_name("fixtures")
DEVICE_TVALS = (55, 65, 66)


def recorded(path):
    scratch = TemporaryDirectory()
    policy, _journal, steps = load(path, Path(scratch.name))
    return scratch, policy, steps[0][1]()


class MeHomeDevices1119RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n1b = recorded(FIXTURES / "quest32-one-turn-kill-1119" / "n1b-411")
        cls.n1c = recorded(FIXTURES / "n1c-217-angband-hold-1119")

    @classmethod
    def tearDownClass(cls):
        cls.n1b[0].cleanup()
        cls.n1c[0].cleanup()

    @staticmethod
    def device_fates(policy, board):
        return [(item.name, item_fate.fate(policy, board, item, item_fate.SHELF))
                for item in policy._home_knowledge_items if item.tval in DEVICE_TVALS]

    def test_n1b_home_devices(self):
        _, policy, board = self.n1b
        fates = self.device_fates(policy, board)
        self.assertEqual(Counter(fate for _, fate in fates),
                         Counter({item_fate.ABSORB: 15, item_fate.HOME: 1}))
        kept = sorted(name for name, fate in fates if fate == item_fate.HOME)
        # The zombie's food (the Wand of Wonder staple, never absorbed).
        self.assertEqual(kept, ["謎の魔法棒 (23回分) {@3}"])
        summary = home_ledger.summary(policy, board)
        self.assertEqual((summary["kept"], summary["absorb"], summary["shed"]["short"]),
                         (207, 15, 7))

    def test_n1c_home_devices(self):
        _, policy, board = self.n1c
        fates = dict(self.device_fates(policy, board))
        self.assertEqual(Counter(fates.values()),
                         Counter({item_fate.ABSORB: 13, item_fate.SELL: 1}))
        self.assertEqual(fates["懐柔の魔法棒 (8回分)"], item_fate.SELL)          # 「取り込まない」
        self.assertEqual(fates["アイス・ボルトの魔法棒 (0回分)"], item_fate.ABSORB)  # empty, absorbed kind
        self.assertEqual(fates["トラップ感知のロッド"], item_fate.ABSORB)
        summary = home_ledger.summary(policy, board)
        self.assertEqual((summary["absorb"], summary["fits"]), (13, True))

    def test_the_home_take_and_the_town_absorption(self):
        _, policy, board = self.n1b
        takes = me_device_policy.home_absorb_takes(policy, board)
        self.assertEqual(len(takes), 15)
        saved = (policy._home_pending_item, policy._home_pending_quantity,
                 policy._home_withdrawal_queued)
        self.addCleanup(self.restore, policy, saved)
        policy._bind_home_absorb_device_withdrawal(board)
        # The last shelf stack first, whole.
        self.assertEqual(policy._home_pending_item, policy._item_signature(takes[-1]))
        self.assertEqual(policy._home_pending_quantity, takes[-1].count)
        # DECLARED CONSTRUCTED: the game's take, the stack at the next pack letter and off the
        # shelf.
        letter = chr(ord("a") + len(board.inventory))
        taken = replace(takes[-1], slot=letter)
        carried = replace(board, inventory=(*board.inventory, taken),
                          player=replace(board.player, hp=board.player.max_hp))
        self.restore(policy, saved)
        self.assertEqual(policy._retention_reservation(carried, taken), taken.count)
        before = policy._home_knowledge_items
        self.addCleanup(setattr, policy, "_home_knowledge_items", before)
        policy._home_knowledge_items = [item for item in before if item is not takes[-1]]
        # The takes come first (tests/test_n1c_217_absorb_deadline_1119_recorded): the next
        # shelf stack is taken before the carried one is absorbed.
        self.assertEqual(me_device_policy.next_home_absorb_take(policy, carried), takes[-2])
        self.assertIsNone(magic_eater.absorb_key(policy, carried, []))
        # DECLARED CONSTRUCTED: the Home without the other copies (all taken): it is absorbed.
        policy._home_knowledge_items = [item for item in before
                                        if not any(item is take for take in takes)]
        self.assertEqual(magic_eater.absorb_key(policy, carried, []), "G" + letter)
        self.assertEqual(policy.last_reason, magic_eater.ABSORB_REASON)

    @staticmethod
    def restore(policy, saved):
        (policy._home_pending_item, policy._home_pending_quantity,
         policy._home_withdrawal_queued) = saved

    def destruction_staff(self, count):
        _, policy, board = self.n1b
        staff = replace(next(item for item in policy._home_knowledge_items if item.tval == 55),
                        name="*破壊*の杖 (5回分)", sval=29, charges=5, pval=5)
        real = me_capability.count

        def counted(policy_, snapshot, kind, sval):
            return count if (kind, sval) == ("staff", 29) else real(policy_, snapshot, kind, sval)
        with patch.object(me_capability, "count", counted):
            return item_fate.fate(policy, board, staff, item_fate.SHELF)

    def test_the_destruction_staff_at_the_cap_is_destroyed(self):
        self.assertEqual(self.destruction_staff(99), item_fate.DESTROY)
        # Below the cap the table recharges it at the Tower and absorbs it (absorb_after_charge).
        self.assertEqual(self.destruction_staff(60), item_fate.ABSORB)

    def test_the_cap_tidy_on_the_decision_path(self):
        """Row 0 as recorded; then DECLARED CONSTRUCTED: the arrival board at full HP (the
        recorded 1082/1103 HP rests first, town:recover)."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(FIXTURES / "quest32-one-turn-kill-1119" / "n1b-411",
                                       Path(scratch.name))
        recorded_row, supply = steps[0]
        board = supply()
        before = copy.copy(policy._store_visit)
        self.assertEqual((policy.choose_key(board), policy.last_reason),
                         (recorded_row["key"], recorded_row["reason"]))
        post(policy, board, recorded_row["key"], before)
        board = replace(board, player=replace(board.player, hp=board.player.max_hp))
        policy.choose_key(board)
        relief = policy._home_full_relief
        # The tidy sheds its count over the cap; the absorptions take the devices on their own.
        self.assertTrue(relief.cap)
        self.assertEqual(relief.remaining, 239 - home_ledger.HOME_KEEP_CAP)
        ware = next(item for item in policy._home_knowledge_items
                    if policy._item_signature(item) == relief.sale[0])
        self.assertEqual(item_fate.fate(policy, board, ware, item_fate.SHELF), item_fate.SELL)
        self.assertEqual(item_fate.clearly_useless(
            policy, board, replace(ware, slot=item_fate.HOME_STOCK_SLOT)), "dominated")

    def test_another_class_keeps_its_rules(self):
        _, policy, board = self.n1b
        warrior = replace(board, player=replace(board.player, class_id=0))
        for item in policy._home_knowledge_items:
            if item.tval in DEVICE_TVALS:
                self.assertIsNone(me_device_policy.home_fate(policy, warrior, item), item.name)


if __name__ == "__main__":
    unittest.main()
