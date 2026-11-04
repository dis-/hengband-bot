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
from unittest.mock import patch

from recorded_pack_budget import pre_pack_budget_replay
import tests  # noqa: F401
from hengbot import town_hold
from hengbot.model import parse_snapshot, _parse_items, StoreItem
from hengbot.policy import HengbotPolicy
from unittest.mock import patch
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO

FIXTURE = Path(__file__).parent / "fixtures/home-full-await-knowledge-20261004.json.gz"


# DECLARED CONSTRUCTED wall (#70, owner decision 2026-10-18 "junk first"):
# the recorded Home's worthless remains (tval 1/3/10) and emptied chest are
# treated as non-junk, so the Home-full relief still chooses among the sale
# stock this pin records instead of destroying a remain first.
_RECORDED_HOME_JUNK_AS_STOCK = patch.object(
    HengbotPolicy, "_is_worthless_junk", lambda _self, _item: False, create=True)


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
        # DECLARED CONSTRUCTED ledger: a two-stack blocked deposit budget.
        # Keep recorded inventory identities; no readiness/selection is patched.
        entries = tuple((policy._item_signature(item), item.count, item.count)
                        for item in board.inventory[-2:])
        policy._begin_home_full_relief(board, entries, refused=True)
        return policy

    def decide(self, policy, board):
        key = policy.choose_key(board)
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
                self.assertEqual(town_hold.standing_claim(policy).owner.value, "home-scan")
                self.assertTrue(policy._home_knowledge_scan_inflight)
                self.assertEqual(town_hold.standing_claim(policy).execution.expected_effect,
                                 "catalogue-adopted")
                # DECLARED CONSTRUCTED delayed response: keep the same store
                # visible until the requested catalogue arrives.
                waiting = replace(board, turn=board.turn + 1, messages=())
                self.assertEqual(self.decide(policy, waiting), "5")
                self.assertEqual(town_hold.standing_claim(policy).owner.value, "home-scan")
                self.assertTrue(policy._home_knowledge_scan_inflight)
                # First divergence is the scan command: do not replay the later
                # recorded ESC/router/detector boards against the changed key.

    @_RECORDED_HOME_JUNK_AS_STOCK
    @pre_pack_budget_replay  # W: 20 used; new rod stack before later relief sale; scan continuation subject.
    # Owner 2026-11-04: this small Home keeps its top 10; the flow is what is pinned.
    @patch("hengbot.item_fate.gear_surplus", return_value=True)
    @patch("hengbot.item_fate.gear_tier", return_value="room")
    def test_recorded_sale_delta_scans_then_selects_next_withdrawal(self, *_):
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
                scan_claim = policy._town_hold.claims.current
                self.assertEqual(scan_claim.owner.value, "home-scan")
                # DECLARED CONSTRUCTED response: the historical scan was not
                # requested at this sale. Remove its observed withdrawn stack
                # from the last recorded complete list, preserving all facts.
                identity = policy._sale_item_identity(sold)
                fresh = tuple(item for item in catalogue
                              if policy._sale_item_identity(item) != identity)
                policy.consume_home_knowledge(fresh)
                self.assertEqual(policy._town_hold.claims.current.claim_id, scan_claim.claim_id)
                self.assertEqual(policy._town_hold.claims.current.closed, "complete")
                self.assertFalse(policy._home_knowledge_scan_inflight)
                # Changed scan means subsequent town navigation is constructed.
                next_board = replace(sold_board, turn=sold_board.turn + 1, messages=())
                key = self.decide(policy, next_board)
                self.assertNotEqual(key, HOME_KNOWLEDGE_MACRO)
                # The sale freed a slot: the deposit takes it (n1-c life-130 20:27).
                self.assertIsNone(policy._home_full_relief)
                self.assertNotIn("detectors", town_hold.standing_claim(policy).owner.value)
