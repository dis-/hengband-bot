"""2026-10-05 07:16 stop: full identification is optional candidate work.

Declared wall: this is the final recorded board, not a replay of all preceding
shopping. Home knowledge, the Alchemist shelf, deferred signatures, and visited
stores come from the capture. The carried producer reconstructs the full need;
the recorded Home wait latch and Orc cave destination are restored explicitly.
Calibration/dump work is outside this boundary; the production departure gate
uses its ordinary calibration-unavailable movement rule. No optimizer is mocked.
The pin ends at the first changed departure command: there is no captured board
after that command. Stock and later-visit cases are separate model perturbations.
"""

import tests  # noqa: F401 -- isolate all runtime files

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import (
    STORE_ALCHEMIST, STORE_BLACK, STORE_HOME, SV_SCROLL_STAR_IDENTIFY,
    TVAL_SCROLL, InventoryItem, StoreItem, StoreState, _parse_items, parse_snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STORE_RESTOCK_WAIT_TURNS
from hengbot.protocol import snapshot_protocol_version


FIXTURE = Path(__file__).parent / "fixtures/star-identify-departure-20261005.json.gz"
SHA256 = "5c05a1d4d603c4452cb97a05497fa21b38c7a293a3ea709e00565b716190aa03"
FAILED = ["home_candidate_resolved", "identification_need_clear",
          "departure_identification_need_clear"]


class StarIdentifyDepartureRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.capture = json.load(stream)

    def stalled(self):
        board = parse_snapshot(self.capture["board"])
        policy = HengbotPolicy()
        policy.prime(board)
        policy.consume_skill_knowledge(self.capture["skills"])
        board = policy.with_known_skill_exp(board)
        policy._refresh_carried_equipment_catalog(board)
        knowledge = self.capture["knowledge"]
        policy.consume_home_knowledge(tuple(_parse_items(
            knowledge["knowledge"]["items"],
            protocol=snapshot_protocol_version(knowledge),
        )))
        shelf = parse_snapshot(self.capture["alchemist"])
        policy._town_supplier_stock[STORE_ALCHEMIST] = shelf.store
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (
            policy._effective_town_id(shelf), shelf.turn,
        )
        for signature in self.capture["deferred_home_item_signatures"]:
            policy._defer_home_item(tuple(signature), "recorded-before-stop")
        # The real carried scan selects the not-fully-known Pike (22/8).
        self.assertIsNone(policy._town_item_processing_key(board))
        self.assertEqual(policy._identification_need, "full")
        signature = policy._identification_candidate
        self.assertEqual(signature[1:], (22, 8))
        for store in self.capture["town_ledger"]["store_visits"]:
            policy._town_store_attempted[int(store)] = board.turn
        policy._home_candidate_waiting = True
        policy._target_dungeon_id = 3  # recorded Orc cave target
        policy._char_dump_done_this_visit = True  # decision 37 completed
        return policy, board, signature

    def star_scroll(self, *, store=False):
        fields = dict(tval=TVAL_SCROLL, sval=SV_SCROLL_STAR_IDENTIFY,
                      name="Scroll of *Identify*", count=1, aware=True, known=True)
        return (StoreItem(letter="z", price=1000, **fields) if store
                else InventoryItem(slot="z", **fields))

    def test_recorded_stop_diverges_to_ready_recall_without_candidate_loss(self):
        pins = self.capture["pins"]
        self.assertEqual([pin["decision_sequence"] for pin in pins], list(range(28, 39)))
        self.assertEqual(
            [(pin["reason"], pin["key"]) for pin in pins[-5:]],
            [("home:atomic-deposit", "db2\r\x1b"),
             ("town:entrance-step-off:town:unsafe-recall-fallback", "3"),
             ("home:request-knowledge-scan", "~9\x1b\x1b"),
             ("town:character-dump", "Cf\ry\x1b\x1b"),
             ("town:blocked:departure-unsatisfiable", "5")],
        )
        self.assertEqual(pins[-1]["departure_block"]["failed"], FAILED)
        self.assertEqual(pins[-1]["procurement_requirements"], [
            {"item": "*Identify* source", "current": 0, "target": 1, "missing": 1},
        ])
        policy, board, signature = self.stalled()
        before = policy._recall_town_departure_conjuncts(board)
        self.assertEqual([name for name, ready in before.items() if not ready], FAILED)
        inventory = tuple(board.inventory)
        home = tuple(policy._home_knowledge_items)

        self.assertIsNone(policy._next_required_store_type(board))
        after = policy._recall_town_departure_conjuncts(board)
        self.assertTrue(all(after.values()), after)
        self.assertEqual(policy._town_special_key(board), "ric")
        self.assertEqual(policy.last_reason, "town:recall-to-alt-dungeon")
        self.assertIn(signature, policy._deferred_home_items)
        self.assertIsNone(policy._identification_need)
        self.assertIsNone(policy._identification_candidate)
        self.assertIsNone(policy._fundraising_mode)
        self.assertIsNone(policy._town_restock_wait_until)
        self.assertEqual(tuple(board.inventory), inventory)
        self.assertEqual(tuple(policy._home_knowledge_items), home)
        target = next(item for item in board.inventory
                      if policy._item_signature(item) == signature)
        self.assertFalse(target.fully_known)
        self.assertTrue(policy._disposal_protected_by_identification(target))
        self.assertNotEqual(policy._find_weapon_sale(board), target)
        self.assertNotEqual(policy._find_disposable_item(board), target)
        self.assertEqual(policy._carried_full_identify_targets(board), [])
        self.assertEqual(policy._home_full_identify_targets(), [])
        self.assertIsNone(policy._town_item_processing_key(board))
        self.assertIsNone(policy._identification_need)

    def test_stored_full_candidate_releases_reservation_and_departure_latch(self):
        policy, board, _ = self.stalled()
        target = next(owned.item for owned in policy._equipment_catalog.items
                      if owned.origin == "home" and owned.identification_incomplete)
        signature = policy._item_signature(target)
        policy._deferred_home_items.discard(signature)
        policy._identification_candidate = signature
        policy._reserve_next_identification_source(board, signature, full=True)
        policy._town_terminal_transitions(board)
        self.assertIn(signature, policy._deferred_home_items)
        self.assertIn(signature, policy._unbuyable_full_identify_sigs)
        self.assertIsNone(policy._identification_source_reservation)
        self.assertIsNone(policy._identification_need)
        self.assertFalse(policy._home_candidate_waiting)
        self.assertNotIn(target, policy._home_full_identify_targets())
        self.assertIsNone(policy._fundraising_mode)

    def test_unknown_stale_or_other_town_shelf_cannot_exclude_candidate(self):
        for kind in ("unknown", "stale", "other-town"):
            with self.subTest(kind=kind):
                policy, board, signature = self.stalled()
                town = policy._effective_town_id(board)
                if kind == "unknown":
                    policy._town_supplier_stock_observations.clear()
                elif kind == "stale":
                    policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (
                        town, board.turn - STORE_RESTOCK_WAIT_TURNS,
                    )
                else:
                    policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (
                        town + 1, board.turn,
                    )
                self.assertFalse(policy._defer_unavailable_equipment_full_identification(board))
                self.assertEqual(policy._identification_need, "full")
                self.assertNotIn(signature, policy._deferred_home_items)

    def test_carried_home_or_affordable_shop_source_preserves_identification(self):
        for source in ("carried", "home", "shop"):
            with self.subTest(source=source):
                policy, board, signature = self.stalled()
                scroll = self.star_scroll()
                if source == "carried":
                    board = replace(board, inventory=[*board.inventory, scroll])
                elif source == "home":
                    policy.consume_home_knowledge((*policy._home_knowledge_items, scroll))
                else:
                    policy._town_supplier_stock[STORE_ALCHEMIST] = StoreState(
                        store_type=STORE_ALCHEMIST, items=[self.star_scroll(store=True)],
                    )
                self.assertFalse(policy._defer_unavailable_equipment_full_identification(board))
                self.assertEqual(policy._identification_need, "full")
                self.assertNotIn(signature, policy._deferred_home_items)

    def test_deferred_candidate_buys_stock_in_local_and_other_town_shops(self):
        for town, store in ((0, STORE_ALCHEMIST), (2, STORE_ALCHEMIST), (3, STORE_BLACK)):
            with self.subTest(town=town, store=store):
                policy, board, signature = self.stalled()
                policy._next_required_store_type(board)
                self.assertIsNone(policy._identification_need)
                scroll = self.star_scroll(store=True)
                stocked = replace(board, town_id=town, store=StoreState(
                    store_type=store, items=[scroll],
                ))
                self.assertEqual(policy._next_purchase(stocked), scroll)
                self.assertTrue(any(match.rung_id == "identify:full"
                                    for match in policy._matching_live_purchase_rungs(stocked, scroll)))
                carried = replace(board, inventory=[*board.inventory, self.star_scroll()])
                self.assertIsNone(policy._next_purchase(replace(stocked, inventory=carried.inventory)))
                self.assertIn(signature, policy._deferred_home_items)

    def test_later_visit_retries_carried_and_home_candidates(self):
        policy, board, signature = self.stalled()
        policy._next_required_store_type(board)
        # Separate model boundary; not claimed to be the effect of recorded ric.
        policy._observe(replace(board, floor_key=(3, 23, 0), town_flag=False))
        policy._observe(replace(board, turn=board.turn + 1000))
        self.assertNotIn(signature, policy._deferred_home_items)
        self.assertIn("identification-source", {
            need.category for need in policy._enumerate_town_needs(board)
        })
        self.assertIsNone(policy._town_item_processing_key(board))
        self.assertEqual(policy._identification_candidate, signature)
        self.assertEqual(policy._identification_need, "full")
        self.assertTrue(policy._home_full_identify_targets())

    def test_single_deferred_home_candidate_checks_new_shelf_without_blocking_on_stockout(self):
        policy, board, carried_signature = self.stalled()
        policy._next_required_store_type(board)
        target = next(owned.item for owned in policy._equipment_catalog.items
                      if owned.origin == "home" and owned.identification_incomplete)
        signature = policy._item_signature(target)
        policy._defer_full_identification(signature)
        # Separate Home-only scenario: one stored target, no carried target and
        # hence no batch-sized Library expedition. The next visit must still
        # check *Identify* stock, then accept an empty shelf and leave.
        town = replace(board, inventory=[
            item for item in board.inventory
            if policy._item_signature(item) != carried_signature
        ], turn=board.turn + 1000)
        policy._observe(replace(board, floor_key=(3, 23, 0), town_flag=False))
        policy._observe(town)
        policy._refresh_carried_equipment_catalog(town)
        policy.consume_home_knowledge((target,))
        self.assertEqual(policy._home_full_identify_targets(), [target])
        self.assertIn("identification-source", {
            need.category for need in policy._enumerate_town_needs(town)
        })
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (
            policy._effective_town_id(town), town.turn,
        )
        self.assertNotIn("identification-source", {
            need.category for need in policy._enumerate_town_needs(town)
        })
        policy._release_stale_home_candidate_waiting(town)
        self.assertTrue(all(policy._recall_town_departure_conjuncts(town).values()))

    def test_deferred_full_retry_does_not_replace_pending_normal_identification(self):
        policy, board, _ = self.stalled()
        policy._next_required_store_type(board)
        policy._request_identification("normal")
        stocked = replace(board, store=StoreState(
            store_type=STORE_ALCHEMIST, items=[self.star_scroll(store=True)],
        ))
        self.assertNotEqual(policy._next_purchase(stocked), stocked.store.items[0])


if __name__ == "__main__":
    unittest.main()
