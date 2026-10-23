"""ROOT-FIX S2-d part 2 (round 5 item 3): departure leaves and the descent.

``departure:<leaf>``: each failing leaf of ``_town_departure_conjuncts`` is
its own refusal code with declared servers (design 3.4 S2 rows).  The recall
leaf names the owner decision of 2026-10-23 (sell the surplus, then scavenge
1F as fundraising); ``identify_staff_ready`` names the staff purchase and the
stock-out mining run (#76).  The material read evaluates the equipment leaf
without its confirmation writes (``commit=False``).

``descent`` / ``descent-here``: the town descent (``_descent_step``'s
committed target, ``direct-descent``'s own grid) is refused with
``quest-entrance-target`` when the destination asks the quest-entry question
(#102), and that code has no server (the rung closes for the visit).

Board: the CONSTRUCTED goldburn seam (row 3512, Telmora; see
test_goldburn_shopping_constructed).
"""

import tests  # noqa: F401

import unittest
from unittest.mock import patch

from hengbot import town_terminal
from hengbot.model import Position
from hengbot.policy import HengbotPolicy
from hengbot.town_terminal import (
    ADMIT, REFUSAL_SERVERS, DepartureMaterial, Server, TerminalRef, refusal_servers,
    verdict_departure,
)
from test_goldburn_shopping_constructed import board


def policy_on(snap):
    policy = HengbotPolicy()
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence += 1
    policy._decision_terminal_admissions = []
    return policy


class DepartureLeafTest(unittest.TestCase):
    def test_each_failing_leaf_is_its_own_code(self):
        self.assertEqual(verdict_departure(DepartureMaterial(())), ADMIT)
        refused = verdict_departure(DepartureMaterial(("recall_departure_ready",
                                                       "identify_staff_ready")))
        self.assertEqual(refused.codes, ("departure:recall_departure_ready",
                                         "departure:identify_staff_ready"))

    def test_every_leaf_of_the_gate_has_a_declared_row(self):
        snap = board()
        policy = policy_on(snap)
        leaves = (set(policy._town_departure_conjuncts(snap, commit=False))
                  | set(policy._recall_town_departure_conjuncts(snap, commit=False)))
        declared = {code.partition(":")[2] for code in REFUSAL_SERVERS
                    if code.startswith("departure:") and code != "departure:*"}
        self.assertEqual(leaves, declared)

    def test_owner_decision_servers(self):
        recall = refusal_servers(("departure:recall_departure_ready",))
        self.assertEqual(recall, (Server("shop-buy", "recall"),
                                  Server("shop-sell", "organization-sale"),
                                  Server("fundraising")))
        staff = refusal_servers(("departure:identify_staff_ready",))
        self.assertEqual(staff, (Server("shop-buy", "identify-staff"),
                                 Server("fundraising")))
        self.assertEqual(refusal_servers(("departure:a-later-leaf",)), ())

    def test_material_read_does_not_commit_the_equipment_leaf(self):
        snap = board()
        policy = policy_on(snap)
        seen = []
        with patch.object(HengbotPolicy, "_equipment_departure_ready",
                          lambda self, snapshot, **kw: seen.append(kw) or True):
            material = town_terminal.gather_departure(policy, snap)
            policy._town_departure_conjuncts(snap)
        self.assertEqual(seen, [{"commit": False}, {}])
        self.assertNotIn("equipment_departure_ready", material.failed)


class DescentTerminalTest(unittest.TestCase):
    def test_direct_descent_on_a_quest_entrance_is_refused(self):
        for quest_entrance in (True, False):
            with self.subTest(quest_entrance=quest_entrance):
                snap = board()
                policy = policy_on(snap)
                with patch.object(HengbotPolicy, "_step_raises_unintended_confirm",
                                  return_value=quest_entrance):
                    key = policy._town_producer_entry(
                        "direct-descent", lambda: ">", family="departure")
                rows = policy._decision_terminal_admissions
                self.assertEqual(key, ">")  # SHADOW: recorded only
                if quest_entrance:
                    row, = rows
                    self.assertEqual((row["terminal"][0], row["codes"], row["closed"]),
                                     ("descent-here", ["quest-entrance-target"],
                                      "terminal-refused-unserved:quest-entrance-target"))
                else:
                    self.assertEqual(rows, [])

    def test_route_terminal_is_the_committed_target(self):
        snap = board()
        policy = policy_on(snap)
        self.assertIsNone(town_terminal.rung_terminal(policy, "_descent_step", snap))
        target = Position(snap.player.position.y + 1, snap.player.position.x)
        policy._nav_ledger.commit_descent_route(target, ())
        terminal = town_terminal.rung_terminal(policy, "_descent_step", snap)
        self.assertEqual(terminal, TerminalRef("descent", (target,)))
        with patch.object(HengbotPolicy, "_step_raises_unintended_confirm",
                          side_effect=lambda board, cell: cell == target):
            self.assertEqual(town_terminal.terminal_admission(policy, snap, terminal).codes,
                             ("quest-entrance-target",))
        self.assertEqual(REFUSAL_SERVERS["quest-entrance-target"], ())


if __name__ == "__main__":
    unittest.main()
