"""Town stops of 2026-11-07 decided again from recorded mid-visit checkpoints.

Recorded substrate: tests/fixtures/town-stops-1107/ (written by
tests/extract_town_stops_1107_fixtures.py, which names the incident captures
and how the checkpoints were taken; ``replay.json`` lists the journal rows
the deployed code decided differently before the checkpoint).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import STORE_HOME
import town_stops_1107_fixture as fx


class TownStops1107RecordedTest(unittest.TestCase):

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def test_town_end_routes_home_for_a_filed_take_home_was_not_marked_tried_for(self):
        """n1-a life 492 09:42:14 town:blocked:unmet:home_candidate_resolved.

        The checkpoint is taken before the stop's board (journal row 55; the
        deployed code decided rows 0-54 as recorded).  The catalogue take of
        闇の陣笠 was filed, four *Identify* scrolls were carried and the
        visit's attempted set was {6: ...}: Home's latch from its pass had
        expired.  filed_take_route_key routed only a Home marked tried, so the
        town end stopped; the restarted process took the helmet on its first
        Home entry (decision 4, home-errand:atomic-withdraw:
        identification-catalog).
        """
        self.assertEqual(fx.replay_facts("home-take-route")["diverged"], [])
        policy = fx.restore("home-take-route", self.scratch)
        entry = fx.journal("home-take-route")[0]
        self.assertEqual(entry["reason"], "town:blocked:unmet:home_candidate_resolved")
        board = fx.board(policy, entry, self.scratch)
        request = policy._home_errand.request
        self.assertTrue(policy._home_errand.active)
        self.assertEqual(request.purpose, "identification-catalog")
        key = policy.choose_key(board)
        # The Home latch of this visit's pass (turn 5583538) expired on this
        # board's observation (turn 5583960), as the live log shows.
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)

    def test_refused_in_home_takeoff_abandons_the_transaction_instead_of_idling(self):
        """n1-b life 337 09:55 owner-retired-burst: the Home transaction loop.

        The checkpoint is taken before journal row 8 (the deployed code and
        this code decide rows 0-7 as recorded): in Home, step 2 (takeoff of
        the main ring) is done and step 3 is the takeoff of 'outer'; a
        Magic-Eater catalogue take (row 5) filled the slot the plan counted
        on, so the pack holds 19 of 23 and the town pack budget refuses the
        takeoff.  The step composed nothing: policy:none-store-exit, then
        equipment-transaction:approach-home re-entered Home for the same step
        (rows 8-46) until the owner retirements stopped the town.
        """
        self.assertEqual(fx.replay_facts("takeoff-refused")["diverged"], [])
        policy = fx.restore("takeoff-refused", self.scratch)
        rows = fx.journal("takeoff-refused")
        self.assertEqual([row["reason"] for row in rows[:3]], [
            "policy:none-store-exit", "equipment-transaction:approach-home",
            "equipment-transaction:approach-home"])
        board = fx.board(policy, rows[0], self.scratch)
        self.assertEqual(board.store.store_type, STORE_HOME)
        self.assertEqual(len(board.inventory), 19)
        actions = policy._equipment_transaction_session.plan.actions
        self.assertEqual((actions[3].kind, actions[3].target_slot), ("takeoff", "outer"))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("\x1b", "equipment-transaction:abandon-blocked-home"))
        fx.post(policy, key)
        # The recorded next board is the same one: outside on Home's entrance.
        board = fx.board(policy, rows[1], self.scratch)
        self.assertIsNone(board.store)
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "equipment-transaction:approach-home")
        # The abandonment restores the ring the transaction had taken off.
        session = policy._equipment_transaction_session
        self.assertEqual(policy.last_reason, "equipment-transaction:equip")
        self.assertEqual([(action.kind, action.target_slot) for action in session.plan.actions],
                         [("equip", "main_ring")])


if __name__ == "__main__":
    unittest.main()
