"""Weight relief root fix (soak c4-a life-014, 2026-10-21 04:53 and 05:00).

The 05:00 stop: three speed potions took the pack from 1749 to 1761 over the
1750 limit; Home showed 239/240, but a Home-full relief left pending by the
2147 skip ('surplus-target-unobserved') hid every Home deposit, so neither the
weight-overload deposit nor the overweight-surplus sale was offered and the
departure ended in the generic 'town:blocked:departure-unsatisfiable'.
"""
from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime state for standalone module runs
import gzip
import inspect
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _parse_items, _policy_final_stop_banner
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS
from hengbot.policy_town import VISIT_CLOSABLE_REASONS
from hengbot.protocol import snapshot_protocol_version
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "weight-relief-root-20261021.jsonl.gz"
LIMIT = 1750
# Recorded Home-full relief take that the 2147 skip retired (its signature is
# not printed by the capture; any name absent from Home reproduces the skip).
SKIPPED = ("兵隊アリの死体", 1, 1)


class WeightReliefRootRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.boards = {(row["capture"], row["index"]): row["board"]
                      for row in rows if "board" in row}
        cls.decisions = next(row["decisions"] for row in rows if "decisions" in row)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _policy_for(self, capture, index):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        snapshot = parse_snapshot(self.boards[(capture, index)], self.monrace)
        policy.prime(snapshot)
        policy._skill_exp_cache = (0, 0, snapshot.player.level,
                                   policy._town_visit_epoch)
        return policy, snapshot

    def _stale_relief_board(self):
        """DECLARED wall: the process state after the recorded 2147 skip.

        Home catalogue = recorded knowledge board 81 (239 items); capacity =
        recorded Home page 82 (239/240); relief = pending, its take skipped,
        begun on the overweight pack as _home_full_relief_key begins it and
        with no ware taken (measured: the capture's decisions 2107..2146 hold
        no relief take; 239 is the 2115 catalogue withdrawal).
        """
        policy, snapshot = self._policy_for("20261021-050011", 86)
        town = policy._effective_town_id(snapshot)
        knowledge = self.boards[("20261021-050011", 81)]
        policy._adopt_home_catalogue(tuple(_parse_items(
            knowledge["knowledge"]["items"],
            protocol=snapshot_protocol_version(knowledge))))
        page = self.boards[("20261021-050011", 82)]["store"]
        policy._home_capacity_observation = (page["stock_num"], page["capacity"], town)
        entries = tuple((policy._item_signature(item), item.count, count)
                        for item in snapshot.inventory
                        if item.weight > 0
                        and (count := policy._retention_surplus(snapshot, item)) > 0)
        policy._home_full_relief = {
            "deposits": entries, "remaining": max(1, len(entries)),
            "sale": None, "withdrawn": False,
            "town": town, "skipped": {SKIPPED: "surplus-target-unobserved"},
        }
        return policy, snapshot

    def test_capture_pins_the_skip_and_the_generic_block(self):
        self.assertEqual(
            [(row["decision_sequence"], row["reason"]) for row in self.decisions][-6:],
            [(2147, "home:full-skip:surplus-target-unobserved"),
             (2148, "home-errand:request-knowledge:full-home-discard"),
             (2149, "policy:none-store-exit"),
             (2150, "periodic:game-save"),
             (2151, "periodic:character-dump"),
             (2152, "town:blocked:departure-unsatisfiable")])
        self.assertEqual(self.decisions[-3]["failed"], ["inventory_weight_ready"])
        page = self.boards[("20261021-050011", 82)]["store"]
        self.assertEqual((page["store_type"], page["stock_num"], page["capacity"]),
                         (7, 239, 240))
        policy, snapshot = self._policy_for("20261021-050011", 86)
        self.assertEqual((policy._inventory_weight(snapshot),
                          policy._inventory_weight_limit(snapshot)), (1761, LIMIT))

    def test_stale_relief_releases_to_the_weight_deposit(self):
        policy, snapshot = self._stale_relief_board()
        needs = [(need.store_type, need.category)
                 for need in policy._town_need_candidates(snapshot)]
        self.assertIn((7, "weight-overload"), needs)
        self.assertIsNone(policy._home_full_relief)
        key = policy.choose_key(snapshot)
        self.assertEqual((str(key), policy.last_reason),
                         ("5", "home:weight-overload-deposit"))
        relief = policy._weight_relief_selection(snapshot)
        self.assertEqual((relief.route, relief.excess, relief.home_room),
                         ("deposit", 11, True))
        self.assertEqual(relief.deposits[0].slot, "o")  # the 200 pickaxe

    def test_stale_relief_releases_at_the_relief_producer(self):
        policy, snapshot = self._stale_relief_board()
        self.assertIsNone(policy._home_full_relief_key(snapshot))
        self.assertIsNone(policy._home_full_relief)
        self.assertEqual(policy._find_home_deposit(snapshot).slot, "o")

    def test_control_full_home_keeps_the_relief(self):
        policy, snapshot = self._stale_relief_board()
        town = policy._effective_town_id(snapshot)
        policy._home_capacity_observation = (240, 240, town)  # CONSTRUCTED full
        relief = policy._weight_relief_selection(snapshot)
        self.assertEqual(relief.route, "sell-or-destroy")
        self.assertFalse(policy._release_home_full_relief_for_weight(snapshot, relief))
        self.assertIsNotNone(policy._home_full_relief)

    def test_relief_that_took_a_ware_keeps_its_freed_slot(self):
        # DECLARED: the same relief after one take (as C4-A 2026-10-20 decision
        # 15 of the one-shot replay: the relief's own take freed the slot).
        policy, snapshot = self._stale_relief_board()
        policy._home_full_relief["remaining"] -= 1
        relief = policy._weight_relief_selection(snapshot)
        self.assertEqual((relief.route, relief.home_room), ("deposit", True))
        self.assertFalse(policy._release_home_full_relief_for_weight(snapshot, relief))
        self.assertIsNotNone(policy._home_full_relief)
        self.assertIsNone(policy._find_home_deposit(snapshot))

    def test_selector_gate_is_the_overweight_test_of_the_deposits(self):
        # The selector asks the overweight test the deposit candidates own
        # (a caller holding that answer gets the same deposit order).
        policy, snapshot = self._policy_for("20261021-050011", 57)
        self.assertFalse(policy._inventory_overweight(snapshot))
        with patch.object(policy, "_inventory_overweight", return_value=True):
            expected = tuple(policy._weight_deposit_candidates(snapshot))
            deposits = policy._weight_relief_selection(snapshot, plan=False).deposits
        self.assertTrue(expected)
        self.assertEqual(deposits, expected)

    def test_control_unobserved_home_capacity_keeps_the_relief(self):
        policy, snapshot = self._stale_relief_board()
        policy._home_capacity_observation = None  # CONSTRUCTED: no capacity fact
        relief = policy._weight_relief_selection(snapshot)
        self.assertEqual((relief.route, relief.home_room), ("sell-or-destroy", False))
        self.assertFalse(policy._release_home_full_relief_for_weight(snapshot, relief))
        self.assertIsNotNone(policy._home_full_relief)

    def test_control_retained_items_are_never_shed(self):
        policy, snapshot = self._stale_relief_board()
        relief = policy._weight_relief_selection(snapshot)
        shed = {item.slot: policy._retention_surplus(snapshot, item)
                for item in relief.deposits}
        shed.update({entry[2].slot: entry[3] for entry in relief.surplus})
        # cure c, teleport h, Stone to Mud j, bolts p: held by their reasons.
        for slot in "chjp":
            self.assertNotIn(slot, shed)
        self.assertEqual(shed["b"], 3)   # speed 13, reservation 10
        self.assertEqual(shed["i"], 4)   # recall 11, reservation 7

    def test_control_not_overweight_board_is_unchanged(self):
        policy, snapshot = self._policy_for("20261021-050011", 57)
        self.assertEqual(policy._inventory_weight(snapshot), 1646)
        relief = policy._weight_relief_selection(snapshot)
        self.assertEqual((relief.route, relief.deposits, relief.surplus),
                         ("none", (), ()))
        needs = {need.category for need in policy._town_need_candidates(snapshot)}
        self.assertFalse(needs & {"weight-overload", "overweight-surplus"})

    def _retained_only_board(self):
        """DECLARED: the 04:53 board after its one sheddable stack (recall f,
        4 surplus) was deposited; the weapons m/n/o stay with identification."""
        policy, snapshot = self._policy_for("20261021-045344", 70)
        inventory = tuple(replace(item, count=6) if item.slot == "f" else item
                          for item in snapshot.inventory)
        snapshot = replace(snapshot, inventory=inventory)
        town = policy._effective_town_id(snapshot)
        policy._home_capacity_observation = (238, 240, town)
        return policy, snapshot

    def test_retained_only_weight_is_named_with_numbers(self):
        policy, snapshot = self._retained_only_board()
        relief = policy._weight_relief_selection(snapshot)
        self.assertEqual((relief.route, relief.weight, relief.limit, relief.excess),
                         ("retained-only", 1908, LIMIT, 158))
        held = {slot: reason for slot, _, _, reason in relief.retained}
        self.assertEqual({held[slot] for slot in "mno"}, {"identification-flow"})
        self.assertTrue(policy._record_weight_relief_retained_only(snapshot))
        record = json.loads(policy._overweight_surplus_record_path.read_text(
            encoding="utf8").splitlines()[-1])
        self.assertEqual((record["reason"], record["weight"], record["limit"],
                          record["excess"]),
                         ("town:blocked:overweight-retained-only", 1908, LIMIT, 158))
        self.assertIn("town:blocked:overweight-retained-only", POLICY_FINAL_STOP_REASONS)
        self.assertIn("only retained items remain above the weight limit",
                      _policy_final_stop_banner("town:blocked:overweight-retained-only"))
        self.assertIn("overweight-retained-only", VISIT_CLOSABLE_REASONS)

    def test_generic_departure_block_is_named_when_only_retained_weight_remains(self):
        policy, snapshot = self._retained_only_board()
        policy._visit_departure_committed = "departure-unsatisfiable"  # DECLARED
        policy._town_blocked_reason = "departure-unsatisfiable"
        policy._town_blocked_key(snapshot)
        self.assertEqual(policy.last_reason, "town:blocked:overweight-retained-only")

    def test_control_sheddable_weight_is_not_named_retained(self):
        policy, snapshot = self._policy_for("20261021-045344", 70)
        policy._home_capacity_observation = (238, 240, policy._effective_town_id(snapshot))
        self.assertEqual(policy._weight_relief_selection(snapshot).route, "deposit")
        self.assertFalse(policy._record_weight_relief_retained_only(snapshot))
        policy._visit_departure_committed = "departure-unsatisfiable"  # DECLARED
        policy._town_blocked_reason = "departure-unsatisfiable"
        policy._town_blocked_key(snapshot)
        self.assertEqual(policy.last_reason, "town:blocked:departure-unsatisfiable")

    def test_every_shedding_site_selects_through_the_selector(self):
        """Structural check: a site that asks a candidate list directly fails."""
        policy, snapshot = self._stale_relief_board()
        outside = []

        def guard(original):
            def wrapper(*args, **kwargs):
                names = {frame.function for frame in inspect.stack()[1:]}
                if "_weight_relief_selection" not in names:
                    outside.append((original.__name__, inspect.stack()[1].function))
                return original(*args, **kwargs)
            return wrapper

        with patch.object(policy, "_weight_deposit_candidates",
                          guard(policy._weight_deposit_candidates)), \
                patch.object(policy, "_overweight_surplus_candidates",
                             guard(policy._overweight_surplus_candidates)):
            policy._town_need_candidates(snapshot)
            self.assertEqual(policy._overweight_home_deposit(snapshot).slot, "o")
            policy._ammo_procurement_target(snapshot, for_retention=True)
            town = policy._effective_town_id(snapshot)
            policy._home_capacity_observation = (240, 240, town)
            policy._overweight_surplus_disposal = {"town": town}
            policy._town_need_candidates(snapshot)
            policy._overweight_surplus_sale_key(snapshot)
            policy.choose_key(snapshot)
        self.assertEqual(outside, [])


if __name__ == "__main__":
    unittest.main()
