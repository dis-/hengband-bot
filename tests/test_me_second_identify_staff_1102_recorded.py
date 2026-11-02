"""n1-c life-106 (2026-11-02 15:49): a second Identify staff stopped the Magic shop entry.

The Magic-Eater (Lv8, after Q1) entered the Magic shop and the staff sequence
bought its stage-1 staffs (Identify 13 charges ``pl``, Treasure Detection 14
``pp``); the entry then bought, inscribed and sold up to the existing budget
of 8 operations (decisions 3530-3537).  On the page after the eighth the pure
departure-blocking preflight still required row j, Identify staff
(15 charges): the carried Identify charges (13) were short of 20 for the
planned depth 19.  ``_shop`` never wanted that row — after Q1 the staff
sequence alone buys these staffs (me_capability.REPLACES, uses ORDER and
CANDIDATE; owner 「2本目は買わない」) — but the preflight asked only the
PURCHASE use, so the entry stopped on shop-required-operation-uncomposable.
Now the preflight refuses every row the ordinary order refuses, and the
entry leaves.

Every decision goes through the public choose_key; the leave key is posted
through the production executor.
DECLARED RECONSTRUCTED:
  - the staff sequence record (powers read, the absorbed Light staff, the
    shelf turn, one rumor batch) is the capture's policy-state at the stop;
  - the ~f skill row is the earliest one left in the life's state.jsonl
    (turn 1310445: two-weapon and shield exp 0, which can only have grown),
    with its level set to the board's (8);
  - the optimizer's planned depth is the recorded decisions' 19 (the life's
    calibration was rewritten later at a higher level);
  - the replay's entry ledger is set to the recorded 8 operations on the stop
    board: this fresh process posts the recorded first two buys, but the
    capture lacks the state of the owners of the other six (the Wand of
    Wonder and Remove Curse staff buys, two inscribed sales).
DECLARED CONSTRUCTED: the board after the leave key (the stop board outside
the shop).
Fixture: tests/extract_me_second_identify_staff_1102_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files

import copy
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_staff_sequence
from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import STORE_STUCK_LIMIT
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness
from tests.test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "me-second-identify-staff-1102.json.gz"
SHA256 = "fcb4a8b333ff9e78dc70671474e51e62100efd43e7c1086647daf96f10373be0"


class MagicEaterSecondIdentifyStaffRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.data = json.loads(gzip.decompress(payload))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def policy(self):
        boards = self.data["boards"]
        directory = Path(self.enterContext(TemporaryDirectory()))
        policy = _policy(directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        policy._in_store_ops_enabled = True
        policy._in_store_screen_verified = True
        policy._equipment_optimization_last_depth = self.data["decisions"][-1]["optimization_depth"]
        policy.prime(parse_snapshot(copy.deepcopy(boards["home"]), policy._monrace_knowledge))
        skill = copy.deepcopy(self.data["skill_exp"])
        skill["player"]["level"] = boards["home"]["player"]["level"]
        policy.consume_skill_knowledge(skill)
        recorded = self.data["staff_sequence"]
        record = me_staff_sequence.state(policy)
        record.powers_read = recorded["powers_read"]
        record.absorbed = dict(recorded["absorbed"])
        record.shelf_after_turn = recorded["shelf_after_turn"]
        record.rumor_batches = recorded["rumor_batches"]
        policy.test_directory = directory
        return policy

    def decide(self, policy, name):
        _decoded, snapshots = _consume_response_sequence(
            [json.dumps(self.data["boards"][name], ensure_ascii=False)], policy,
            lambda _key: True, self.monrace,
            knowledge_ledger_path=policy.test_directory / "knowledge.jsonl")
        return policy.choose_key(snapshots[-1]), policy.last_reason

    def test_recorded_entry_ends_on_the_second_identify_staff(self):
        decisions = self.data["decisions"]
        self.assertEqual([row["ops"] for row in decisions[1:-1]], list(range(STORE_STUCK_LIMIT)))
        stop = decisions[-1]
        self.assertEqual((stop["key"], stop["reason"]),
                         ("\x1b", "town:blocked:shop-required-operation-uncomposable"))
        self.assertEqual((stop["required"]["cause"], stop["required"]["row"],
                          stop["required"]["signature"]),
                         ("entry-budget", "j", ["鑑定の杖 (15回分)", 55, 5]))

    def test_entry_at_its_budget_leaves_without_the_second_staff(self):
        policy = self.policy()
        self.decide(policy, "home")
        recorded = [(row["key"], row["reason"]) for row in self.data["decisions"][:3]]
        self.assertEqual([self.decide(policy, name) for name in
                          ("outside", "shop-first", "shop-second")], recorded)
        policy._in_store_entry_ledger["ops"] = STORE_STUCK_LIMIT
        stop_board = self.data["boards"]["shop-stop"]
        key, reason = self.decide(policy, "shop-stop")
        # 9afd9203e: ('\x1b', 'town:blocked:shop-required-operation-uncomposable').
        self.assertEqual((key, reason), ("\x1b", "shop:in-store-done"))
        self.assertNotIn("required-page-continuation", policy._shop_selector_diagnostics)
        outside = copy.deepcopy(stop_board)
        outside["store"] = None
        outside["type"] = "player_turn"
        self.post(policy, stop_board, key, outside)


if __name__ == "__main__":
    import unittest
    unittest.main()
