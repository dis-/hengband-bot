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
from recorded_equipment_decisions import recorded_equipment_decisions
from xbow_pref_walls import apply_shelf_wall

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
        # fixer-reconcile-prompt.txt STEP 2: weight/guardian remedies are the
        # subject; the captured kit decision is an input, including restores.
        self.enterContext(recorded_equipment_decisions("classC2"))
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.policy, self.board, self.capture = attachment(Path(directory.name))
        # Declared wall (tests/xbow_pref_walls.py): shelves without plain
        # bolts, so the 2026-10-02 crossbow swap does not apply here.
        apply_shelf_wall(self.policy)

    def test_recorded_residual_weight_deposits_exactly_four_shots_after_restore(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "b886d8f7f1393690ce0f8b5c2f82bb733f658f808e8dee3158c7ca6834bc57b7")
        self.assertEqual((self.policy._inventory_weight(self.board),
                          self.policy._inventory_weight_limit(self.board)), (1768, 1750))
        saved = checkpoint(self.policy)
        for policy in (self.policy, restore_checkpoint(HengbotPolicy, saved)):
            deposit = policy._overweight_home_deposit(self.board)
            self.assertIsNotNone(deposit)
            self.assertEqual((deposit.slot, deposit.count, deposit.weight), ("i", 99, 5))
            self.assertEqual(policy._retention_surplus(self.board, deposit), 4)
            self.assertEqual([(i.slot, n) for i, n in policy._home_deposit_batch(
                self.board, deposit)], [("i", 4)])
            self.assertEqual(policy._home_deposit_key(self.board, deposit), "di4\r")
            self.assertEqual(policy._inventory_weight(self._after_shots()), 1748)

    def _after_shots(self):
        # Constructed effect board of the exact four-shot deposit above. It is
        # not a later historical input row or a replay beyond first divergence.
        return replace(self.board, inventory=tuple(
            replace(i, count=95) if i.slot == "i" else i
            for i in self.board.inventory))

    def test_next_visit_buys_only_fitting_count_and_leaves_deposit_home(self):
        # Constructed next visit: no historical continuation is replayed. The
        # current kit is unchanged; five shots were consumed during a dive.
        pack = next(i for i in self.board.inventory if i.slot == "i")
        shared = {f.name for f in fields(StoreItem)} & {f.name for f in fields(type(pack))}
        ware = StoreItem(letter="a", price=1, **{
            name: getattr(pack, name) for name in shared})
        board = replace(self._after_shots(), inventory=tuple(
            replace(i, count=90) if i.slot == "i" else i
            for i in self.board.inventory), store=StoreState(2, [ware]))
        policy = HengbotPolicy()
        policy.consume_home_knowledge((replace(pack, slot="a", count=4),))
        saved = checkpoint(policy)
        for policy in (policy, restore_checkpoint(HengbotPolicy, saved)):
            self.assertIs(policy._next_purchase_unreserved(board), ware)
            self.assertEqual(policy._purchase_quantity(board, ware), 5)
            self.assertEqual(policy._ammo_procurement_target(board, ware), 95)
            topped_up = replace(board, inventory=self._after_shots().inventory)
            self.assertEqual(policy._inventory_weight(topped_up), 1748)
            self.assertEqual(policy._purchase_quantity(topped_up, ware), 0)
            self.assertIsNone(policy._next_purchase_unreserved(topped_up))
            self.assertIsNone(policy._home_ammo_top_up(topped_up))
            self.assertEqual(policy._procurement_missing_amount(topped_up, ware), 0)
            self.assertFalse(any(need.category in {"ammo", "ammo-home-first"}
                                 for need in policy._enumerate_town_needs(topped_up)))
            empty = replace(board, inventory=tuple(i for i in board.inventory if not i.is_ammo))
            self.assertIs(policy._next_purchase_unreserved(empty), ware)
            self.assertEqual(policy._purchase_quantity(empty, ware), 95)

    def test_overweight_matching_ammo_for_each_launcher_deposits_minimum(self):
        # Constructed launcher/ammo substitutions, preserving the recorded
        # kit weight and overload; no weapon comparison or ready gate is walled.
        for ammo_tval, launcher_sval in ((16, 2), (17, 12), (18, 23)):
            board = replace(self.board,
                inventory=tuple(replace(i, tval=ammo_tval) if i.slot == "i" else i
                                for i in self.board.inventory),
                equipment=tuple(replace(i, sval=launcher_sval) if i.slot == "bow" else i
                                for i in self.board.equipment))
            policy = restore_checkpoint(HengbotPolicy, checkpoint(self.policy))
            saved = checkpoint(policy)
            for policy in (policy, restore_checkpoint(HengbotPolicy, saved)):
                deposit = policy._overweight_home_deposit(board)
                self.assertEqual((deposit.slot, deposit.weight), ("i", 5))
                self.assertEqual(policy._retention_surplus(board, deposit), 4)

    def test_fixed_quest_force_still_requires_99_after_normal_weight_deposit(self):
        board = self._after_shots()
        strategy = self.policy._carry_procurement_strategy(board)
        status = self.policy._quest_carry_status(board, strategy.required_force)
        self.assertEqual(status["throwing_items.launcher_ammo"],
                         {"measured": 95, "required": 99, "ready": False})
        self.assertFalse(self.policy._fixed_quest_ready_for_travel(board, strategy.quest_id))

    def test_recorded_public_board_routes_ammo_home_before_departure(self):
        saved = checkpoint(self.policy)
        for policy in (self.policy, restore_checkpoint(HengbotPolicy, saved)):
            key = policy.choose_key(self.board)
            self.assertEqual((str(key), policy.last_reason), ("\x1b`n(.", "shop:travel"))
            self.assertEqual(policy._shopping_approach_store_type, 7)
            self.assertIsNone(policy._town_blocked_reason)

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
                          ("f", 6), ("g", 1), ("h", 0), ("i", 95)])
        self.assertEqual(self.policy._total_identify_staff_charges(self.board), 20)
        self.assertEqual(self.policy._find_surplus_identify_staff(
            self.board, for_weight_overload=True), None)
        home = next(row["store"] for row in reversed(self.capture["boards"])
                    if (row.get("store") or {}).get("store_type") == 7)
        self.assertEqual((home["stock_num"], home["capacity"]), (61, 240))
        self.assertEqual(len(self.policy._equipment_catalog.items), 40)

    def test_public_stop_board_offers_deeper_guardian_remedy_after_restore(self):
        board = self._after_shots()
        saved = checkpoint(self.policy)
        for policy in (self.policy, restore_checkpoint(HengbotPolicy, saved)):
            self.assertEqual(policy._town_recall_destination(board, guardian_gate=False),
                             ("yeek-cave", 2))
            self.assertEqual(policy._guardian_floor_blocked(board, 2, 12), True)
            self.assertEqual(policy._guardian_floor_blocked(board, 3, 18), False)
            self.assertEqual(policy._missing_required_abilities(board, 18), frozenset())
            # Evaluate departure directly on the constructed effect board.
            # Weight relief also makes optional launcher enchanting live; its
            # shop route may precede this evaluator on the public path.
            key = policy._town_special_key(board)
            historical = self.capture["decisions"][-1]
            print("CLASS C2 FIRST DIFFERENCE", "live", repr(historical["key"]),
                  historical["reason"], "replay", repr(str(key)), policy.last_reason,
                  "target", policy._target_dungeon_id)
            self.assertEqual((str(key), policy.last_reason),
                ("5", "town:unsafe-recall-fallback"))
            self.assertEqual((policy._alternate_dungeon, policy._target_dungeon_id), (3, 3))
            self.assertEqual(policy._conquest_committed, None)
            self.assertEqual(policy._town_blocked_reason, None)
            self.assertEqual(policy._pending_recall_dungeon_id, None)
            # The guardian remedy is still required after the weight remedy.
            self.assertEqual(policy._departure_block["failed"],
                ["recall_landing_not_guardian_blocked"])
            self.assertEqual(policy._inventory_overweight(board), False)
            self.assertTrue(policy._town_departure_ready(board))
            self.assertTrue(all(policy._recall_town_departure_conjuncts(board).values()))
            # The departure evaluator's next decision on this constructed kit
            # can issue the safe recall; no later live response is supplied.
            recall = policy._town_special_key(board)
            self.assertTrue(str(recall).startswith("r"))
            self.assertEqual(policy.last_reason, "town:recall-to-alt-dungeon")
            self.assertEqual(policy._pending_recall_dungeon_id, 3)
            # Stop at this changed decision: no future live effect is claimed.

    def test_no_alternate_keeps_visible_stop_and_weight_requirement(self):
        # Named counterfactual: only Angband and the refused Yeek cave entered.
        # The four-shot weight remedy has completed on this counterboard.
        board = replace(self._after_shots(), entered_dungeon_ids=(1, 2))
        key = self.policy._town_special_key(board)
        self.assertEqual((str(key), self.policy.last_reason),
                         ("1", "town:blocked:guardian-bounce-no-alternate"))
        self.assertEqual(self.policy._target_dungeon_id, 2)
        self.assertEqual(self.policy._inventory_overweight(board), False)

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
            self.assertEqual([(i.slot, n) for i, n in policy._home_deposit_batch(
                board, deposit)], [("j", 1), ("i", 4)])
            self.assertEqual(policy._inventory_weight(board), 1773)
            key = policy.choose_key(board)
            self.assertEqual((str(key), policy.last_reason), ("\x1b`n(.", "shop:travel"))
            self.assertEqual(policy._shopping_approach_store_type, 7)
            self.assertEqual(policy._target_dungeon_id, 2)
            self.assertEqual(policy._town_blocked_reason, None)


if __name__ == "__main__":
    unittest.main()
