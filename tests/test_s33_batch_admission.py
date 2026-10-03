"""DECLARED CONSTRUCTED admission seams from the October 1-3 captures.

The retained tails are decision projections, not restorable checkpoints.
These pins run the real choose_key/arbiter on a small town corridor, then
probe each foreign entry without replacing any decision/readiness method.
Reverting entry admission invokes the sentinel mutation; reverting OFF
binding restores gate-missing; reverting quest holder coverage lets idle run.
"""
import gzip
import json
from pathlib import Path
import unittest
from dataclasses import replace

import tests  # noqa: F401
from hengbot.claim_register import reach
from hengbot.model import Position, Snapshot
from hengbot.policy import HengbotPolicy
from policy_fixtures import grid, player


FIXTURE = Path(__file__).parent / "fixtures/s33-batch-seams-20261003.json.gz"


def corridor():
    return Snapshot(
        player=player(10, 10),
        grids={Position(10, x): grid(10, x) for x in range(9, 16)},
        visible_monsters=[], detected_monsters=[], turn=100,
        floor_key=(0, 0, 0), town_flag=True, town_id=0,
    )


def route_policy(board, *, family="store-router", enforced=True):
    policy = HengbotPolicy()
    policy.prime(board)
    policy._town_claim_bar_enforced = enforced
    policy._home_knowledge_current = True
    policy._equipment_catalog.home_scan_complete = True
    cell = (10, 14)
    claim = policy._claim_register.declare(family, reach(cell), floor=board.floor_key)
    policy._claim_register.declare_execution(
        claim.claim_id, work_id="route:constructed", producer=family,
        state="acting", next_step="route.resume", arguments=("store", cell),
        expected_effect="arrive", continuation="route.resume", budget_ref="town-travel")
    return policy


class AdmissionTest(unittest.TestCase):
    def test_foreign_entries_cannot_mutate_the_route(self):
        board = corridor()
        policy = route_policy(board)
        held = policy._claim_register.current.claim_id
        self.assertEqual(policy.choose_key(board), "6")
        self.assertEqual(policy.last_reason, "shop:approach")
        mutations = []
        for family in ("quest-request", "town-plan", "idle", "home-errand",
                       "home-visit", "floor-loot", "curse-enchant", "identification"):
            with self.subTest(family=family):
                self.assertIsNone(policy._town_producer_entry(
                    "constructed-foreign", lambda: mutations.append(family), family=family))
        self.assertEqual(mutations, [])
        self.assertEqual(policy._claim_register.current.claim_id, held)
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
        self.assertIsNone(policy._s33_shadow_verdict(board, "6")["would_stop"])

    def test_off_probe_is_bound_to_the_actual_foreign_output(self):
        board = corridor()
        policy = route_policy(board, enforced=False)
        def bounty():
            policy.last_reason = "bounty:leave-supplier"
            return "\x1b"
        self.assertEqual(policy._town_producer_entry(
            "constructed-bounty", bounty, family="quest-request"), "\x1b")
        shadow = policy._s33_shadow_verdict(board, "\x1b")
        self.assertIsNone(shadow["would_stop"])
        # An unrelated output cannot borrow the gated entry's provenance.
        self.assertEqual(policy._s33_shadow_verdict(board, "8")["would_stop"],
                         "ownership:gate-missing:quest-request")

    def test_quest_route_holds_foreign_idle(self):
        board = corridor()
        policy = route_policy(board, family="quest-request")
        held = policy._claim_errand_hold("idle")
        self.assertIsNotNone(held)
        self.assertIsNone(policy._town_producer_entry(
            "idle-fallback", lambda: policy._town_idle_key(board), family="idle"))
        self.assertTrue(held.is_open)

    def test_teleport_admission_precedes_route_mutation(self):
        board = corridor()
        policy = route_policy(board)
        before = policy._decision_goal
        self.assertIsNone(policy._town_teleport_key(
            board, 1, producer="quest-request", reason="fixedquest:q2-teleport"))
        self.assertEqual(policy._decision_goal, before)
        self.assertIsNone(policy.town_teleport_refusal)

    def test_quest_teleport_continues_through_choose_key(self):
        board = corridor()
        inn = Position(10, 14)
        board = replace(board, grids={**board.grids, inn: grid(10, 14, building_type=0)})
        policy = route_policy(board, family="quest-request")
        claim = policy._claim_register.current
        policy._claim_register.declare_execution(
            claim.claim_id, work_id="teleport:1", producer="quest-request",
            state="awaiting", arguments=(1, "fixedquest:q2-teleport"),
            operation_ref="decision:1:6", expected_effect="town:1",
            continuation="town.teleport.resume", budget_ref="town-travel")
        key = policy.choose_key(board)
        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "fixedquest:q2-teleport")
        self.assertEqual(policy.decision_claim["claim_id"], claim.claim_id)
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])

    def test_real_identification_and_full_pack_disposal_are_gated_before_mutation(self):
        from hengbot.model import parse_snapshot
        pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        pin = next(pin for pin in pins if "170231" in pin["source"] and pin["line"] == 232)
        recorded = parse_snapshot(pin["board"])
        board = replace(corridor(), inventory=recorded.inventory, equipment=recorded.equipment)
        for method in ("_town_item_processing_key", "_full_pack_destroy_key"):
            with self.subTest(method=method):
                policy = route_policy(board, family="equipment-txn")
                before = (policy._home_pending_item, policy._identification_need,
                          policy._destroy_watch)
                self.assertIsNone(getattr(policy, method)(board))
                self.assertEqual((policy._home_pending_item, policy._identification_need,
                                  policy._destroy_watch), before)
                self.assertTrue(any(row["deferred_family"] == "identification"
                                    for row in policy._decision_errand_deferred))

    def test_capture_pairings_remain_identifiable(self):
        pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        kinds = {(pin["row"].get("claim", {}).get("s33_shadow") or {}).get("would_stop")
                 for pin in pins}
        self.assertIn("ownership:gate-missing:quest-request", kinds)
        self.assertIn("ownership:gate-missing:store-router", kinds)
        self.assertIn("ownership:gate-missing:home-errand", kinds)
        self.assertTrue(any(pin["board"] is not None for pin in pins))

    def test_live_off_crossarea_home_holder_allows_recorded_disposal(self):
        from hengbot.model import parse_snapshot, STORE_HOME
        pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        pin = next(p for p in pins if "170231" in p["source"] and p["line"] == 232)
        recorded = parse_snapshot(pin["board"])
        board = replace(corridor(), inventory=recorded.inventory, equipment=recorded.equipment)
        for family in ("store-router", "home-visit", "equipment-txn"):
            with self.subTest(family=family):
                policy = route_policy(board, family=family, enforced=False)
                policy._crossarea_fundraising_enforced = True
                policy._map_predicate_snapshot = board
                policy._request_store_trip(STORE_HOME, "home-visit")
                self.assertTrue(policy._home_sequence_has_holder())
                self.assertEqual(policy._full_pack_destroy_key(board), "01kb")
                self.assertEqual(policy.last_reason, "inventory:destroy-disposable-item")
                row = next(r for r in policy._decision_errand_deferred
                           if r["deferred_reason"] == "entry:verified-disposal")
                self.assertFalse(row["token_would_admit"])
                self.assertEqual(row["producer_key"], "01kb")
                # A pre-existing entry still honors the cross-area Home hold.
                self.assertTrue(policy._defer_town_errand("identification", "equipped-identification"))

    def test_deferred_approved_home_disposal_retains_pending_work(self):
        from hengbot.model import parse_snapshot
        pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        pin = next(p for p in pins if "170231" in p["source"] and p["line"] == 232)
        recorded = parse_snapshot(pin["board"])
        board = replace(corridor(), inventory=recorded.inventory, equipment=recorded.equipment)
        policy = route_policy(board, family="equipment-txn")
        policy._map_predicate_snapshot = board
        target = next(it for it in board.inventory if it.slot == "b")
        pending = (policy._item_signature(target), "destroy")
        policy._home_disposal_pending = pending
        self.assertIsNone(policy._home_disposal_processing_key(board))
        self.assertEqual(policy._home_disposal_pending, pending)


if __name__ == "__main__":
    unittest.main()
