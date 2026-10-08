"""Recorded sale observations remain useful after sale/transaction yielding was removed."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.model import parse_snapshot
from hengbot.model import STORE_HOME, StoreState
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, TownErrandPlan
from test_equipment_optimizer_sales import measurement


FIXTURE = Path(__file__).parent / "fixtures/equipment-sale-transaction-yield-20261008.json.gz"
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    "501095788ada36de15ca46ef5015f03f4a335bbc4e7a36ae58c90d195fa780d5"
)
LOOP_FIXTURE = Path(__file__).parent / "fixtures/equipment-sale-yield-loops-20261008-09.json.gz"
assert hashlib.sha256(LOOP_FIXTURE.read_bytes()).hexdigest() == (
    "c0e5686be8e4c552dac875fa65eaccb9ff6a30904683d29b75fcb575aa4189fa"
)
BURST_FIXTURE = Path(__file__).parent / "fixtures/equipment-sale-owner-retired-burst-20261009.json.gz"
assert hashlib.sha256(BURST_FIXTURE.read_bytes()).hexdigest() == (
    "f8feff76b2627ca743c3d710c4087483ec02acece499c9e0fbac1d37721f181f"
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

    def test_D_recorded_shopping_visit_resumes_selected_carried_sale(self):
        pin = json.loads(gzip.decompress(BURST_FIXTURE.read_bytes()))
        rows = pin["decisions"]
        observe = next(row for row in rows if row["decision_sequence"] == 113)
        repeat = next(row for row in rows if row["decision_sequence"] == 116)
        self.assertEqual(observe["reason"], "shop:observe-and-leave")
        self.assertEqual(observe["shop_selector"]["rejection_reason"],
                         "observed-page-nothing-wanted")
        self.assertEqual(observe["store_visit"]["owner"], "town-errand")
        self.assertEqual(observe["store_visit"]["purpose"], "shopping")
        self.assertEqual(observe["equipment_sale"]["active_store"], 2)
        self.assertEqual(observe["equipment_sale"]["withdrawals"], 20)
        self.assertEqual((repeat["reason"], repeat["key"]),
                         ("shop:observe-and-leave", "\x1b"))

        board = parse_snapshot(pin["store_page"], {})
        policy = HengbotPolicy()
        policy.prime(board)
        candidate = next(
            item for item in board.inventory
            if (policy._store_accepts_sale(board.store.store_type, item)
                and not item.is_digging_tool)
        )
        signature = policy._item_signature(candidate)
        # DECLARED CONSTRUCTED: the capture records the selected sale store,
        # current pack, and shopping visit, but not the private pending item
        # signature. Rebuild the in-flight pack sale from that saved selection
        # and the still-carried store-2 stock; the purchase-only stop had lost
        # the pending pointer before the observed shelf was composed.
        policy._equipment_sale_session = {
            "built": True, "blocker": None,
            "items": [{"signature": signature, "origin": "pack",
                       "store_type": board.store.store_type}],
            "attempted": {signature}, "refused": set(),
            "withdrawals": observe["equipment_sale"]["withdrawals"],
            "active_store": board.store.store_type,
        }
        policy._store_visit = StoreVisit(
            owner=observe["store_visit"]["owner"],
            purpose=observe["store_visit"]["purpose"],
            store_type=board.store.store_type,
        )
        key = policy._shop(board)
        self.assertTrue(key.startswith("{"), (key, policy.last_reason))
        self.assertEqual(policy.last_reason, "shop:batch-inscribe")
        self.assertEqual(policy._execution_offers_for()[-1][:2],
                         (key, "shop-sell"))
        self.assertEqual(policy._pending_disposal_item, signature)
        self.assertEqual(policy._batch_sell_pending["phase"], "await-inscription")

        # DECLARED CONSTRUCTED continuation: apply the observed sale tag to
        # the captured carried candidate, then replay the existing batch-sale
        # owner at its next observation boundary.
        tag = policy._batch_sell_pending["entries"][0]["tag"]
        tagged_candidate = replace(candidate, inscription=f"@{tag}")
        tagged_board = replace(
            board,
            inventory=tuple(
                tagged_candidate if item.slot == candidate.slot else item
                for item in board.inventory
            ),
        )
        sale_key = policy._batch_sell_key(tagged_board)
        # The captured pack already uses this tag on another carried item.
        # The existing safety rule refuses the ambiguous sale and latches the
        # buyer, which bounds this sale attempt without changing J-D selection.
        self.assertEqual(sale_key, "\x1b")
        self.assertEqual(policy.last_reason,
                         "shop:sale-inscription-ambiguous-leave")
        self.assertIn(board.store.store_type, policy._store_sale_refused)
        self.assertIsNone(policy._equipment_sale_next_store(tagged_board))
        self.assertFalse(policy._equipment_sale_has_reachable_items(
            policy._equipment_sale_session, tagged_board,
        ))

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

    def test_0143_capture_repeated_selection_does_not_count_planned_withdrawals(self):
        pin = json.loads(gzip.decompress(BURST_FIXTURE.read_bytes()))
        observed = next(
            row for row in pin["decisions"]
            if row.get("equipment_sale", {}).get("withdrawals") == 20
        )
        self.assertEqual(observed["equipment_sale"]["withdrawals"], 20)
        policy = HengbotPolicy()
        signatures = [(f"captured planned sale {i}", 1, 1) for i in range(3)]
        policy._equipment_sale_session = {
            "built": True, "items": [
                {"signature": sig, "origin": "home", "store_type": 2,
                 "weight": 1} for sig in signatures
            ],
            "attempted": set(), "planned": set(), "refused": set(),
            "withdrawals": 9,
            "active_store": None,
        }
        policy._home_available = lambda _snapshot: True
        policy._inventory_weight_limit = lambda _snapshot: 100
        policy._inventory_weight = lambda _snapshot: 0
        board = SimpleNamespace(inventory=[])

        before = (
            policy._equipment_sale_session["withdrawals"],
            set(policy._equipment_sale_session["attempted"]),
        )
        self.assertEqual(policy._equipment_sale_next_store(board), STORE_HOME)
        self.assertEqual(
            (policy._equipment_sale_session["withdrawals"],
             policy._equipment_sale_session["attempted"]), before,
        )
        self.assertEqual(policy._equipment_sale_next_store(board), STORE_HOME)
        self.assertEqual(policy._equipment_sale_next_store(board), STORE_HOME)
        self.assertEqual(
            (policy._equipment_sale_session["withdrawals"],
             policy._equipment_sale_session["attempted"]), before,
        )
        self.assertEqual(
            policy._equipment_sale_session["planned"], set(signatures)
        )

    def test_B_recorded_pending_home_knowledge_still_blocks_stale_sale(self):
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

if __name__ == "__main__":
    unittest.main()
