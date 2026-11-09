"""n1-a life-505 2026-11-10 01:37 equipment-transaction:restore-blocked-terminal.

Recorded: the town-arrival checkpoint of the incident capture and its journal
(tests/extract_n1a_505_stolen_deposit_1110_fixture.py).  Every decision goes
through the public ``choose_key`` on the restored arrival policy; each key is
acknowledged as posted the way the CLI does (``RecordedVisit``).

The transaction 577445949f1207dc took the ロング・ソード (main hand) and the
浮遊の指輪 (main ring) off, wore the 耐光耐暗の指輪 and the 滅善の鎖つき鉄球
(rows 19-22) and walked home to deposit the two (row 23).  On the way a
ブラックマーケットのエージェント touched the player and stole the sword from
the pack (row 25: 「ロング・ソード (2d5) (+3,+3)(o)を盗まれた！」, the game's
monster-eating.cpp:145 ``process_eat_item``, pack slots only).  Home took the
ring (rows 26-27); the sword's deposit found nothing (row 29,
``deposit-missing``), the restoration found the owned sword nowhere and the
bot stopped (row 31, ``restore-blocked-terminal``).

Fix (equipment_pack_loss): gear the game took out of the pack is recorded,
its transaction ownership released and its deposit dropped, so the rest of
the transaction completes on the new loadout.

DECLARED WALL 1 (optimizer input): the live bot read the character dump it
wrote at decision 2349 (row 0); the capture holds only the dump of the
arrival (level 15, the character is level 17), so the replayed optimizer
answers calibration-required and the visit diverges from row 5.  Rows 0-18
are fed with the recorded keys, and at row 19 the recorded plan
(``transaction_actions`` of decision 2368, target 577445949f1207dc) is
installed through ``_set_equipment_transaction_session``, its items taken
from the row-19 board.
DECLARED WALL 2 (Home catalogue): the replayed rows 5-9 leave the Home
knowledge stale (the live session recorded its deposit); the complete Home
page of row 9 is adopted through ``_adopt_home_catalogue``, as the live
catalogue was current at decision 2367 (decision log
``home_knowledge_current``).
With both walls rows 19-31 decide exactly as recorded before the fix.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path

from hengbot import equipment_pack_loss
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import (
    EquipmentTransaction,
    EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import STORE_HOME
from hengbot.policy_constants import EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT
from tests.test_stops_1109_town_recorded import RecordedVisit

FIXTURES = Path(__file__).with_name("fixtures") / "stolen-deposit-1110"

# transaction_actions of decision 2368 (phase, kind, item id, target slot).
RECORDED_PLAN = (
    ("equip", "takeoff", "equipped:e8ace03b75c9e536:0", "main_hand"),
    ("equip", "takeoff", "equipped:163ac56a60a36f1b:0", "main_ring"),
    ("equip", "equip", "pack:a4a10489dd003130:0", "main_ring"),
    ("equip", "equip", "pack:0cbb45a4c14d7f76:0", "main_hand"),
    ("home_finalize", "deposit", "equipped:163ac56a60a36f1b:0", None),
    ("home_finalize", "deposit", "equipped:e8ace03b75c9e536:0", None),
)
SWORD = "e8ace03b75c9e536"
RING = "163ac56a60a36f1b"
THEFT_ROW, RING_DEPOSIT_ROW, RING_CONFIRMED_ROW, LAST_ROW = 25, 26, 27, 31


class StolenDepositVisit(RecordedVisit):
    fixtures = FIXTURES
    fixture = "t505"

    def to_transaction(self):
        """Rows 0-18 as recorded, then the recorded plan (walls 1 and 2)."""
        home_page = None
        for row in range(19):
            board, _key, _reason = self.decide(row, post_recorded=True)
            if board.store is not None and board.store.store_type == STORE_HOME:
                home_page = (row, board)
        self.assertEqual(home_page[0], 9)
        self.assertTrue(self.policy._open_home_page_is_complete(home_page[1]))
        self.policy._adopt_home_catalogue(tuple(
            self.policy._inventory_item_from_store_item(item)
            for item in home_page[1].store.items))
        board = self.board(19)
        carried = {equipment_identity(item): item
                   for item in (*board.equipment, *board.inventory) if item.is_equipment}
        actions = []
        for phase, kind, item_id, slot in RECORDED_PLAN:
            item = carried[item_id.split(":")[1]]
            actions.append(EquipmentTransaction(
                phase, kind, item_id, slot,
                equipment_identity(item), equipment_move_identity(item)))
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan(tuple(actions), (), 0),
            max_unconfirmed_observations=EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
            physical_context="legacy")
        self.assertEqual(session.target_loadout_id, "577445949f1207dc")
        self.policy._set_equipment_transaction_session(session)
        self.sword_move = equipment_move_identity(carried[SWORD])

    def replay_rows(self, first, last):
        """(row, key, reason) of rows ``first``..``last``."""
        return [(row, *self.decide(row)[1:]) for row in range(first, last + 1)]


class StolenSwordDepositTest(StolenDepositVisit):

    def test_recorded_rows_are_the_theft_and_the_terminal(self):
        self.assertEqual(
            [self.journal[row]["reason"] for row in (THEFT_ROW, 29, LAST_ROW)],
            ["equipment-transaction:travel-home", "equipment-transaction:deposit-missing",
             "equipment-transaction:restore-blocked-terminal"])
        self.to_transaction()
        self.replay_rows(19, THEFT_ROW - 1)
        board = self.board(THEFT_ROW)
        self.assertIn("ロング・ソード (2d5) (+3,+3)(o)を盗まれた！", board.messages)
        self.assertNotIn(self.sword_move, {equipment_move_identity(item) for item in board.inventory})

    def test_rows_before_the_theft_decide_as_recorded(self):
        self.to_transaction()
        for row, key, reason in self.replay_rows(19, THEFT_ROW):
            self.assertEqual((key, reason), (self.journal[row]["key"], self.journal[row]["reason"]), row)

    def test_the_theft_releases_the_sword_and_records_the_loss(self):
        self.to_transaction()
        self.replay_rows(19, THEFT_ROW - 1)
        self.assertIn(self.sword_move, [identity for identity, _ in
                                        self.policy._equipment_transaction_owned_items])
        self.replay_rows(THEFT_ROW, THEFT_ROW)
        self.assertNotIn(self.sword_move, [identity for identity, _ in
                                           self.policy._equipment_transaction_owned_items])
        losses = equipment_pack_loss.losses_report(self.policy)
        self.assertEqual([(loss["cause"], loss["name"], loss["identity"]) for loss in losses],
                         [("stolen", "ロング・ソード (2d5) (+3,+3)", SWORD)])
        state = self.policy.equipment_optimization_state(self.board(THEFT_ROW + 1))
        self.assertEqual(state["transaction_pack_losses"][0]["identity"], SWORD)

    def test_the_ring_is_deposited_and_the_transaction_completes(self):
        self.to_transaction()
        self.replay_rows(19, RING_DEPOSIT_ROW - 1)
        _board, key, reason = self.decide(RING_DEPOSIT_ROW)
        self.assertEqual((key, reason), ("dn", "equipment-transaction:deposit"))
        self.decide(RING_CONFIRMED_ROW)
        # Before (f593fe3c9b): the session stayed on the sword's deposit and
        # row 29 abandoned it as deposit-missing.
        self.assertIsNone(self.policy._equipment_transaction_session)
        self.assertEqual(self.policy._equipment_transaction_owned_items, [])
        self.assertIsNone(self.policy._equipment_transaction_restore_terminal)
        self.assertIn("浮遊の指輪", [item.name for item in self.policy._home_knowledge_items])
        worn = {item.slot: equipment_identity(item) for item in self.board(RING_CONFIRMED_ROW).equipment}
        self.assertEqual((worn["main_hand"], worn["main_ring"]),
                         ("0cbb45a4c14d7f76", "a4a10489dd003130"))

    def test_the_visit_goes_on_without_the_terminal(self):
        self.to_transaction()
        rows = self.replay_rows(19, LAST_ROW)
        reasons = [reason for _row, _key, reason in rows]
        self.assertFalse([reason for reason in reasons
                          if "restore-blocked" in reason or "deposit-missing" in reason], reasons)
        self.assertIsNone(self.policy._equipment_transaction_restore_terminal)
        self.assertEqual(self.policy._equipment_transaction_restore_remainder, ())


class LossMessageTest(unittest.TestCase):
    """The game's messages (monster-eating.cpp:145-147, inventory-damage.cpp:70-72)."""

    def test_messages(self):
        self.assertEqual(equipment_pack_loss.loss_lines([
            "触られた。",
            "ロング・ソード (2d5) (+3,+3)(o)を盗まれた！",
            "泥棒は笑って逃げた！",
            "油つぼ(b)を一つ盗まれた！",
            "ロングボウ (x3) (+2,+3)(p)が壊れてしまった！",
            "矢 (1d4)(q)が何個か壊れてしまった！",
            "Your Long Sword (2d5) (+3,+3) (o) was stolen!",
            "One of your Flasks of Oil (b) was stolen!",
            "All of your Arrows (1d4) (q) were destroyed!",
            "ロング・ソード (2d5) (+3,+3)(o)を装備からはずした。",
        ]), [
            ("stolen", "ロング・ソード (2d5) (+3,+3)", "o"),
            ("stolen", "油つぼ", "b"),
            ("destroyed", "ロングボウ (x3) (+2,+3)", "p"),
            ("destroyed", "矢 (1d4)", "q"),
            ("stolen", "Long Sword (2d5) (+3,+3)", "o"),
            ("stolen", "Flasks of Oil", "b"),
            ("destroyed", "Arrows (1d4)", "q"),
        ])


if __name__ == "__main__":
    unittest.main()
