"""The 2026-10-08 Home-route stop must yield to its prepared sale plan."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.equipment_transaction_planner import (
    EquipmentTransaction,
    EquipmentTransactionPlan,
    PHASE_HOME_FINALIZE,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import _parse_items, parse_snapshot
from hengbot.model import StoreState
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HOME_SALE_MAX_HOME_WITHDRAWALS_PER_RETURN
from hengbot.policy_types import TownErrandPlan
from hengbot.warrior_optimization import load_character_calibration
from test_equipment_optimizer_sales import measurement


FIXTURE = Path(__file__).parent / "fixtures/equipment-sale-transaction-yield-20261008.json.gz"
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    "501095788ada36de15ca46ef5015f03f4a335bbc4e7a36ae58c90d195fa780d5"
)
LOOP_FIXTURE = Path(__file__).parent / "fixtures/equipment-sale-yield-loops-20261008-09.json.gz"
assert hashlib.sha256(LOOP_FIXTURE.read_bytes()).hexdigest() == (
    "c0e5686be8e4c552dac875fa65eaccb9ff6a30904683d29b75fcb575aa4189fa"
)


def _lore(data):
    result = {}
    for key, value in data["knowledge"].items():
        value["flags"] = frozenset(value["flags"])
        value["abilities"] = frozenset(value["abilities"])
        value["blows"] = tuple(
            row if isinstance(row, MonsterBlow) else MonsterBlow(**row)
            for row in value["blows"]
        )
        result[int(key)] = MonraceKnowledge(**value)
    return result


class EquipmentSaleTransactionYieldRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loop_pins = json.loads(gzip.decompress(LOOP_FIXTURE.read_bytes()))

    def test_A_recorded_refused_store_cannot_keep_sale_yield_alive(self):
        rows = self.loop_pins["captures"]["A"]["decisions"]
        self.assertEqual(
            [(row["reason"], row["key"]) for row in rows[-3:]],
            [("equipment-transaction:yield-for-equipment-sale", "\x1b"),
             ("town:entrance-step-off:policy:none-wait", "3"),
             ("town:blocked:owner-retired-burst", "5")],
        )
        policy = HengbotPolicy()
        # DECLARED CONSTRUCTED: preserve the capture's saved-list semantics;
        # only the observed sale-store refusal is injected as a terminal fact.
        sale = {
            "built": True, "blocker": None, "items": [{
                "signature": ("captured refused stock", 1, 1),
                "origin": "pack", "store_type": 2,
            }],
            "attempted": set(), "refused": set(), "withdrawals": 3,
        }
        policy._store_sale_refused.add(2)
        self.assertFalse(policy._equipment_sale_has_reachable_items(sale))

    def test_B_recorded_pending_home_knowledge_cannot_own_transaction_yield(self):
        rows = self.loop_pins["captures"]["B"]["decisions"]
        self.assertEqual(
            [(row["reason"], row["key"]) for row in rows[-3:]],
            [("home:await-fresh-knowledge", "9"),
             ("shop:approach", "1"),
             ("town:blocked:owner-retired-burst", "5")],
        )
        policy = HengbotPolicy()
        policy._home_knowledge_current = False
        policy._home_knowledge_invalidated = True
        # DECLARED CONSTRUCTED: the row records a stale Home census and a
        # pending refresh; its saved Home-origin item is retained unchanged.
        sale = {
            "built": True, "blocker": None, "items": [{
                "signature": ("captured Home stock", 1, 1),
                "origin": "home", "store_type": 2,
            }],
            "attempted": set(), "refused": set(), "withdrawals": 2,
        }
        self.assertFalse(policy._equipment_sale_has_reachable_items(sale))

    def test_C_recorded_observed_empty_shelf_retires_moved_store_stop(self):
        rows = self.loop_pins["captures"]["C"]["decisions"]
        reasons = [row["reason"] for row in rows]
        self.assertGreaterEqual(reasons.count("shop:observe-and-leave"), 4)
        self.assertGreaterEqual(reasons.count("shop:approach"), 4)
        self.assertEqual(rows[1]["town_work"][0]["work"]["producer"],
                         "policy.py:HengbotPolicy._decide")
        self.assertEqual(rows[5]["town_work"][0]["work"]["producer"],
                         "policy_home.py:HomeMixin._home_full_leave_key")

        data, _catalog, _snapshot, _evaluator, _options = measurement.recorded_inputs()
        board = parse_snapshot(
            json.loads(gzip.decompress(FIXTURE.read_bytes()))["board"], _lore(data),
        )
        policy = HengbotPolicy()
        position = board.player.position
        grids = dict(board.grids)
        grids[position] = replace(grids[position], store_number=1)
        board = replace(board, grids=grids, store=None)
        policy._town_errand_plan = TownErrandPlan(stops=[1], index=1)
        policy._shop_observation = (StoreState(1, [], 0, 0, 12), 1)
        policy.prime(board)
        # DECLARED CONSTRUCTED outside board: replay the captured no-operation
        # shelf at its captured buyer after the mutable plan cursor advanced.
        def observed_empty_shelf(_snapshot):
            policy.last_reason = "shop:observe-and-leave"
            return "\x1b"

        with patch.object(policy, "_shop", side_effect=observed_empty_shelf), \
                patch.object(policy, "_in_store_cached_shop",
                             return_value=(False, None)), \
                patch.object(policy, "_record_shop_selector_diagnostics"):
            key = policy._atomic_shop_transaction_key(board)
        self.assertEqual(key, "5", (key, policy.last_reason))
        self.assertEqual(policy.last_reason, "shop:observed-operation-uncomposable")
        self.assertIn(1, policy._town_visit_ledger.nonhome_attempted_without_effect)

    def test_built_sale_runs_before_home_route_terminal_without_losing_stripped_items(self):
        self._run_scene(home_refilled=False)

    def test_spent_withdrawal_cap_returns_turn_to_transaction(self):
        """Live 2026-10-08 22:28: after the three Home withdrawals the Home was
        full again, nothing on the sale list was reachable, and the yield kept
        sending ESC until the owner-retired burst stop."""
        self._run_scene(home_refilled=True)

    def _run_scene(self, *, home_refilled):
        pin = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        self.assertEqual(
            pin["terminal_stop"]["reason"],
            "equipment-transaction:home-route-repeat-terminal",
        )
        self.assertEqual(pin["sale_built_stop"]["equipment_sale"]["items"], 106)
        self.assertEqual(pin["sale_built_stop"]["equipment_sale"]["withdrawals"], 3)

        data, catalog, _recorded_snapshot, _evaluator, _options = (
            measurement.recorded_inputs()
        )
        lore = _lore(data)
        board = parse_snapshot(pin["board"], lore)
        policy = HengbotPolicy(monrace_knowledge=lore)
        policy.consume_skill_knowledge(data["skill"])
        board = policy._with_cached_skill_exp(board)
        policy.prime(board)
        home = tuple(_parse_items(
            data["home"]["knowledge"]["items"],
            protocol=data["home"]["protocol_version"],
        ))
        policy.consume_home_knowledge(home)
        policy._equipment_catalog = catalog  # TEST_FAKERY_LINT_ALLOW: private-state-injected: replay reconstructs the captured optimizer catalogue
        policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
        policy._home_knowledge_items = home
        policy._home_knowledge_current = True
        policy._home_knowledge_invalidated = False
        policy._home_scan_item_count = len(home)
        policy._home_capacity_observation = (
            240, 240, policy._effective_town_id(board),
        )

        with tempfile.TemporaryDirectory(prefix="sale-transaction-yield-") as directory:
            calibration_path = Path(directory) / "character-calibration.json"
            calibration_path.write_text(
                json.dumps(data["calibration"]), encoding="utf-8",
            )
            policy._character_calibration = load_character_calibration(
                calibration_path
            )
            policy._character_calibration_loaded = True
            policy._ensure_equipment_sale_session(board)
            policy._equipment_sale_session["sale_needed"] = True
            policy._build_equipment_sale_session(board)

        self.assertTrue(policy._equipment_sale_session["built"])
        self.assertEqual(len(policy._equipment_sale_session["items"]), 106)

        # DECLARED CONSTRUCTED transaction checkpoint: the captured stop did
        # not retain a policy checkpoint, so reconstruct the blocked Home
        # deposit and its stripped-item ownership from the recorded failure.
        transaction = EquipmentTransactionSession(EquipmentTransactionPlan((
            EquipmentTransaction(
                PHASE_HOME_FINALIZE, "deposit", "live-item", "body", "live-identity",
            ),
        ), (), 0))
        transaction.block("home-route-unavailable")
        held_items = [("live-identity", "body")]
        policy._equipment_transaction_session = transaction
        policy._equipment_transaction_owned_items = list(held_items)

        key = policy.choose_key(board)

        self.assertEqual(policy.last_reason, "shop:travel")
        self.assertTrue(key.startswith("\x1b`n"))
        self.assertIs(policy._equipment_transaction_session, transaction)
        self.assertEqual(policy._equipment_transaction_owned_items, held_items)
        self.assertEqual(transaction.blockers, ["home-route-unavailable"])
        self.assertIsNone(policy._equipment_transaction_route_terminal)
        sale = policy._equipment_sale_session
        self.assertEqual(sale["withdrawals"], 3)  # Three planned batch slots.
        self.assertEqual(len(sale["batch"]), 3)
        self.assertEqual(sale["attempted"], set(sale["batch"]))

        # DECLARED CONSTRUCTED batch completion: three withdrawals/sales have
        # freed Home slots. The same blocked deposit is executable again.
        policy._pending_disposal_item = None
        policy._home_pending_batch.clear()
        if home_refilled:
            # DECLARED CONSTRUCTED refill: the freed slots were used again, so
            # the Home is full while this return's withdrawal cap is spent.
            sale["withdrawals"] = HOME_SALE_MAX_HOME_WITHDRAWALS_PER_RETURN
            policy._home_capacity_observation = (
                240, 240, policy._effective_town_id(board),
            )
            self.assertTrue(policy._home_is_full(board))
            self.assertFalse(policy._equipment_sale_has_unstarted_items())
            self.assertFalse(
                policy._equipment_sale_should_yield_transaction(board)
            )
            self.assertFalse(sale["transaction_yield"])
            self.assertIs(policy._equipment_transaction_session, transaction)
            self.assertEqual(policy._equipment_transaction_owned_items, held_items)
            return
        policy._home_capacity_observation = (
            239, 240, policy._effective_town_id(board),
        )
        self.assertFalse(policy._equipment_sale_should_yield_transaction(board))
        self.assertIs(policy._equipment_transaction_session, transaction)
        self.assertTrue(transaction.executable)
        self.assertEqual(transaction.current_action.kind, "deposit")
        self.assertEqual(transaction.blockers, [])


if __name__ == "__main__":
    unittest.main()
