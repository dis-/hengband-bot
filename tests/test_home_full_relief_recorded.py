"""Full-Home user decision, anchored to the 2026-10-03 23:40 capture.

DECLARED CONSTRUCTED: use the existing immutable capture (including its two
blocked deposit stacks, capacity 240, and refusal) and reconstructed posted
ledger. No onset checkpoint or successful recovery exists in that capture.
The corridor, surplus stock, and all command-dependent later observations are
constructed alternatives, not a replay after a changed historical command.
Only public choose_key, posting confirmation, and catalogue consumption drive
the recovery. No decision/selector/readiness collaborators are replaced.
"""
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.model import (InventoryItem, Position, StoreItem, StoreState,
    STORE_ALCHEMIST, STORE_HOME, TVAL_POTION, SV_POTION_RESIST_COLD)
from hengbot.policy_constants import STORE_STUCK_LIMIT
from hengbot.policy import HengbotPolicy
from policy_fixtures import grid
from test_home_route_release_recorded import reconstructed
from test_s33_batch_context import captured_session

FIXTURE = Path(__file__).parent / "fixtures/home-route-release-20261003.json.gz"


def relief_scene(pin, enforced, *, safe=3, excellent=False):
    policy, before, board, entries = reconstructed(pin, enforced)
    # DECLARED CONSTRUCTED stock: original capacity and two deposit identities
    # stay captured. Distinct unknown filler rows cannot be sold without ID.
    catalogue = tuple(InventoryItem(str(index), f"unknown reserve {index}", 1,
        TVAL_POTION, SV_POTION_RESIST_COLD, False, False)
        for index in range(pin["before"]["store"]["capacity"]))
    catalogue = tuple(replace(item, name=f"sale surplus {index}", known=True,
        aware=True, fully_known=True) if index < safe else item
        for index, item in enumerate(catalogue))
    if excellent:
        catalogue = (replace(catalogue[0], name="excellent unknown", known=False,
                            fully_known=False, pseudo_feeling="excellent"),
                     replace(catalogue[1], name="special unknown", known=False,
                            fully_known=False, pseudo_feeling="special"),
                     *catalogue[2:])
    policy.consume_home_knowledge(catalogue)
    board = replace(board, messages=tuple(pin["refused"]["messages"]),
        grids={**board.grids, Position(10, 9):
               replace(grid(10, 9), store_number=STORE_ALCHEMIST)})
    return policy, board, catalogue, entries


class HomeFullReliefTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
            "31ad6e4413b6d1681e176d63a6467aa3571c8d3a08bc1a50435e181278596302")
        cls.pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))

    def decide(self, policy, board, **changes):
        board = replace(board, turn=board.turn + 1, **changes)
        key = policy.choose_key(board)
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
        self.assertIsNone(policy.decision_claim["violation"])
        self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])
        if key:
            policy.confirm_key_posted(key)
        return board, key

    def refuse(self, policy, board):
        for _ in range(STORE_STUCK_LIMIT - 1):
            board, key = self.decide(policy, board)
            self.assertEqual(key, "5")
            self.assertEqual(policy.last_reason, "home:atomic-deposit-await-confirmation")
        return self.decide(policy, board)

    def home_page(self, catalogue):
        return StoreState(STORE_HOME, [StoreItem(chr(ord("a") + index),
            item.name, item.count, item.tval, item.sval, 20,
            known=item.known, aware=item.aware, fully_known=item.fully_known,
            pseudo_feeling=item.pseudo_feeling)
            for index, item in enumerate(catalogue[:12])],
            len(catalogue), 0, 12, 240)

    def test_refusal_withdraws_sells_two_slots_then_retries_original_deposit(self):
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, board, catalogue, entries = relief_scene(self.pins[0], enforced)
                # DECLARED CONSTRUCTED: restore the capture's real equipment
                # continuation alongside the reconstructed deposit ledger.
                _state, session = captured_session("234018", 224)
                policy._equipment_transaction_session = session
                board, key = self.refuse(policy, board)
                self.assertIsNotNone(policy._home_errand.request)
                self.assertEqual(policy._home_errand.request.purpose, "full-home-sale")
                self.assertEqual(policy._home_full_relief["remaining"], len(entries))
                for sale_number in range(len(entries)):
                    if sale_number:
                        # The asserted scan command receives the Home after the
                        # previous take, with shifted addresses and one less row.
                        self.assertEqual(key, "~9\x1b")
                        policy.consume_home_knowledge(catalogue)
                        board, key = self.decide(policy, board)
                    self.assertEqual(policy._home_errand.request.signature[0],
                                     catalogue[0].name)
                    board, key = self.decide(policy, board, messages=(),
                        player=replace(board.player, position=Position(10, 14)),
                        store=self.home_page(catalogue))
                    self.assertEqual(key, "\x1b")
                    board, key = self.decide(policy, board, store=None)
                    self.assertEqual(key, "5pa\x1b")
                    taken = replace(catalogue[0], slot="s")
                    catalogue = catalogue[1:]
                    board, key = self.decide(policy, board,
                                            inventory=(*board.inventory, taken))
                    self.assertIsNone(policy._home_atomic_withdraw_pending)
                    shop = StoreState(STORE_ALCHEMIST, [], 0, 0, 12)
                    board, key = self.decide(policy, board, store=shop,
                        player=replace(board.player, position=Position(10, 9)))
                    self.assertEqual(key, "{s@0\r")
                    board, key = self.decide(policy, board, inventory=tuple(
                        replace(item, inscription="@0", name=item.name + " {@0}")
                        if item.slot == "s" else item for item in board.inventory))
                    self.assertEqual(key, "\x1b")
                    board, key = self.decide(policy, board, store=None)
                    self.assertEqual(key, "5")
                    self.assertEqual(policy.last_reason, "shop:one-shot-sell")
                    board, key = self.decide(policy, board, store=shop)
                    self.assertEqual(key, "d0y\x1b")
                    board, key = self.decide(policy, board, store=None,
                        inventory=tuple(item for item in board.inventory if item.slot != "s"),
                        player=replace(board.player, gold=board.player.gold + 20))
                self.assertIsNone(policy._home_full_relief)
                self.assertEqual(key, "~9\x1b")
                self.assertEqual(policy.decision_claim["owner"], "home-scan")
                self.assertTrue(policy._home_knowledge_scan_inflight)
                self.assertIs(policy._equipment_transaction_session, session)
                self.assertEqual(catalogue[0].name, "sale surplus 2")
                self.assertTrue({entry[0] for entry in entries}.isdisjoint(
                    policy._home_rejected_deposits))
                policy.consume_home_knowledge(catalogue)
                board, key = self.decide(policy, board,
                    player=replace(board.player, position=Position(10, 14)),
                    store=self.home_page(catalogue))
                # Fresh page reauthorizes the original recorded deposit batch.
                if key == "\x1b":
                    board, key = self.decide(policy, board, store=None)
                    self.assertEqual(key, "5")
                    board, key = self.decide(policy, board, store=self.home_page(catalogue))
                self.assertTrue(key.startswith("d"), (key, policy.last_reason))
                self.assertTrue({entry[0] for entry in entries} <= {
                    entry[0] for entry in policy._home_atomic_deposit_pending[0]})
                original = {entry[0] for entry in entries}
                board, key = self.decide(policy, board, store=None,
                    inventory=tuple(item for item in board.inventory
                        if policy._item_signature(item) not in original))
                self.assertIsNone(policy._home_full_retry_deposits)
                self.assertIs(policy._equipment_transaction_session, session)

    def test_unidentified_excellent_and_special_are_not_selected_for_sale(self):
        for enforced in (False, True):
            policy, board, catalogue, _entries = relief_scene(
                self.pins[1], enforced, excellent=True)
            board, key = self.refuse(policy, board)
            self.assertIsNotNone(policy._home_errand.request)
            self.assertEqual(policy._home_errand.request.signature[0], "sale surplus 2")
            self.assertNotIn(policy._home_errand.request.signature[0],
                             ("excellent unknown", "special unknown", catalogue[3].name))

    def test_observed_capacity_triggers_relief_without_refusal_message(self):
        _checkpoint, board, catalogue, _entries = relief_scene(self.pins[0], True)
        from hengbot.model import parse_snapshot
        full = parse_snapshot(self.pins[0]["before"]).store
        self.assertEqual(getattr(full, "capacity", None), 240)
        # DECLARED CONSTRUCTED new episode: the first page observes capacity;
        # no command is pending and no refusal message is supplied.
        policy = HengbotPolicy()
        policy.prime(replace(board, messages=(), store=full))
        policy.consume_skill_knowledge(self.pins[0]["skill_knowledge"])
        policy.consume_home_knowledge(catalogue)
        board, key = self.decide(policy, board, messages=())
        self.assertIsNotNone(policy._home_errand.request)
        self.assertEqual(policy._home_errand.request.purpose, "full-home-sale")

    def test_unknown_surplus_requires_identification_before_disposal(self):
        for enforced in (False, True):
            policy, board, _catalogue, _entries = relief_scene(
                self.pins[2], enforced, safe=0)
            board, key = self.refuse(policy, board)
            self.assertEqual(policy._home_full_relief["mode"], "identify")
            self.assertNotIn("k", key or "")
            self.assertEqual(policy._home_errand.request.purpose, "full-home-discard")
            self.assertIsNone(policy._home_disposal_pending)
            self.assertIsNone(policy._pending_disposal_item)
