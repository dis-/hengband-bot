"""The town's hold flags in one place (town rebuild stage 3-2a, owner 2026-11-12).

Real last board of tests/fixtures/keep-running-a0 (test_keep_running_a0); the
attribute values set below are DECLARED CONSTRUCTED.
"""
import tests  # noqa: F401

from dataclasses import fields
import pickle
import unittest

from hengbot.policy_constants import TOWN_CYCLE_WINDOW
from hengbot.town_visit import HOLD_LEGACY_NAMES, TownHolds, adopt_legacy_holds, town_holds
from test_keep_running_a0 import ready_board


class TownHoldsTest(unittest.TestCase):
    def test_every_hold_has_one_former_name(self):
        self.assertEqual(sorted(HOLD_LEGACY_NAMES.values()),
                         sorted(spec.name for spec in fields(TownHolds)))

    def test_the_former_names_read_and_write_the_holds(self):
        policy, _board, _ = ready_board()
        holds = town_holds(policy)
        policy._town_cycle_pending = True
        policy._town_restock_waiting_for = (3,)
        self.assertTrue(holds.cycle_pending)
        self.assertEqual(holds.restock_waiting_for, (3,))
        self.assertNotIn("_town_cycle_pending", vars(policy))
        self.assertEqual(policy._town_signature_history.maxlen, TOWN_CYCLE_WINDOW)

    def test_release_forgets_every_hold_and_keeps_the_containers(self):
        policy, _board, _ = ready_board()
        history = policy._town_signature_history
        recorded = policy._visit_departure_recorded
        history.append(("x",))
        recorded.add("y")
        policy._town_errand_plan = object()
        policy._town_no_progress_count = 7
        policy._terminal_pack_space_signature = (("a", 1),)
        town_holds(policy).release()
        self.assertIs(policy._town_signature_history, history)
        self.assertIs(policy._visit_departure_recorded, recorded)
        self.assertEqual((len(history), len(recorded)), (0, 0))
        self.assertIsNone(policy._town_errand_plan)
        self.assertEqual(policy._town_no_progress_count, 0)
        self.assertIsNone(policy._terminal_pack_space_signature)
        self.assertEqual(history.maxlen, TOWN_CYCLE_WINDOW)

    def test_an_old_checkpoint_moves_its_attributes_into_the_holds(self):
        """DECLARED CONSTRUCTED: the state an old checkpoint unpickles to."""
        plan = object()
        state = {"_town_errand_plan": plan, "_town_cycle_breaks": 2, "other": 1}
        adopt_legacy_holds(state)
        self.assertEqual(set(state), {"_town_holds", "other"})
        self.assertIs(state["_town_holds"].errand_plan, plan)
        self.assertEqual(state["_town_holds"].cycle_breaks, 2)

    def test_the_holds_survive_a_pickle_round_trip(self):
        policy, _board, _ = ready_board()
        policy._town_cycle_breaks = 3
        restored = pickle.loads(pickle.dumps(town_holds(policy)))
        self.assertEqual(restored.cycle_breaks, 3)
        self.assertEqual(restored.signature_history.maxlen, TOWN_CYCLE_WINDOW)


if __name__ == "__main__":
    unittest.main()
