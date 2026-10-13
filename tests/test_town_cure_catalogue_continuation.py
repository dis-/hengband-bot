"""D4 independent attachment after the recorded cure take at board 58.

The LIVE-KEY checkpoint ends at 57. From 58 onward every posted key is the
policy's own. The response from 63 is attached independently to the posted
59 request. The delayed outside await is DECLARED CONSTRUCTED; the recorded
66 confirmation is independently attached to the posted shovel take. This
proves the shovel continuation only: the carried speed potions are processed
without another take. It does not sanction the prefix divergence whitelist.
"""
import tests  # noqa: F401

from dataclasses import replace
import json
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence, _dispatch_response_lines
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO
import tests.test_town_cure_supplier_recorded as replay


class TownCureCatalogueContinuationTest(replay._RecordedProcess):
    @classmethod
    def setUpClass(cls):
        # DECLARED WALL: shorten only the inherited LIVE-KEY checkpoint.
        with patch.object(replay, "CHECKPOINT", 57):
            super().setUpClass()

    def _post(self, policy, board):
        key = policy.choose_key(board)
        row = key, policy.last_reason
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and replay.staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": str(key)})
        return row

    def _response(self, policy, lines):
        _dispatch_response_lines(
            lines, policy, lambda _key: True,
            knowledge_ledger_path=self.directory / "attached.jsonl")
        ledger = json.loads((self.directory / "attached.jsonl").read_text(
            encoding="utf-8").splitlines()[-1])
        self.assertTrue(ledger["accepted"])
        self.assertTrue(ledger["settled"])
        self.assertTrue(policy._home_knowledge_current)

    def test_own_keys_from_58_request_await_adopt_and_take_shovel(self):
        policy = self._resume()
        self.assertEqual(self._step(policy, 58)[:2],
                         ("5pC5\r\x1b", "home:atomic-withdraw"))
        key, reason, outside = self._step(policy, 59)
        self.assertEqual((key, reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        pending = tuple(policy._home_pending_batch)
        self.assertEqual([(sig[1], sig[2]) for sig in pending], [(20, 3), (75, 29)])
        epoch = policy._home_knowledge_scan_epoch
        self.assertTrue(policy._home_knowledge_scan_inflight)
        self.assertEqual(self._post(policy, replace(outside, turn=outside.turn + 1)),
                         ("", "home:scan-await-observation"))
        self.assertEqual(policy._home_knowledge_scan_epoch, epoch)
        self._response(policy, self.segments[63][:1])
        self.assertFalse(policy._home_knowledge_scan_inflight)
        self.assertIsNone(policy._home_knowledge_scan_epoch)
        current = replace(outside, turn=outside.turn + 2)
        self.assertEqual(self._post(policy, current),
                         ("5   pv\x1b", "home:atomic-withdraw"))
        telemetry = policy._home_atomic_withdraw_telemetry
        self.assertEqual((telemetry["resolved_index"], telemetry["resolved_page"],
                          telemetry["resolved_letter"]), (177, 3, "v"))
        self.assertEqual(tuple(telemetry["selected_signature"]), pending[0])
        # Independently attach the recorded confirmation: its pack gains exactly
        # this shovel and retains all nine already-carried speed potions.
        key, reason, observed = self._step(policy, 66)
        self.assertEqual((key, reason), ("5", "shop:travel:await-entry"))
        self.assertEqual(policy._inventory_signature_count(observed, pending[0]),
                         policy._inventory_signature_count(outside, pending[0]) + 1)
        self.assertEqual(policy._inventory_signature_count(outside, pending[1]), 9)
        self.assertEqual(policy._inventory_signature_count(observed, pending[1]), 9)
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        self.assertIsNone(policy._home_pending_item)
        self.assertEqual(policy._home_pending_batch, [])
        self.assertIn(pending[1], policy._processed_home_items)
        self.assertNotIn(pending[0], policy._deferred_home_items)
        self.assertNotIn(pending[1], policy._deferred_home_items)

    def test_wall_60_is_rendered_but_not_a_complete_catalogue(self):
        policy = self._resume()
        for index in (58, 59):
            self._step(policy, index, live_key=True)
        key, reason, board = self._step(policy, 60, live_key=True)
        self.assertEqual((key, reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        self.assertEqual((len(board.store.items), board.store.page_size,
                          board.store.page_top, board.store.stock_num),
                         (52, 52, 0, 197))
        self.assertFalse(policy._open_home_page_is_complete(board))
        self.assertTrue(policy._store_page_can_request_knowledge(board))
        self.assertFalse(policy._home_knowledge_scan_inflight)
        self.assertIsNone(policy._home_knowledge_scan_epoch)
        holder_id = policy._claim_register.current.claim_id
        self.assertEqual(policy._claim_register.current.owner.value, "home-scan")
        self.assertEqual(policy._home_visit.state.value, "approaching")
        self.assertEqual(policy._home_visit.request.item_identity[1:], (70, 26))
        self.assertEqual(policy._home_visit.queued, [])
        row = self._step(policy, 61, live_key=True)
        self.assertEqual(row[:2], ("3", "town:entrance-step-off:policy:none-wait"))
        self.assertFalse(policy._home_knowledge_current)
        self.assertTrue(policy._home_knowledge_invalidated)
        self.assertFalse(policy._home_knowledge_scan_inflight)
        self.assertIsNone(policy._home_knowledge_scan_epoch)
        self.assertIsNone(policy._home_pending_item)
        self.assertEqual([sig[1:] for sig in policy._home_pending_batch], [(20, 3), (75, 29)])
        self.assertEqual([request.item_identity[1:] for request in policy._home_visit.queued],
                         [(20, 3)])
        deferred = [row for row in policy._decision_errand_deferred
                    if row["deferred_reason"] == "entry:_shopping_approach_key#2"]
        self.assertEqual(len(deferred), 1)
        self.assertEqual((deferred[0]["holder_family"], deferred[0]["holder_claim_id"],
                          deferred[0]["token_would_admit"]), ("home-scan", holder_id, False))
        self.assertEqual(policy._town_turn_arbiter._retired, {})

    def test_genuinely_incomplete_rendered_home_page_still_exits(self):
        policy = self._resume()
        for index in (58, 59):
            self._step(policy, index, live_key=True)
        _, snapshots = _consume_response_sequence(
            self.segments[60], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl")
        page = snapshots[-1]
        # DECLARED CONSTRUCTED: one of the page's 52 rendered slots is missing.
        partial = replace(page, store=replace(page.store, items=page.store.items[:-1]))
        self.assertFalse(policy._store_page_can_request_knowledge(partial))
        self.assertEqual(self._post(policy, partial),
                         ("\x1b", "home:scan-incomplete-open-page"))
