"""07:10:40 full-Home scan regression, using immutable incident rows.

DECLARED CONSTRUCTED: the process log retains boards, not a policy checkpoint.
Rebuild the relief/sale ledger and prior Home page/terrain observations.
The two-stack relief budget is constructed; no policy checkpoint survives
to prove the exact blocked deposit batch at 07:10:40.
No collaborator is replaced. The recorded board is valid through the first
changed key; any response/board after that point is a constructed alternative,
never claimed as historical replay. Full sale/take/deposit driving is also
covered by test_home_full_relief_recorded.
"""
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.model import parse_snapshot, _parse_items, StoreItem
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO

FIXTURE = Path(__file__).parent / "fixtures/home-full-await-knowledge-20261004.json.gz"


class HomeFullAwaitKnowledgeRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
            "9ec426659c3767361e9e4037488d1ae2909c2ce4cec8848ab429214136d28165")
        cls.pin = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        cls.rows = {entry["line"]: entry["row"] for entry in cls.pin["states"]}

    def policy_at(self, board, enforced):
        policy = HengbotPolicy(baseitem_costs={(tval, sval): cost
            for tval, sval, cost in self.pin["baseitem_costs"]})
        policy.prime(parse_snapshot(self.rows[58]))
        # DECLARED CONSTRUCTED substrate: restore geometry from the
        # recorded earlier Home exit, which the live process had observed.
        policy._build_grid_index(parse_snapshot(self.rows[59]))
        policy.prime(board)
        policy.consume_skill_knowledge(self.pin["skill_knowledge"]["row"])
        policy._town_claim_bar_enforced = enforced
        # DECLARED CONSTRUCTED ledger: a two-stack blocked deposit budget.
        # Keep recorded inventory identities; no readiness/selection is patched.
        entries = tuple((policy._item_signature(item), item.count, item.count)
                        for item in board.inventory[-2:])
        policy._begin_home_full_relief(board, entries, refused=True)
        return policy

    def decide(self, policy, board):
        key = policy.choose_key(board)
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
        self.assertIsNone(policy.decision_claim["violation"])
        self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])
        policy.confirm_key_posted(key)
        return key

    def test_071040_board_requests_scan_instead_of_recorded_escape(self):
        board = parse_snapshot(self.rows[75])
        historical = self.pin["decisions"][-1]["row"]
        self.assertEqual(board.turn, historical["turn"])
        self.assertEqual(historical["key"], "\x1b")
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = self.policy_at(board, enforced)
                self.assertEqual(self.decide(policy, board), HOME_KNOWLEDGE_MACRO)
                self.assertEqual(policy.decision_claim["owner"], "home-scan")
                self.assertTrue(policy._home_knowledge_scan_inflight)
                self.assertEqual(policy.decision_claim["execution"]["expected_effect"],
                                 "catalogue-adopted")
                # DECLARED CONSTRUCTED delayed response: keep the same store
                # visible until the requested catalogue arrives.
                waiting = replace(board, turn=board.turn + 1, messages=())
                self.assertEqual(self.decide(policy, waiting), "5")
                self.assertEqual(policy.decision_claim["owner"], "home-scan")
                self.assertTrue(policy._home_knowledge_scan_inflight)
                # First divergence is the scan command: do not replay the later
                # recorded ESC/router/detector boards against the changed key.

    def test_recorded_sale_delta_scans_then_selects_next_withdrawal(self):
        sale_board = parse_snapshot(self.rows[70])
        sold_board = parse_snapshot(self.rows[72])
        sold = next(item for item in sale_board.inventory
                    if item.slot == "i")
        self.assertFalse(any(item.name == sold.name for item in sold_board.inventory))
        self.assertGreater(sold_board.player.gold, sale_board.player.gold)
        catalogue = tuple(_parse_items(self.rows[54]["knowledge"]["items"], protocol=3))
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy = self.policy_at(parse_snapshot(self.rows[66]), enforced)
                policy.consume_home_knowledge(catalogue)
                policy._home_full_relief["sale"] = (policy._item_signature(sold),
                                                     sale_board.store.store_type, 0)
                policy._home_full_relief["withdrawn"] = True
                # Recorded sale prefix. Every subsequent board is used only
                # after the preceding key matches its historical command.
                for line, expected in ((66, "{i@0\r"), (67, "\x1b"),
                                       (68, "5"), (70, "d0y\x1b")):
                    self.assertEqual(self.decide(policy, parse_snapshot(self.rows[line])),
                                     expected, f"first divergence at state line {line}")
                self.assertEqual(self.decide(policy, sold_board), HOME_KNOWLEDGE_MACRO)
                self.assertEqual(policy._home_full_relief["remaining"], 1)
                scan_claim = policy._claim_register.current
                self.assertEqual(scan_claim.owner.value, "home-scan")
                # DECLARED CONSTRUCTED response: the historical scan was not
                # requested at this sale. Remove its observed withdrawn stack
                # from the last recorded complete list, preserving all facts.
                identity = policy._sale_item_identity(sold)
                fresh = tuple(item for item in catalogue
                              if policy._sale_item_identity(item) != identity)
                policy.consume_home_knowledge(fresh)
                self.assertEqual(policy._claim_register.current.claim_id, scan_claim.claim_id)
                self.assertEqual(policy._claim_register.current.closed, "complete")
                self.assertFalse(policy._home_knowledge_scan_inflight)
                # Changed scan means subsequent town navigation is constructed.
                next_board = replace(sold_board, turn=sold_board.turn + 1, messages=())
                key = self.decide(policy, next_board)
                self.assertNotEqual(key, HOME_KNOWLEDGE_MACRO)
                self.assertIsNotNone(policy._home_full_relief["sale"])
                self.assertEqual(policy._home_errand.request.purpose, "full-home-sale")
                self.assertIn(policy._home_errand.request.signature,
                              {policy._item_signature(item) for item in fresh})
                self.assertNotEqual(policy._home_errand.request.signature,
                                    policy._item_signature(sold))
                self.assertNotIn("detectors", policy.decision_claim["owner"])

                # DECLARED CONSTRUCTED arrival/withdrawal after divergence.
                # Use the recorded Home location; the complete fresh catalogue
                # supplies the atomic withdrawal's current address authority.
                home = parse_snapshot(self.rows[58])
                arrival = replace(next_board, turn=next_board.turn + 1,
                                  player=replace(next_board.player,
                                                 position=home.player.position),
                                  grids=parse_snapshot(self.rows[59]).grids,
                                  store=replace(home.store, stock_num=len(fresh),
                                      page_top=0, items=tuple(StoreItem(
                                          chr(ord("a") + index), item.name, item.count,
                                          item.tval, item.sval, 0, known=item.known,
                                          aware=item.aware, fully_known=item.fully_known)
                                          for index, item in enumerate(fresh[:12]))))
                self.assertEqual(self.decide(policy, arrival), "\x1b")
                outside = replace(arrival, turn=arrival.turn + 1, store=None)
                take_key = self.decide(policy, outside)
                self.assertTrue(take_key.startswith("5p"), (take_key, policy.last_reason, policy._home_pending_item))
                request = policy._home_errand.request
                taken = next(item for item in fresh
                             if policy._item_signature(item) == request.signature)
                observed = replace(outside, turn=outside.turn + 1,
                                   inventory=(*outside.inventory,
                                              replace(taken, slot="u")))
                self.decide(policy, observed)
                self.assertIsNone(policy._home_atomic_withdraw_pending)
                self.assertTrue(policy._home_full_relief["withdrawn"])
