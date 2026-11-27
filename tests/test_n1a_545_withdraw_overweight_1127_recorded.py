"""An equipment swap within the weight that costs no speed goes on; one that would cost speed is
dropped before anything comes off (n1-a life-545, MAINTAINABILITY.md 2 and 3).

Recorded (tests/extract_n1a_545_withdraw_overweight_1127_fixture.py,
``n1a-545-withdraw-overweight-1127``): the town-arrival checkpoint of 2026-11-27 16:58:52
(Amberite Rogue CL34, gold 24683, turn 5302903).  The equipment transaction swapped two pieces
through Home (rows 34-46 and 48-59; the first lowered the weight limit from 1700 to 1650,
adj_str_wgt x 50, player-status.cpp:2556-2563).  Row 60 opened the third session: take off the
ドラゴンスレイヤーのロッホアーバー・アックス (250 tenths of a pound), deposit it, take the
(聖戦者)ランス (300) out of Home and wield it.  Rows 62-63 took the axe off and deposited it
(1635 -> 1385), and row 69, on the lance's Home page, refused the withdrawal
(equipment-transaction:withdraw-overweight): the kept load after the swap is 1631 - 250 + 300 =
1681 on the 1650 limit, 3.1 lb over, which costs no speed (player-speed.cpp:43-51: one speed per
330 over).  The refusal blocked the session without ending it, so the next board entered Home for
the same refusal (row 70, livelock:exhausted on the repeated entry; without the detector the
decision is equipment-transaction:travel-home:await-entry).  The character stood with no weapon.

The fix asks the swap's weight once, before the session's first action, with the town's one
overweight answer (overweight_departure.swap_departs): the load departs when within the weight
that costs no speed (1979 here) once the reserved quantities the relief may shed are shed.
Every row before the one decided is replayed through the public ``choose_key`` and compared
with the record (full state: the town-arrival checkpoint, its journal and sidecars).

DECLARED CONSTRUCTED: the last two tests make the Home lance heavier in the optimizer's Home
catalogue on the row-60 board (3000: nothing sheds enough; 1000: the iron shots do).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import dataclasses
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import equipment_swap_weight, overweight_departure
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-withdraw-overweight-1127"
SESSION_ROW = 60
STOP_ROW = 69
STOP = ("\x1b", "equipment-transaction:withdraw-overweight")
LANCE = "home:3a7673003a3bd8ea:0"
LIMIT = 1650


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


def main_hand(board):
    return [item.name for item in board.equipment if item.slot == "main_hand"]


class WithdrawOverweight545RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Rows 0-59 are replayed once; every test restores the policy on the row-60 board.
        cls.scratch = TemporaryDirectory()
        policy, journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.stop = (journal[STOP_ROW]["key"], journal[STOP_ROW]["reason"])
        cls.replayed = []
        for recorded, supply in steps[:SESSION_ROW]:
            cls.replayed.append((decide(policy, supply()), (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])
        cls.rows = [(recorded, supply()) for recorded, supply in steps[SESSION_ROW:STOP_ROW + 1]]
        cls.checkpoint = checkpoint_bytes(policy)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        self.assertEqual(self.stop, STOP)
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)

    def heavier_lance(self, weight):
        """DECLARED CONSTRUCTED: the Home lance of the optimizer's catalogue weighs ``weight``."""
        home = self.policy._equipment_catalog._home
        owned = home[LANCE]
        home[LANCE] = dataclasses.replace(owned, item=dataclasses.replace(owned.item, weight=weight))

    def test_the_lance_comes_out_of_home(self):
        policy = self.policy
        for recorded, board in self.rows[:-1]:
            self.assertEqual(decide(policy, board), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            post(policy, recorded["key"])
        board = self.rows[-1][1]
        self.assertEqual(main_hand(board), [])
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (1385, LIMIT))
        self.assertEqual(overweight_departure.tolerated_weight(LIMIT), 1979)
        key, reason = decide(policy, board)
        self.assertNotEqual((key, reason), STOP)
        self.assertEqual(reason, "equipment-transaction:withdraw")
        self.assertTrue(key.startswith("p"), key)
        self.assertIsNone(policy._town_blocked_reason)

    def test_the_swap_is_asked_before_the_axe_comes_off(self):
        policy = self.policy
        recorded, board = self.rows[0]
        session = policy._equipment_transaction_session
        self.assertEqual((session.index, [action.kind for action in session.plan.actions]),
                         (0, ["takeoff", "deposit", "withdraw", "equip"]))
        # The old test (the limit) refused this swap; the overweight answer admits it.
        self.assertEqual(policy._inventory_weight(board), 1635)
        self.assertTrue(overweight_departure.swap_departs(policy, board, 1681, []))
        self.assertIsNone(equipment_swap_weight.withdraw_overload(policy, board, session))
        self.assertEqual(decide(policy, board), (recorded["key"], recorded["reason"]))

    def test_a_swap_that_would_cost_speed_is_dropped_with_the_axe_worn(self):
        policy = self.policy
        self.heavier_lance(3000)
        recorded, board = self.rows[0]
        overload = equipment_swap_weight.withdraw_overload(
            policy, board, policy._equipment_transaction_session)
        self.assertEqual(overload, {"limit": LIMIT, "weight": 1635, "kept": 1631,
                                    "kept_after": 4381, "tolerated": 1979})
        key, reason = decide(policy, board)
        self.assertTrue(reason.endswith("equipment-transaction:withdraw-overweight"), reason)
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertIsNone(policy._town_blocked_reason)
        closure = policy._equipment_transaction_visit_closure
        self.assertEqual((closure["reason"], closure["epoch"]),
                         (equipment_swap_weight.REFUSAL, policy._town_visit_epoch))
        self.assertEqual(len(main_hand(board)), 1)
        post(policy, key)
        # The visit goes on without the swap: no session reopens and nothing stops.
        for _ in range(3):
            key, reason = decide(policy, board)
            self.assertIsNone(policy._equipment_transaction_session)
            self.assertNotIn("blocked", reason)
            self.assertNotIn("livelock", reason)
            self.assertFalse(reason.startswith("equipment-transaction"), reason)
            post(policy, key)

    def test_a_swap_the_shed_reserved_weight_carries_goes_on(self):
        policy = self.policy
        self.heavier_lance(1000)
        recorded, board = self.rows[0]
        # 1631 - 250 + 1000 = 2381, 402 over the tolerated 1979; the reserved quantities the
        # relief may shed cover it: 81 of the 84 iron shots (5 each, the cheapest per weight).
        shed = overweight_departure.shed_candidates(policy, board, [], extra=2381 - 1635)
        self.assertEqual([(entry[2].slot, entry[3]) for entry in shed], [("s", 81)])
        self.assertTrue(overweight_departure.swap_departs(policy, board, 2381, []))
        self.assertIsNone(equipment_swap_weight.withdraw_overload(
            policy, board, policy._equipment_transaction_session))
        self.assertEqual(decide(policy, board), (recorded["key"], recorded["reason"]))


if __name__ == "__main__":
    unittest.main()
