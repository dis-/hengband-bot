"""ROOT-FIX S2 (a): the cross-town shopping hold is a refusal code of the
fixed-quest terminals (design 3.3 M5, ``cross-town-shopping-in-progress``).

Boards are the CONSTRUCTED goldburn seams of test_goldburn_shopping_constructed
(row 3512, Telmora, the admitted identification trip).  The entry asks the
terminal's verdict before any hold, so the quest rung does not run while the
trip still holds; once the local supplier shows stock-out it runs again.
"""

import tests  # noqa: F401

import unittest

from hengbot import town_terminal
from hengbot.model import STORE_ALCHEMIST
from test_goldburn_shopping_constructed import board, shopping_policy


def _decision_board(policy, snap):
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence = 1
    policy._decision_terminal_admissions = []
    policy._observe_cross_town_shopping_arrival(snap)
    return snap


class QuestWorkHoldTest(unittest.TestCase):
    def test_hold_is_the_entry_refusal_of_the_quest_terminal(self):
        policy = shopping_policy()
        snap = _decision_board(policy, board())
        calls = []
        key = policy._town_producer_entry(
            "_fixed_quest_key#2", lambda: calls.append("ran") or "7")
        self.assertIsNone(key)
        self.assertEqual(calls, [])
        rows = policy._decision_terminal_admissions
        self.assertEqual([row["codes"] for row in rows],
                         [["cross-town-shopping-in-progress"]])
        self.assertEqual(rows[0]["terminal"], ["quest-prepare-return", [1]])
        self.assertEqual(
            town_terminal.terminal_admission(
                policy, snap, town_terminal.TerminalRef("quest-claim", (2,))),
            town_terminal.refused(("cross-town-shopping-in-progress",)))

    def test_control_stockout_releases_the_quest_rung(self):
        policy = shopping_policy()
        snap = _decision_board(policy, board())
        policy._town_visit_ledger.shelf_observations[
            (STORE_ALCHEMIST, "identification-source:full")] = ()
        calls = []
        key = policy._town_producer_entry(
            "_fixed_quest_key#2", lambda: calls.append("ran") or "7")
        self.assertEqual((key, calls), ("7", ["ran"]))
        self.assertEqual(policy._decision_terminal_admissions, [])

    def test_verdict_is_pure_and_names_the_server(self):
        held = town_terminal.QuestWorkMaterial(shopping_hold=True)
        self.assertEqual(town_terminal.verdict_quest_work(held).codes,
                         ("cross-town-shopping-in-progress",))
        self.assertTrue(town_terminal.verdict_quest_work(
            town_terminal.QuestWorkMaterial()).admitted)
        self.assertEqual(
            town_terminal.refusal_servers(("cross-town-shopping-in-progress",)),
            (town_terminal.Server("cross-town"),))


if __name__ == "__main__":
    unittest.main()
