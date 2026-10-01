"""Frozen departure seam, not a replay of the prior 7,520 decisions.

Attach the recorded supplies, depth, shelf memories and visit ledger to the
real outside board. Stop at the first changed route key; no later historical
board is claimed as the effect of that key. No screen/modal code is changed.
"""
import tests  # noqa: F401 -- isolate all runtime writes
import hashlib
import json
from dataclasses import fields
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from hengbot.model import StoreItem, StoreState, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURE = Path(__file__).parent / "fixtures/live36-weight.json"


def attachment(directory):
    capture = json.loads(FIXTURE.read_text(encoding="utf8"))
    board = parse_snapshot(capture["stop"])
    policy = _policy(directory, load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc"))
    policy.prime(board)
    stop = capture["decisions"][-1]
    policy._equipment_optimization_last_depth = stop["equipment_optimization"]["optimization_depth"]
    policy._equipment_optimization_preparation = SimpleNamespace(blockers=(), result=None)
    policy._equipment_catalog.home_scan_complete = True
    policy._home_knowledge_current = capture["attachment"]["home_knowledge_current"]
    policy._home_scan_item_count = stop["home_scan"]["item_count"]
    policy._town_store_attempted = {int(k): v for k, v in capture["attachment"]["town_store_attempted"].items()}
    policy._abandoned_quest_carry_requirements = dict(capture["attachment"]["abandoned_carry"])
    policy._town_visit_purchases = {tuple(row) for row in capture["attachment"]["purchases"]}
    policy._town_supplier_stock_observations = {
        int(k): tuple(v) for k, v in capture["attachment"]["stock_observations"].items()}
    # Recorder serializes actual dataclasses. Rehydrate their declared fields;
    # this is shelf memory, not a fabricated live store screen.
    item_fields = {f.name for f in fields(StoreItem)}
    store_fields = {f.name for f in fields(StoreState)} - {"items"}
    for key, stock in capture["shelves"].items():
        items = []
        for row in stock["items"]:
            values = {k: v for k, v in row.items() if k in item_fields}
            for name in ("known_flags", "exported_fields"):
                if name in values:
                    values[name] = frozenset(values[name])
            items.append(StoreItem(**values))
        policy._town_supplier_stock[int(key)] = StoreState(
            items=items, **{k: v for k, v in stock.items() if k in store_fields})
    ledger = stop["departure_block"]["town_ledger"]
    policy._town_visit_ledger.need_attempts.update(ledger["need_attempts"])
    for name in ("store_visits", "approach_fails", "unsatisfied_passes"):
        getattr(policy._town_visit_ledger, name).update({int(k): v for k, v in ledger[name].items()})
    return policy, board, capture


class Live36WeightTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.policy, self.board, self.capture = attachment(Path(directory.name))

    def test_frozen_stop_and_retained_quantities(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                         "b9d78eefbc220d7accb30eeb96433cae91414a45c94ff5dcce869addc9322ff3")
        stop = self.capture["decisions"][-1]
        self.assertEqual((stop["decision_sequence"], stop["key"], stop["reason"]),
                         (7520, "1", "town:blocked:departure-unsatisfiable"))
        self.assertEqual(stop["departure_block"]["failed"], ["inventory_weight_ready"])
        self.assertEqual((self.policy._inventory_weight(self.board),
                          self.policy._inventory_weight_limit(self.board)), (1780, 1750))
        self.assertEqual([(i.slot, self.policy._retention_reservation(self.board, i))
                          for i in self.board.inventory],
                         [("a", 5), ("b", 2), ("c", 10), ("d", 4), ("e", 15),
                          ("f", 10), ("g", 6), ("h", 1), ("i", 0), ("j", 0),
                          ("k", 0), ("l", 99)])
        self.assertEqual((self.capture["home"]["store"]["stock_num"],
                          self.capture["home"]["store"]["capacity"]), (57, 240))

    def test_recorded_surface_has_a_safe_weight_deposit(self):
        deposit = self.policy._overweight_home_deposit(self.board)
        self.assertIsNotNone(deposit)
        self.assertEqual((deposit.slot, deposit.count), ("k", 2))

    def test_weight_owner_survives_prior_successful_attempts(self):
        self.policy._town_claims_active(self.board)
        self.assertEqual("weight-overload" in self.policy._town_claim_categories, True)


if __name__ == "__main__":
    unittest.main()
