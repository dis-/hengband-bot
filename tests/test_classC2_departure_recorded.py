"""Recorded 16:16 departure seams; no reconstruction of the whole live run.

The capture does not serialize the equipment catalog or a pre-decision pickle.
Attach its actual shelves, purchase history, ledger, target, optimization depth
and catalog-completion facts to the exported outside board. The absent optimizer
cache is declared exhausted (no pending session/actions, as recorded). This is
an explicit frozen seam, not a fidelity claim for preceding decisions. Each
board is independent; no historical board is an effect of a changed key (R4).
No screen/modal predicate or readiness predicate is mocked.
"""
import tests  # noqa: F401 -- isolate runtime writes
import ast
from dataclasses import fields
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import StoreItem, StoreState, parse_snapshot, _parse_items
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURE = Path(__file__).parent / "fixtures/classC2-departure-20261001.json.gz"


def attachment(directory, sequence=11411):
    capture = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    state = capture["state"]["modes_and_latches"]
    decision = next(row for row in capture["decisions"]
                    if row["decision_sequence"] == sequence)
    # Exact store context and player position select the deciding board among
    # the response's intermediate boards at the same turn.
    raw = next(row for row in reversed(capture["boards"])
               if row.get("turn") == decision["turn"]
               and row.get("type") == "player_turn"
               and (row.get("store") or {}).get("store_type") == decision["store_type"]
               and {"y": row["player"]["y"], "x": row["player"]["x"]} == decision["position"])
    board = parse_snapshot(raw)
    policy = _policy(directory, load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc"))
    policy._character_calibration_path.write_text(json.dumps(capture["calibration"]), encoding="utf8")
    policy.prime(board)
    for name in ("_conquest_committed", "_fundraising_cleared_for_conquest",
                 "_yeek_conquest_processed", "_town_was_in_town",
                 "_town_visit_epoch", "_observed_town_id"):
        setattr(policy, name, state[name])
    policy.consume_skill_knowledge(capture["knowledge"]["skill_exp"])
    board = policy.with_known_skill_exp(board)
    policy._refresh_carried_equipment_catalog(board)
    policy.consume_home_knowledge(tuple(_parse_items(
        capture["knowledge"]["home"]["knowledge"]["items"], protocol=3)))
    policy._equipment_transaction_failed_items.update(
        decision["equipment_optimization"]["failed_transaction_item_ids"])
    policy._target_dungeon_id = decision["over_extension"]["target_dungeon_id"]
    policy._deepest_level = board.dungeon_recall_depths[policy._target_dungeon_id]
    policy._equipment_optimization_last_depth = decision["equipment_optimization"]["optimization_depth"]
    policy._equipment_catalog.home_scan_complete = decision["equipment_optimization"]["home_scan_complete"]
    policy._home_knowledge_current = decision["equipment_optimization"]["home_knowledge_current"]
    policy._home_knowledge_invalidated = decision["equipment_optimization"]["home_knowledge_invalidated"]
    # No catalog continuation was pending when the terminal was recorded.
    policy._home_candidate_waiting = decision["home_candidate_waiting"]
    policy._char_dump_done_this_visit = True
    policy._town_store_attempted = {int(k): v for k, v in state["_town_store_attempted"].items()}
    policy._town_visit_purchases = {tuple(row) for row in state["_town_visit_purchases"]}
    policy._town_visit_purchase_quantities = {tuple(ast.literal_eval(k)): v
        for k, v in state["_town_visit_purchase_quantities"].items()}
    policy._abandoned_quest_carry_requirements = dict(state["_abandoned_quest_carry_requirements"])
    policy._town_supplier_stock_observations = {
        int(k): tuple(v) for k, v in state["_town_supplier_stock_observations"].items()}
    item_fields = {field.name for field in fields(StoreItem)}
    store_fields = {field.name for field in fields(StoreState)} - {"items"}
    for key, page in state["_town_supplier_stock"].items():
        items = []
        for item in page["items"]:
            values = {k: v for k, v in item.items() if k in item_fields}
            for name in ("known_flags", "exported_fields"):
                if name in values:
                    values[name] = frozenset(values[name])
            items.append(StoreItem(**values))
        policy._town_supplier_stock[int(key)] = StoreState(items=items,
            **{k: v for k, v in page.items() if k in store_fields})
    ledger = capture["decisions"][-1]["departure_block"]["town_ledger"]
    policy._town_visit_ledger.need_attempts.update(ledger["need_attempts"])
    for name in ("store_visits", "approach_fails", "unsatisfied_passes"):
        getattr(policy._town_visit_ledger, name).update({int(k): v for k, v in ledger[name].items()})
    policy._town_visit_ledger.blocked_stores.update(ledger["blocked_stores"])
    return policy, board, capture


class ClassC2DepartureRecordedTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.policy, self.board, self.capture = attachment(Path(directory.name))

    def test_recorded_residual_weight_has_no_safe_deposit(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "b886d8f7f1393690ce0f8b5c2f82bb733f658f808e8dee3158c7ca6834bc57b7")
        self.assertEqual((self.policy._inventory_weight(self.board),
                          self.policy._inventory_weight_limit(self.board)), (1768, 1750))
        self.assertEqual(self.policy._overweight_home_deposit(self.board), None)


if __name__ == "__main__":
    unittest.main()
