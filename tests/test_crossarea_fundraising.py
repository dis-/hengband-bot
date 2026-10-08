"""Pins for the first cross-area fundraising switch and captured stair facts."""

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import tests  # noqa: F401 -- isolate runtime files

from hengbot.policy import HengbotPolicy
from hengbot.claim_register import ClaimOwner, observe
from hengbot.policy_fundraising import (
    FundraisingFacts, FundraisingPurpose, FundraisingPurposeRecord,
    FundraisingTransportChild,
    fundraising_run_verdict,
)
from hengbot.model import (
    DUNGEON_YEEK_CAVE, Position, Snapshot, STORE_GENERAL, STORE_HOME,
    STORE_MAGIC, StoreState, parse_snapshot,
)
from hengbot.policy_constants import FOOD_TYPE_MANA
from hengbot.policy_types import TownErrandPlan
from policy_fixtures import grid, item, player, store_item
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.home_entry_capture import HomeEntryCapture
from test_esp_threat_rest_recorded import EDIT


FIXTURES = Path(__file__).parent / "fixtures"
CAPTURE = FIXTURES / "crossarea-holder-silent"


class CrossAreaFundraisingTest(unittest.TestCase):
    def setUp(self):
        self.facts = FundraisingFacts(
            carried_edible=False, hungry=False, light_ready=True,
            pack_full=False, objective_achieved=False,
            procurement_exhausted=True, first_run=True,
            known_treasure=False, mode="mine",
        )
        self.purpose = FundraisingPurpose(29, "mine", True)

    def test_captured_29_30_pair_has_unchanged_normal_food_premise(self):
        with gzip.open(str(CAPTURE) + ".decisions.jsonl.gz", "rt",
                       encoding="utf-8") as source:
            decisions = [json.loads(row) for row in source]
        pair = [row for row in decisions
                if row.get("decision_sequence") in {29, 30}]
        self.assertEqual([(row["key"], row["reason"]) for row in pair[:2]],
                         [(">\ry", "descend"), ("<", "fundraise:ascend")])
        with gzip.open(str(CAPTURE) + ".states.jsonl.gz", "rt",
                       encoding="utf-8") as source:
            states = [json.loads(row) for row in source]
        town, floor = states
        for state in (town, floor):
            self.assertEqual(state["player"]["food_state"], "normal")
            self.assertEqual(state["player"]["gold"], 136)
            self.assertFalse(any(item["tval"] in {55, 65}
                                 for item in state["inventory"]))
        admitted = fundraising_run_verdict(self.facts, self.purpose)
        self.assertTrue(admitted.may_depart)
        self.assertTrue(admitted.may_continue)
        self.assertFalse(admitted.must_return)

    def test_live_1710_to_1712_posts_departure_only_after_final_arbitration(self):
        capture = FIXTURES / "crossarea-stair-await"
        with gzip.open(str(capture) + ".states.jsonl.gz", "rt",
                       encoding="utf-8") as source:
            states = [json.loads(row) for row in source]
        with gzip.open(str(capture) + ".decisions.jsonl.gz", "rt",
                       encoding="utf-8") as source:
            decisions = [json.loads(row) for row in source]
        before = next(row for row in states if row["turn"] == 231461)
        stopped = next(row for row in states if row["turn"] == 231466)
        self.assertEqual([before["turn"], stopped["turn"]],
                         [231461, 231466])
        self.assertEqual([(row["decision_sequence"], row["key"])
                          for row in decisions[-3:]],
                         [(1709, "wga"), (1710, "tb"), (1712, "")])
        self.assertEqual((stopped["player"]["y"], stopped["player"]["x"]),
                         (31, 150))
        snapshot = parse_snapshot(
            stopped, load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        )
        self.assertTrue(snapshot.grid_at(snapshot.player.position).has_down_stairs)

        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_mode = "mine"
        policy._fundraising_run_purpose = self.purpose
        policy._fundraising_purpose_record = FundraisingPurposeRecord(self.purpose)
        policy._decision_sequence = 1710
        policy.consume_skill_knowledge(next(
            row for row in states
            if row.get("knowledge", {}).get("category") == "skill_exp"
        ))
        equipment_claim = policy._claim_register.declare(
            ClaimOwner.EQUIPMENT_TXN,
            observe(("transaction",), 10, "transaction"),
            opened_sequence=1709, opened_turn=231452, floor=snapshot.floor_key,
        )
        policy._claim_register.declare_execution(
            equipment_claim.claim_id, work_id="equipment:completed:1709",
            producer="equipment-txn", state="releasing",
            cause="transaction-complete",
        )
        passes = []

        def decide(_snapshot):
            policy._decision_sequence += 1
            passes.append(policy._decision_sequence)
            if len(passes) == 1:
                self.assertTrue(policy._defer_town_errand(
                    "departure", "entry:stair.post"))
                return None
            policy.last_reason = "descend"
            return ">\ry"

        class CountingCapture(HomeEntryCapture):
            calls = 0

            def choose_key(self, subject, board):
                self.calls += 1
                return super().choose_key(subject, board)

        with TemporaryDirectory() as directory:
            capture = CountingCapture(Path(directory) / "home-entry.jsonl")
            policy._home_entry_capture = capture
            with patch.object(policy, "_choose_key_with_latch_capture",
                              side_effect=decide):
                key = policy.choose_key(snapshot)
        self.assertEqual(passes, [1711, 1712],
                         (key, policy.last_reason,
                          policy._decision_errand_deferred,
                          policy._claim_register.current))
        self.assertEqual(capture.calls, 2)
        self.assertEqual((key, policy.last_reason), (">\ry", "descend"))
        self.assertEqual(policy._pending_stair_command[0], ">")
        claim = policy._claim_register.current
        self.assertEqual((claim.owner.value, claim.goal.source, claim.state.value),
                         ("departure", "floor-change", "active"))
        child = policy._fundraising_purpose_record.child
        self.assertEqual((child.direction, child.state, child.posted_sequence),
                         ("depart", "posted", 1712))

    def test_captured_floor_does_not_immediately_ascend_with_active_purpose(self):
        with gzip.open(str(CAPTURE) + ".states.jsonl.gz", "rt",
                       encoding="utf-8") as source:
            states = [json.loads(row) for row in source]
        floor = parse_snapshot(
            states[1], load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        )
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_mode = "mine"
        policy._fundraising_run_purpose = self.purpose
        policy._fundraising_purpose_record = FundraisingPurposeRecord(
            self.purpose
        )
        policy._fundraising_purpose_record = replace(
            policy._fundraising_purpose_record,
            child=FundraisingTransportChild(
                self.purpose.identity, "depart", (0, 0, 0), 29,
                state="complete",
            ),
        )
        key = policy.choose_key(floor)
        self.assertNotEqual(key, "<")

    def test_waiver_is_first_run_only_and_hunger_still_returns(self):
        self.assertFalse(fundraising_run_verdict(
            replace(self.facts, first_run=False), None
        ).may_depart)
        self.assertFalse(fundraising_run_verdict(
            replace(self.facts, procurement_exhausted=False), None
        ).may_depart)
        hungry = fundraising_run_verdict(
            replace(self.facts, hungry=True), self.purpose
        )
        self.assertTrue(hungry.must_return)
        self.assertFalse(hungry.may_continue)
        self.assertTrue(fundraising_run_verdict(
            replace(self.facts, carried_edible=True, first_run=False), None
        ).may_depart)
        self.assertFalse(fundraising_run_verdict(
            replace(self.facts, first_run=False), self.purpose
        ).may_continue)
        for change in ({"light_ready": False}, {"pack_full": True},
                       {"objective_achieved": True}):
            self.assertTrue(fundraising_run_verdict(
                replace(self.facts, **change), self.purpose
            ).must_return)
        self.assertFalse(fundraising_run_verdict(
            replace(self.facts, objective_achieved=True,
                    known_treasure=True), self.purpose
        ).must_return)
        self.assertTrue(fundraising_run_verdict(
            replace(self.facts, objective_achieved=True,
                    known_treasure=True, mode="scavenge"), self.purpose
        ).must_return)

    def test_home_copy_and_affordable_shop_prevent_first_run_waiver(self):
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._town_store_attempted[STORE_MAGIC] = 1
        home_device = item("a", 55, 1, charges=20)
        policy._home_knowledge_items = [home_device]
        home_grid = replace(grid(10, 11), store_number=STORE_HOME)
        snapshot = Snapshot(
            player(10, 10, food_type=FOOD_TYPE_MANA, gold=136, food=5000),
            {Position(10, 10): grid(10, 10), home_grid.position: home_grid},
            [], town_flag=True,
        )
        facts = policy._fundraising_facts(snapshot)
        self.assertFalse(facts.procurement_exhausted)
        self.assertFalse(facts.first_run)
        self.assertFalse(fundraising_run_verdict(facts, None).may_depart)
        policy._home_knowledge_items = []
        snapshot = replace(snapshot, store=StoreState(
            STORE_MAGIC, [store_item("a", 55, 1, price=100)]
        ))
        facts = policy._fundraising_facts(snapshot)
        self.assertFalse(facts.procurement_exhausted)
        self.assertFalse(fundraising_run_verdict(facts, None).may_depart)

    def test_fresh_attachment_needs_save_backed_first_run_evidence(self):
        policy = HengbotPolicy()
        policy._home_knowledge_current = True
        policy._town_store_attempted[STORE_MAGIC] = 1
        snapshot = Snapshot(
            player(10, 10, food_type=FOOD_TYPE_MANA, gold=136, food=5000),
            {Position(10, 10): grid(10, 10)}, [], town_flag=True,
            inventory=[item("a", 39, 0, fuel=5000)],
            protocol_version=3, visited_town_ids=(0,),
            entered_dungeon_ids=(DUNGEON_YEEK_CAVE,),
        )
        facts = policy._fundraising_facts(snapshot)
        self.assertFalse(facts.first_run)
        self.assertFalse(fundraising_run_verdict(facts, None).may_depart)
        facts = policy._fundraising_facts(
            replace(snapshot, entered_dungeon_ids=())
        )
        self.assertTrue(facts.first_run)
        self.assertTrue(fundraising_run_verdict(facts, None).may_depart)

    def test_magic_shop_uses_home_device_before_affordable_ware(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_mode = "mine"
        policy._home_knowledge_current = True
        ware = store_item("a", 55, 1, price=100)
        home_device = item("a", 55, 1, charges=20)
        policy._home_knowledge_items = [home_device]
        home_grid = replace(grid(10, 11), store_number=STORE_HOME)
        snapshot = Snapshot(
            player(10, 10, food_type=FOOD_TYPE_MANA, gold=136, food=5000),
            {Position(10, 10): grid(10, 10), home_grid.position: home_grid},
            [], town_flag=True, store=StoreState(STORE_MAGIC, [ware]),
        )
        self.assertIsNone(policy._legacy_next_purchase_unreserved(snapshot))
        self.assertEqual(policy._home_pending_item,
                         policy._item_signature(home_device))
        self.assertTrue(policy._fundraising_affordable_food_seen)
        policy._home_pending_item = None
        policy._home_knowledge_items = []
        self.assertIs(policy._legacy_next_purchase_unreserved(snapshot), ware)

    def test_suppressed_restock_still_checks_shared_admission(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._town_restock_suppressed = True
        policy._fundraising_mode = "mine"
        snapshot = SimpleNamespace(
            in_town=True, inventory=[],
            player=SimpleNamespace(gold=136),
        )
        with (patch.object(policy, "_next_depth_supply_shortage",
                           return_value=False),
              patch.object(policy, "_recall_departure_shortage",
                           return_value=False),
              patch.object(policy, "_fundraising_departure_ready",
                           return_value=False)):
            self.assertTrue(policy._descent_is_blocked(snapshot))
        self.assertEqual(policy._descent_refusal_reason,
                         "recall-departure-shortage")

    def test_transport_completion_keeps_economic_purpose_open(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_run_purpose = self.purpose
        policy._decision_sequence = 29
        town = SimpleNamespace(floor_key=(0, 0, 0))
        policy._post_fundraising_transport(town, "depart")
        child = policy._fundraising_purpose_record.child
        self.assertEqual(child.purpose_id, self.purpose.identity)
        floor = SimpleNamespace(
            floor_key=(DUNGEON_YEEK_CAVE, 1, 1), in_town=False,
            dungeon_level=1, player=SimpleNamespace(gold=136),
        )
        self.assertTrue(policy._observe_fundraising_transport(floor))
        record = policy._fundraising_purpose_record
        self.assertEqual(record.child.state, "complete")
        self.assertEqual(record.status, "active")
        policy._post_fundraising_transport(floor, "return")
        arrived = SimpleNamespace(
            floor_key=(0, 0, 0), in_town=True, dungeon_level=0,
            player=SimpleNamespace(gold=136),
        )
        self.assertTrue(policy._observe_fundraising_transport(arrived))
        self.assertEqual(policy._fundraising_purpose_record.status, "active")
        self.assertEqual(policy._fundraising_purpose_record.child.state,
                         "complete")

    def test_wrong_destination_fails_purpose_and_bars_readmission(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_run_purpose = self.purpose
        policy._post_fundraising_transport(
            SimpleNamespace(floor_key=(0, 0, 0)), "depart"
        )
        wrong = SimpleNamespace(
            floor_key=(9, 3, 0), in_town=False, dungeon_level=3,
            player=SimpleNamespace(gold=136),
        )
        self.assertFalse(policy._observe_fundraising_transport(wrong))
        self.assertEqual(policy._fundraising_purpose_record.status, "failed")
        self.assertEqual(policy._fundraising_purpose_record.failure,
                         "wrong-destination")
        with patch.object(policy, "_fundraising_facts", return_value=self.facts):
            self.assertFalse(policy._fundraising_departure_ready(wrong))

    def test_missing_transport_grant_stops_before_dungeon_work(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_mode = "mine"
        # This process posted a fundraising departure (the in-run case).  A
        # process that posted none is a restart and leaves the floor instead
        # (test_restart_without_purpose_leaves_the_floor; live 2026-10-03).
        policy._fundraising_runs_started = 1
        board = SimpleNamespace(
            floor_key=(DUNGEON_YEEK_CAVE, 1, 1), dungeon_level=1,
            in_town=False, player=SimpleNamespace(hungry=False),
        )
        self.assertEqual(policy._fundraising_key(board, []), "5")
        self.assertEqual(policy.last_reason,
                         "ownership:contract-conflict:fundraising:missing-purpose")
        board.player.hungry = True
        with (patch.object(policy, "_find_edible", return_value=None),
              patch.object(policy, "_leave_fundraising_floor",
                           return_value="<")):
            self.assertEqual(policy._fundraising_key(board, []), "<")

    def test_restart_without_purpose_leaves_the_floor(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_mode = "mine"
        board = SimpleNamespace(
            floor_key=(DUNGEON_YEEK_CAVE, 1, 1), dungeon_level=1,
            in_town=False, player=SimpleNamespace(hungry=False),
        )
        with patch.object(policy, "_leave_fundraising_floor",
                          return_value="<"):
            self.assertEqual(policy._fundraising_key(board, []), "<")
        # A record that exists but failed is still a conflict in a restart.
        policy._fundraising_run_purpose = self.purpose
        policy._fundraising_purpose_record = replace(
            FundraisingPurposeRecord(self.purpose), status="failed"
        )
        self.assertEqual(policy._fundraising_key(board, []), "5")
        self.assertEqual(policy.last_reason,
                         "ownership:contract-conflict:fundraising:missing-purpose")

    def test_checkpoint_keeps_waiver_and_legacy_checkpoint_gets_defaults(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_run_purpose = self.purpose
        policy._fundraising_purpose_record = FundraisingPurposeRecord(
            self.purpose
        )
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertTrue(restored._crossarea_fundraising_enforced)
        self.assertEqual(restored._fundraising_run_purpose, self.purpose)
        self.assertEqual(restored._fundraising_purpose_record.status, "active")
        for name in ("_crossarea_fundraising_enforced",
                     "_fundraising_run_purpose", "_fundraising_purpose_record",
                     "_fundraising_runs_started",
                     "_fundraising_affordable_food_seen"):
            delattr(policy, name)
        older = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertFalse(older._crossarea_fundraising_enforced)
        self.assertIsNone(older._fundraising_run_purpose)
        self.assertIsNone(older._fundraising_purpose_record)
        self.assertIsNone(older._fundraising_runs_started)
        self.assertFalse(older._fundraising_affordable_food_seen)

    def test_recorded_exhausted_home_shortage_reopens_fundraising_preparation(self):
        fixture = Path(__file__).parent / "fixtures" / (
            "unaffordable-fundraise-home-exhausted-20261008.json.gz"
        )
        self.assertEqual(
            hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "986ae5551d2bb479f2778554682805b088ff7ae54fd6ea2d5db74e48bcc547e8",
        )
        with gzip.open(fixture, "rt", encoding="utf-8") as source:
            raw_board = json.load(source)
        board = parse_snapshot(
            raw_board, load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        )
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._fundraising_runs_started = 1
        policy._town_errand_plan = TownErrandPlan([STORE_HOME], index=1)
        policy._town_store_attempted.update({
            STORE_HOME: board.turn, STORE_GENERAL: board.turn,
            STORE_MAGIC: board.turn,
        })

        ledger = policy._supply_ledger(board, policy._planned_depth())
        food = ledger["food"]
        self.assertEqual((food.count, food.required_departure, food.obtainable),
                         (14, 15, False))
        with (patch.object(policy, "_skill_exp_request_key", return_value=None),
              patch.object(policy, "_refresh_carried_equipment_catalog"),
              patch.object(policy, "_choose_key_with_latch_capture",
                           return_value="5")):
            policy.choose_key(board)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._fundraising_runs_started, 1)
        # Preparation cannot waive the return ticket or ordinary food gate.
        self.assertTrue(policy._descent_is_blocked(board))
        self.assertIn(policy._descent_refusal_reason,
                      {"recall-departure-shortage", "food-departure-shortage"})


if __name__ == "__main__":
    unittest.main()
