"""#47 N1: the Magic-Eater capability facade and the REPLACES table (me_capability).

Owner rules: 「今後条件を追加する可能性があること、取り込み魔法道具は今後も増える
ことに留意して保守性を維持するように作って。」 (2026-10-31) and 「修正の際にも保守性が
向上するように努めて」 (2026-10-28).

Boards: the recorded n1-c life-016 Yeek-cave board (tests/fixtures/
me-mining-death-20261030.json.gz, test_me_mining_death_recorded) for the
evidence rule, and the recorded D25 life-033 Outpost board with an Alchemist
page (test_me_powerful_activation) for the table end to end.  DECLARED
CONSTRUCTED: the absorption record (old int keys where a checkpoint written
before #47 N1 would hold them), the displayed power lists
(``_magic_eater_power_list`` rows with BaseitemDefinitions names), the class
of the not-class-16 case, and the table row added for the end-to-end case.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from dataclasses import replace
import unittest
from unittest import mock

from hengbot import me_absorbed_substitutes as substitutes
from hengbot import me_capability as capability
from hengbot import me_staff_sequence as sequence
from hengbot.me_device_attacks import observe_lists
from hengbot.me_device_attacks_input import compile_device
from hengbot.model import (
    STORE_ALCHEMIST, SV_SCROLL_STAR_IDENTIFY, SV_STAFF_IDENTIFY, SV_STAFF_LITE,
    SV_STAFF_REMOVE_CURSE, SV_WAND_STONE_TO_MUD, TVAL_SCROLL, TVAL_STAFF, parse_snapshot,
)
from tests import test_me_mining_death_recorded as mining
from tests import test_me_powerful_activation as powerful_tests

LIFE, TURN = "life-016", 94171


def listed(kind, *rows):
    """A displayed power list: (name, current, max) rows."""
    return {"kind": kind, "rows": [{"name": name, "current": current, "max": count,
                                    "fail": 10, "success": 90} for name, current, count in rows]}


class EvidenceTest(mining.harness.ProductionHarness):
    """One rule: the displayed row, else the record keyed by (kind, sval)."""
    raw = mining.MagicEaterMiningDeathRecordedTest.raw
    recorded_policy = mining.MagicEaterMiningDeathRecordedTest.policy

    @classmethod
    def setUpClass(cls):
        mining.MagicEaterMiningDeathRecordedTest.setUpClass.__func__(cls)

    def board(self, power_list=None, *, class_id=None):
        raw = self.raw(LIFE, TURN, class_id=class_id)
        if power_list is not None:
            raw["_magic_eater_power_list"] = power_list
        policy = self.recorded_policy(LIFE, raw)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        observe_lists(policy, board)
        return policy, board

    def test_old_record_keys_load_in_their_own_kind(self):
        policy, board = self.board()
        # A checkpoint before #47 N1: stage staffs by int sval, extras by kind:sval.
        sequence.state(policy).absorbed = {SV_STAFF_IDENTIFY: 21, SV_STAFF_REMOVE_CURSE: 3,
                                           "wand:6": 12, "staff:27": 5}
        self.assertTrue(capability.has(policy, board, "staff", SV_STAFF_IDENTIFY))
        self.assertEqual(capability.count(policy, board, "staff", SV_STAFF_IDENTIFY), 21)
        # The int key 6 is the staff (Remove Curse), never the Stone to Mud wand.
        self.assertEqual(capability.charges(policy, board, "wand", SV_WAND_STONE_TO_MUD), 12)
        self.assertEqual(capability.count(policy, board, "wand", SV_WAND_STONE_TO_MUD), 12)
        self.assertEqual(capability.count(policy, board, "staff", SV_STAFF_REMOVE_CURSE), 3)
        # Unfixed: a non-stage staff the sequence absorbed read 0 (int keys only).
        self.assertEqual(capability.charges(policy, board, "staff", 27), 5)
        self.assertEqual(sequence.state(policy).absorbed,
                         {"staff:5": 21, "staff:6": 3, "wand:6": 12, "staff:27": 5})

    def test_a_displayed_row_or_the_record(self):
        policy, board = self.board(listed("staff", ("鑑定", 5, 14)))
        self.assertTrue(capability.has(policy, board, "staff", SV_STAFF_IDENTIFY))
        self.assertEqual((capability.count(policy, board, "staff", SV_STAFF_IDENTIFY),
                          capability.charges(policy, board, "staff", SV_STAFF_IDENTIFY)), (14, 5))
        # The list predates an absorption the record holds (an absorbed power
        # stays listed, mind-magic-eater.cpp): the record serves.
        self.assertFalse(capability.has(policy, board, "staff", SV_STAFF_LITE))
        sequence.state(policy).absorbed = {capability.record_key("staff", SV_STAFF_LITE): 19}
        self.assertTrue(capability.has(policy, board, "staff", SV_STAFF_LITE))
        self.assertEqual(capability.charges(policy, board, "staff", SV_STAFF_LITE), 19)

    def test_a_board_that_shows_the_power_empty(self):
        policy, board = self.board(listed("staff", ("光", 0, 19)))
        sequence.state(policy).absorbed = {capability.record_key("staff", SV_STAFF_LITE): 19}
        self.assertEqual(capability.recorded_charges(policy, board, "staff", SV_STAFF_LITE), 0)
        self.assertEqual(capability.charges(policy, board, "staff", SV_STAFF_LITE), 0)
        later = replace(board, turn=board.turn + 10, magic_eater_power_list=None)
        # It regenerates: a later board serves the record's count again.
        self.assertEqual(capability.recorded_charges(policy, later, "staff", SV_STAFF_LITE), 19)

    def test_only_class_16(self):
        policy, board = self.board(class_id=1)
        sequence.state(policy).absorbed = {"staff:5": 21}
        self.assertFalse(capability.has(policy, board, "staff", SV_STAFF_IDENTIFY))
        self.assertEqual(capability.charges(policy, board, "staff", SV_STAFF_IDENTIFY), 0)
        # A caller without a board reads the evidence (only class 16 records it).
        self.assertTrue(capability.has(policy, None, "staff", SV_STAFF_IDENTIFY))


class ReplacesTableTest(unittest.TestCase):
    """Every row names a known power, condition, reading and use."""

    def test_rows_are_well_formed(self):
        for row in capability.REPLACES:
            with self.subTest(row=row):
                self.assertIn(row.when, capability.WHEN)
                self.assertTrue(row.amount is None or row.amount in capability.AMOUNT)
                self.assertTrue(row.uses <= capability.EVERY_USE and row.uses)
                if row.power is None:
                    self.assertIn(row.when, {"staff-sequence", "stage-staff"})
                else:
                    self.assertEqual(len(capability.names(*row.power)), 2)

    def test_every_carry_power_is_cast_through_the_executor(self):
        for ident in capability.carry_powers():
            power = substitutes.POWERS[ident]
            with self.subTest(power=ident):
                self.assertEqual(power.names, capability.names(*ident))
                key = power.key + ("6" if power.aimed else "")
                self.assertEqual(power.aimed, ident[0] == "wand")
                self.assertIsNotNone(compile_device(key, "quest-strategy:q2" + substitutes.CAST_SUFFIX))

    def test_a_carry_and_an_item_are_asked_alike(self):
        light = capability.Carry("required_scrolls", "light")
        self.assertEqual(capability.replacing_power(light), ("staff", SV_STAFF_LITE))
        self.assertIsNone(capability.replacing_power(capability.Carry("required_scrolls", "phase")))
        self.assertEqual(capability.replacing_power((TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY)),
                         ("staff", SV_STAFF_IDENTIFY))


class NewRowEndToEndTest(powerful_tests.executor_harness.ProductionHarness):
    """Adding a device that replaces an item is one row: the shop then neither
    offers nor matches the item (the recorded life-033 board, an Alchemist
    page with the *Identify* scroll, only Remove Curse absorbed)."""
    _case = powerful_tests.MagicEaterPowerfulActivationTest
    setUpClass = classmethod(_case.setUpClass.__func__)
    board = _case.board
    choose = _case.choose
    shop = _case.shop

    def purchase(self, rows):
        policy, raw = self.board(store=self.shop(STORE_ALCHEMIST, SV_SCROLL_STAR_IDENTIFY, "*鑑定*の巻物"),
                                 effects=(powerful_tests.powerful.UNCURSE,))
        raw["player"]["gold"] = 20000
        with mock.patch.object(capability, "REPLACES", rows):
            self.choose(policy, raw)
            policy._identification_need = "full"
            policy._fundraising_mode = None  # DECLARED CONSTRUCTED as the borrowed case
            board = parse_snapshot(raw, policy._monrace_knowledge)
            ware = policy._next_purchase(board)
            rungs = policy._matching_live_purchase_rungs(board, board.store.items[0])
        return ware, rungs

    def test_one_row_stops_the_purchase(self):
        ware, rungs = self.purchase(capability.REPLACES)
        self.assertEqual((ware.tval, ware.sval), (TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY))
        self.assertTrue(rungs)
        # DECLARED CONSTRUCTED row (no owner rule): the absorbed Remove Curse
        # power standing in for the *Identify* scroll.
        row = capability.Replacement(("staff", SV_STAFF_REMOVE_CURSE),
                                     capability.Kind(TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY))
        ware, rungs = self.purchase((*capability.REPLACES, row))
        self.assertIsNone(ware)
        self.assertEqual(rungs, ())


if __name__ == "__main__":
    unittest.main()
