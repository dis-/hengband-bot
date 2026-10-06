"""Short action-consistent Home entry attachment from live23, no long replay."""
import gzip
import hashlib
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import tests  # noqa: F401 -- protect live runtime files
from hengbot.model import parse_snapshot
from hengbot.cli import _dispatch_response_lines
from hengbot.policy import HengbotPolicy
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.claim_register import observe
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO

FIXTURE = Path(__file__).parent / "fixtures/live23-home-cycle"


def attachment(enforced=False, crossarea=True):
    with gzip.open(FIXTURE / "state.jsonl.gz", "rt", encoding="utf8") as source:
        boards = [parse_snapshot(row, {}) for row in map(json.loads, source)]
    skills = {row["id"]: row["exp"] for row in json.loads(
        (FIXTURE / "skill-knowledge.json").read_text(encoding="utf8"))["knowledge"]["skills"]}
    # The emitter's separate recorded ~f reply supplies the player skill fields.
    boards = [replace(board, player=replace(board.player,
              two_weapon_skill=skills[1], shield_skill=skills[3])) for board in boards]
    policy = HengbotPolicy()
    policy._town_claim_bar_enforced = enforced
    policy._crossarea_fundraising_enforced = crossarea
    policy.prime(boards[0])
    prior = parse_snapshot(json.loads(
        (FIXTURE / "prior-home-page.json").read_text(encoding="utf8")), {})
    policy._adopt_home_catalogue(tuple(
        policy._inventory_item_from_store_item(item) for item in prior.store.items))
    # Attachment is the recorded post-deposit catalogue invalidation, not a
    # pretend observed equipment result. The old page has 23, new page 24 items.
    policy._invalidate_home_observation()
    return policy, boards


class Live23HomeCycleTest(unittest.TestCase):
    def test_recorded_partial_home_page_requests_catalogue_in_place(self):
        fixture = json.loads((Path(__file__).parent / "fixtures"
                              / "home-catalogue-burst-20261007.json").read_text(
                                  encoding="utf8"))
        page = parse_snapshot(fixture, {})
        self.assertEqual(fixture["pin"]["decision_sequence"], 2)
        self.assertEqual((page.store.stock_num, page.store.page_top,
                          page.store.page_size, len(page.store.items)),
                         (239, 0, 52, 52))

        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        holder = policy._claim_register.declare(
            "equipment-txn", observe((str(page.turn), str(page.store.store_type),
                                      "knowledge"), 8, "knowledge"))
        policy._claim_register.declare_execution(
            holder.claim_id, producer="equipment-txn",
            work_id="equipment:acquire-home-catalog", state="acting",
            next_step="home.catalogue.acquire",
            expected_effect="home-catalog-available",
            continuation="home.catalogue.acquire",
        )

        key = policy._home_catalogue_work_key(page)

        # Before this fix the recorded 52/239 page exited to request ~9 on the
        # map, starting the request/approach cycle captured in the incident.
        self.assertEqual(key, HOME_KNOWLEDGE_MACRO)
        self.assertEqual(policy.last_reason,
                         "equipment-transaction:catalogue-request-knowledge")
        policy.confirm_key_posted(key)
        self.assertTrue(policy._home_knowledge_scan_inflight)
        self.assertEqual(policy._home_knowledge_scan_epoch,
                         policy._town_visit_epoch)

        response = {
            "type": "knowledge",
            "knowledge": {"category": "home", "menu_key": "9", "items": []},
            "player": {"position": {"y": page.player.position.y,
                                     "x": page.player.position.x}},
        }
        with TemporaryDirectory() as directory:
            self.assertEqual(_dispatch_response_lines(
                [json.dumps(response)], policy, Mock(return_value=True),
                knowledge_ledger_path=Path(directory) / "knowledge.jsonl"), 1)
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(policy._home_scan_source, "~9")

    def test_recorded_entry_completes_catalogue_before_other_errand(self):
        provenance = json.loads((FIXTURE / "provenance.json").read_text(encoding="utf8"))
        for name, digest in provenance["fixture_sha256"].items():
            data = (FIXTURE / name).read_bytes()
            if name.endswith(".json"):
                data = data.replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
        for enforced, crossarea in ((False, True), (True, False), (True, True)):
            for restored in (False, True):
                with self.subTest(enforced=enforced, crossarea=crossarea, restored=restored):
                    policy, boards = attachment(enforced, crossarea)
                    self.assertEqual(policy.choose_key(boards[0]), "5")
                    self.assertEqual(policy.last_reason, "equipment-transaction:travel-home:await-entry")
                    holder_id = policy._claim_register.current.claim_id
                    policy.confirm_key_posted("5")
                    if restored:
                        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
                    # This page really follows the unchanged recorded 5.
                    key = policy.choose_key(boards[1])
                    self.assertEqual(key, "\x1b")
                    self.assertEqual(policy.last_reason, "equipment-transaction:home-catalog-acquired")
                    self.assertTrue(policy._home_knowledge_current)
                    self.assertFalse(policy._home_knowledge_invalidated)
                    self.assertEqual(len(policy._home_knowledge_items), 24)
                    closed = policy.decision_claim["closed_claim"]
                    self.assertEqual(closed["claim_id"], holder_id)
                    self.assertEqual(closed["closed_reason"], "home-knowledge-current")
                    self.assertIsNone(policy._home_pending_item)
                    # Stop here: no historical board is claimed to follow a
                    # changed purpose or a future equipment optimization.

    def test_historical_competing_actor_names_registered_holder_in_shadow(self):
        for restored in (False, True):
            policy, boards = attachment()
            self.assertEqual(policy.choose_key(boards[0]), "5")
            holder_id = policy._claim_register.current.claim_id
            policy.confirm_key_posted("5")
            if restored:
                policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
            # Independent shadow adjudication of the captured bad producer
            # result; do not call corrected producers or fabricate a next board.
            policy.last_reason = "home:queue-digging-tool-withdraw"
            policy._record_decision_claim(boards[1], "\x1b")
            shadow = policy.decision_claim["s33_shadow"]
            self.assertEqual(shadow["holder_family"], "equipment-txn")
            self.assertEqual(shadow["holder_claim_id"], holder_id)
            self.assertEqual(shadow["would_stop"], "ownership:gate-missing:home-visit")

    def test_digger_withdrawal_is_for_mining_departure_only(self):
        for enforced, crossarea in ((False, True), (True, False), (False, False)):
            for mode in (None, "prepare", "mine", "scavenge"):
                policy, boards = attachment(enforced, crossarea)
                policy._fundraising_mode = mode  # supplemental departure-purpose cases
                policy = pickle.loads(pickle.dumps(policy))
                key = policy._queue_standing_home_digger(boards[1])
                if mode is None and (enforced or crossarea):
                    self.assertIsNone(key)
                    self.assertIsNone(policy._home_pending_item)
                else:
                    self.assertEqual(key, "\x1b")

    def test_registered_catalogue_keeps_turn_even_for_later_mining_withdraw(self):
        for enforced, crossarea in ((False, True), (True, False)):
            policy, boards = attachment(enforced, crossarea)
            self.assertEqual(policy.choose_key(boards[0]), "5")
            policy.confirm_key_posted("5")
            policy._fundraising_mode = "prepare"  # supplemental competing need
            policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
            self.assertIsNone(policy._queue_standing_home_digger(boards[1]))
            self.assertIsNone(policy._home_pending_item)
            self.assertEqual(policy._decision_errand_deferred[-1]["holder_family"], "equipment-txn")

    def test_earlier_home_operation_defers_catalogue_before_producer_mutation(self):
        # Supplemental registration-order case uses the incident's real Home
        # operation shape; it is not presented as a sequential live replay.
        for enforced, crossarea in ((False, True), (True, False)):
            policy, boards = attachment(enforced, crossarea)
            holder = policy._claim_register.declare(
                "home-visit", observe((7, 1970, "ds\x1b"), 8, "store-operation"),
                non_discardable=True)
            policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
            policy._map_predicate_snapshot = boards[0]
            self.assertIsNone(policy._town_producer_entry(
                "_equipment_transaction_town_key",
                lambda: self.fail("later equipment producer ran"), family="equipment-txn"))
            self.assertEqual(policy._claim_register.current.claim_id, holder.claim_id)
            self.assertIsNone(policy._equipment_transaction_session)

    def test_recorded_off_scan_continues_registered_catalogue(self):
        # The unchanged entry/scan actions and their recorded knowledge response.
        # Never consume a historical board after a changed key.
        from tempfile import TemporaryDirectory
        from hengbot.cli import _consume_response_sequence
        from tests.test_home_withdraw_failed_stock_present_recorded import (
            HomeWithdrawFailedStockPresentRecordedTest as Capture, _policy, CALIBRATION)
        Capture.setUpClass()
        for restored in (False, True):
            with TemporaryDirectory() as raw:
                directory = Path(raw)
                policy = _policy(directory, Capture.monrace)
                policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
                for index in range(5):
                    if restored and index == 3:
                        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
                    _, boards = _consume_response_sequence(
                        Capture._board_lines(index), policy, lambda _key: True,
                        Capture.monrace, knowledge_ledger_path=directory / "knowledge.jsonl")
                    key = policy.choose_key(boards[-1])
                    historical = Capture.recorded[index]
                    self.assertEqual((str(key), policy.last_reason),
                                     (historical["key"], historical["reason"]))
                    if index == 2:
                        holder_id = policy._claim_register.current.claim_id
                    if index == 3:
                        self.assertEqual(policy.decision_claim["owner"], "equipment-txn")
                        self.assertEqual(policy.decision_claim["claim_id"], holder_id)
                        self.assertIsNone(policy.decision_claim["violation"])
                        self.assertEqual(policy._claim_register.current.execution.work_id,
                                         "equipment:acquire-home-catalog")
                        self.assertEqual(policy._claim_register.current.execution.continuation,
                                         "home.catalogue.acquire")
                    if index == 4:
                        closed = policy.decision_claim["closed_claim"]
                        self.assertEqual(closed["claim_id"], holder_id)
                        self.assertEqual(closed["closed"], "complete")
                        self.assertEqual(closed["closed_reason"], "home-knowledge-current")
                        self.assertTrue(policy._home_knowledge_current)
                    policy.confirm_key_posted(key)

    def test_restored_legacy_entry_declaration_still_requires_catalogue_evidence(self):
        policy, boards = attachment()
        with gzip.open(FIXTURE / "decisions.jsonl.gz", "rt", encoding="utf8") as source:
            recorded = next(map(json.loads, source))["claim"]
        goal = recorded["goal"]
        holder = policy._claim_register.declare("equipment-txn", observe(
            goal["expectation"], goal["within"], goal["source"]))
        execution = recorded["execution"]
        policy._claim_register.declare_execution(
            holder.claim_id, producer=execution["producer"], work_id=execution["work_id"],
            state=execution["state"], next_step=execution["next_step"],
            expected_effect=execution["expected_effect"], continuation=execution["continuation"])
        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        policy.last_reason = "home:queue-digging-tool-withdraw"
        policy._record_decision_claim(boards[1], "\x1b")
        shadow = policy.decision_claim["s33_shadow"]
        self.assertEqual(shadow["holder_claim_id"], holder.claim_id)
        self.assertEqual(shadow["holder_family"], "equipment-txn")
        self.assertEqual(shadow["would_stop"], "ownership:gate-missing:home-visit")
        # Independent partial-page attachment explains the withdraw ON row-3
        # divergence. Never feed this other incident as the effect of live23's 5.
        partial = parse_snapshot(json.loads(
            (FIXTURE / "partial-home-page.json").read_text(encoding="utf8")), {})
        self.assertEqual((partial.store.stock_num, len(partial.store.items)), (131, 52))
        for enforced in (False, True):
            policy, _ = attachment(enforced=enforced, crossarea=False)
            holder = policy._claim_register.declare("equipment-txn", observe(
                goal["expectation"], goal["within"], goal["source"]))
            policy._claim_register.declare_execution(
                holder.claim_id, producer=execution["producer"], work_id=execution["work_id"],
                state=execution["state"], next_step=execution["next_step"],
                expected_effect=execution["expected_effect"], continuation=execution["continuation"])
            self.assertEqual(policy._home_catalogue_work_key(partial), HOME_KNOWLEDGE_MACRO)
            self.assertEqual(policy.last_reason,
                             "equipment-transaction:catalogue-request-knowledge")
            self.assertFalse(policy._home_knowledge_current)
            policy._record_decision_claim(partial, HOME_KNOWLEDGE_MACRO)
            self.assertEqual(policy._claim_register.current.claim_id, holder.claim_id)
            policy.confirm_key_posted(HOME_KNOWLEDGE_MACRO)
            policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
            self.assertTrue(policy._home_knowledge_scan_inflight)
            self.assertIsNone(policy._town_holder_structural_stop(policy._claim_register.current, partial))



if __name__ == "__main__":
    unittest.main()
