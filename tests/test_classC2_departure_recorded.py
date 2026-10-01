"""Recorded 16:16 departure seams; no reconstruction of the whole live run.

The capture does not serialize the equipment catalog or a pre-decision pickle.
Attach its actual Home/skill knowledge, shelves, purchase history, ledger,
conquest latch, target, optimization depth and catalog-completion facts to the
exported outside board. The optimizer runs with the run's own calibration.
This is an explicit frozen seam, not a fidelity claim for preceding decisions. Each
board is independent; no historical board is an effect of a changed key (R4).
No screen/modal predicate or readiness predicate is mocked.
"""
import tests  # noqa: F401 -- isolate runtime writes
import ast
from dataclasses import fields, replace
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
    if sequence >= 11399:
        # The full knowledge list predates the recorded dkdjdd deposit. Both
        # diggers really left the pack after that exact recorded key; add their
        # observed Home moves to retain the live catalog's 40 equipment items.
        before = next(parse_snapshot(row) for row in capture["boards"]
                      if row.get("turn") == 1493262 and row.get("type") == "player_turn")
        for item in before.inventory:
            if item.slot in "jk":
                policy._equipment_catalog.record_home_deposit(item, intent=(
                    before.turn, item.slot, policy._item_signature(item),
                    item.count, item.charges, len(before.inventory)))
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
    # Load the actual calibration before a checkpoint is captured: restored
    # runtime paths are intentionally isolated from the original temp files.
    policy._validated_character_calibration(board)
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

    def test_recorded_deposit_and_residual_supply_quantities(self):
        before = next(parse_snapshot(row) for row in self.capture["boards"]
                      if row.get("turn") == 1493262 and row.get("type") == "player_turn")
        self.assertEqual(self.policy._inventory_weight(before), 1983)
        self.assertEqual([(item.slot, item.weight) for item in before.inventory
                          if item.slot in "djk"], [("d", 5), ("j", 60), ("k", 150)])
        recorded = next(row for row in self.capture["decisions"]
                        if row["decision_sequence"] == 11398)
        self.assertEqual(recorded["key"], "dkdjdd\x1b")
        self.assertEqual([(item.slot, self.policy._retention_reservation(self.board, item))
                          for item in self.board.inventory],
                         [("a", 5), ("b", 10), ("c", 3), ("d", 15), ("e", 10),
                          ("f", 6), ("g", 1), ("h", 0), ("i", 99)])
        self.assertEqual(self.policy._total_identify_staff_charges(self.board), 20)
        self.assertEqual(self.policy._find_surplus_identify_staff(
            self.board, for_weight_overload=True), None)
        home = next(row["store"] for row in reversed(self.capture["boards"])
                    if (row.get("store") or {}).get("store_type") == 7)
        self.assertEqual((home["stock_num"], home["capacity"]), (61, 240))
        self.assertEqual(len(self.policy._equipment_catalog.items), 40)

    def test_public_stop_board_offers_deeper_guardian_remedy_after_restore(self):
        board = self.board
        saved = checkpoint(self.policy)
        for policy in (self.policy, restore_checkpoint(HengbotPolicy, saved)):
            self.assertEqual(policy._town_recall_destination(board, guardian_gate=False),
                             ("yeek-cave", 2))
            self.assertEqual(policy._guardian_floor_blocked(board, 2, 12), True)
            self.assertEqual(policy._guardian_floor_blocked(board, 3, 18), False)
            self.assertEqual(policy._missing_required_abilities(board, 18), frozenset())
            key = policy.choose_key(board)
            historical = self.capture["decisions"][-1]
            print("CLASS C2 FIRST DIFFERENCE", "live", repr(historical["key"]),
                  historical["reason"], "replay", repr(str(key)), policy.last_reason,
                  "target", policy._target_dungeon_id)
            self.assertEqual((str(key), policy.last_reason),
                ("1", "town:entrance-step-off:town:unsafe-recall-fallback"))
            self.assertEqual((policy._alternate_dungeon, policy._target_dungeon_id), (3, 3))
            self.assertEqual(policy._conquest_committed, None)
            self.assertEqual(policy._town_blocked_reason, None)
            self.assertEqual(policy._pending_recall_dungeon_id, None)
            # These are the refusal's own facts on the deciding board. The
            # fallback selects a target, never removes the hard weight gate.
            self.assertEqual(policy._departure_block["failed"],
                ["inventory_weight_ready", "recall_landing_not_guardian_blocked"])
            self.assertEqual(policy._inventory_overweight(board), True)
            # Stop at this changed decision: no future live effect is claimed.

    def test_no_alternate_keeps_visible_stop_and_weight_requirement(self):
        # Named counterfactual: only Angband and the refused Yeek cave entered.
        # All pack/equipment/weight facts are still the recorded stop board.
        board = replace(self.board, entered_dungeon_ids=(1, 2))
        key = self.policy.choose_key(board)
        self.assertEqual((str(key), self.policy.last_reason),
                         ("1", "town:blocked:guardian-bounce-no-alternate"))
        self.assertEqual(self.policy._target_dungeon_id, 2)
        self.assertEqual(self.policy._inventory_overweight(board), True)

    def test_any_remaining_safe_surplus_goes_home_before_guardian_switch(self):
        # Named counterfactual: retain one of the phase-door scrolls that the
        # live deposit removed. Its real exported item is copied to free slot
        # j on the stop board. The 5 removed weight cannot clear the 23 excess;
        # nevertheless all available surplus must be deposited before stopping.
        before = next(parse_snapshot(row) for row in self.capture["boards"]
                      if row.get("turn") == 1493262 and row.get("type") == "player_turn")
        phase = next(item for item in before.inventory if item.slot == "d")
        board = replace(self.board, inventory=(*self.board.inventory, replace(phase, slot="j")))
        saved = checkpoint(self.policy)
        for policy in (self.policy, restore_checkpoint(HengbotPolicy, saved)):
            deposit = policy._overweight_home_deposit(board)
            self.assertEqual((deposit.slot, deposit.count, deposit.weight), ("j", 1, 5))
            self.assertEqual(policy._inventory_weight(board), 1773)
            key = policy.choose_key(board)
            self.assertEqual((str(key), policy.last_reason), ("\x1b`n(.", "shop:travel"))
            self.assertEqual(policy._shopping_approach_store_type, 7)
            self.assertEqual(policy._target_dungeon_id, 2)
            self.assertEqual(policy._town_blocked_reason, None)


if __name__ == "__main__":
    unittest.main()
