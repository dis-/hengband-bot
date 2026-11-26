"""A Home take that cannot happen is not filed again and again (n1-a life-545, MAINTAINABILITY.md 1-3).

Recorded (tests/extract_n1a_545_identify_withdraw_loop_1127_fixture.py,
``n1a-545-identify-withdraw-loop-1127``): the town-arrival checkpoint of 2026-11-27 03:11:01 (Amberite
Rogue CL23, ordinary food, none carried, a mining set open).  Row 24 handed the queued 18 bolts
(the ammunition top-up) to Home's entrance; the fundraising food need had replaced that queue with
Home's Identify staves as the Rogue's "food" (``_home_mana_food_candidate`` for an eater of food),
row 25 took the 4-charge staff, and from row 27 the 5-charge staff's take was refused as overweight,
re-queued on the next board and refused again until town:blocked:stage-deadline:home.  Rows before
the one decided are replayed through the public ``choose_key`` and post the recorded key.

DECLARED CONSTRUCTED: ``test_a_refused_take_waits_for_a_lighter_pack`` records a refusal of the
5-charge staff on row 25's board and lightens that board by the carried shield (the pack the sale of
the shield would leave).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import home_take_admission, town_hold
from hengbot.model import STORE_HOME, SV_STAFF_IDENTIFY, TVAL_STAFF
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-identify-withdraw-loop-1127"
TAKE_ROW = 25
TVAL_BOLT = 18


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


class IdentifyWithdrawLoop545RecordedTest(unittest.TestCase):
    def replay(self, rows):
        """(policy, journal steps) after the recorded rows before ``rows``."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(FIXTURE, Path(scratch.name))
        for recorded, supply in steps[:rows]:
            key, reason = decide(policy, supply())
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), recorded["row"])
            post(policy, recorded["key"])
        return policy, steps

    def staves(self, policy):
        return [item for item in policy._home_knowledge_items
                if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY]

    def test_the_rogue_takes_its_queued_bolts_not_a_staff_as_food(self):
        policy, steps = self.replay(TAKE_ROW)
        recorded, supply = steps[TAKE_ROW]
        board = supply()
        self.assertEqual(recorded["key"], "5pr\x1b")  # the recorded take: Home's 4-charge staff
        self.assertNotEqual(board.player.food_type, 4)
        self.assertIsNone(policy._find_edible(board))
        # Rule 1: Home holds no ration-class food for this eater; its staves are no food.
        self.assertIsNone(policy._home_food_candidate(board))
        self.assertEqual(policy._home_mana_food_candidate().tval, TVAL_STAFF)

        key, reason = decide(policy, board)

        self.assertEqual(reason, "home:atomic-withdraw")
        self.assertTrue(key.startswith("5 p") and key.endswith("18\r\x1b"), key)
        self.assertEqual(policy._home_pending_item[1], TVAL_BOLT)

    def test_a_refused_take_waits_for_a_lighter_pack(self):
        policy, steps = self.replay(TAKE_ROW)
        board = steps[TAKE_ROW][1]()
        staff = min(self.staves(policy), key=lambda item: item.charges)
        signature = policy._item_signature(staff)
        self.assertIsNone(home_take_admission.refusal(policy, board, staff, 1))
        # DECLARED CONSTRUCTED: the take refused here (the executor's record).
        home_take_admission.record(policy, board, signature)
        self.assertEqual(home_take_admission.refusal(policy, board, staff, 1),
                         home_take_admission.REFUSED_THIS_VISIT)
        self.assertFalse(home_take_admission.admit(policy, board, staff, 1))
        shield = next(item for item in board.inventory if item.tval == 34)
        lighter = replace(board, inventory=[item for item in board.inventory if item is not shield])
        self.assertLess(policy._inventory_weight(lighter), policy._inventory_weight(board))
        self.assertTrue(home_take_admission.admit(policy, lighter, staff, 1))

    def test_the_home_visit_holder_opens_the_walk_to_its_queued_take(self):
        policy, steps = self.replay(TAKE_ROW)
        board = steps[TAKE_ROW][1]()
        key, _reason = decide(policy, board)
        post(policy, key)
        board = steps[TAKE_ROW + 1][1]()
        holder = town_hold.errand_hold(policy, "__none__", enforced=True)
        self.assertEqual(holder.owner.value, "home-visit")
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)
        self.assertTrue(town_hold.home_route_opened_for(policy, "store-router"))
        key, reason = decide(policy, board)
        self.assertNotEqual(reason, "policy:none-wait")
        self.assertNotIn("identify-staff-overweight", reason)


if __name__ == "__main__":
    unittest.main()
