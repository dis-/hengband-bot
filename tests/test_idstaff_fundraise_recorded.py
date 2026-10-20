"""Recorded pin: the Identify-staff stockout kit must rebuy sold detection.

Live soak 2026-10-20 14:00 (c4-a life-014, Level 31, bot b8401802, capture
20261020-140000-town-blocked-departure-unsatisfiable): 10,595 gold, Identify
staff charges 18/20 on four staves, departure_block.failed
``["identify_staff_ready"]`` only, fundraising ``prepare`` with one planned
run (the #76 Identify-staff stockout time-pass, installed at decision_sequence
79).  Its mining kit lacked one Treasure Detection scroll: at
decision_sequence 52, before the time-pass existed, six scrolls had been sold
to the Alchemist as Home-full surplus.  From decision_sequence 82 on, the
in-store shelf evidence skipped the Alchemist's detection needs (``absent``:
the dry run refused the sold class as sell-rebuy churn), no owner was left,
and decision_sequence 115 posted ``("9", "town:blocked:departure-
unsatisfiable")``.

Substrate: the recorded raw state row of decision_sequence 115
(tests/extract_idstaff_fundraise_fixture.py) replayed through the public
response path (``_consume_response_sequence``, ``choose_key``) on one fresh
policy, with the live argv flags (cross-area fundraising, in-store shop
operations) and the recorded complete Home list (state row 71).

DECLARED CONSTRUCTED walls (the live process state before the window is not
replayable): the stockout time-pass state (fundraising mode "prepare", one
planned run, none completed, the Identify-staff mining plan; all recorded on
the rows); the store-attempted latches for Home, General Store and Black
Market (Home and General were visited after the plan's latch reset, decision
rows 82-108; Black Market was observed at decision_sequence 78); the sold
Treasure Detection class of this visit (recorded sale messages of
decision_sequence 52); the Alchemist shelf observed at turn 3088237 (recorded
on the in-store telemetry) built from the Alchemist page of capture
20261020-135723 state row 89 (turn 3086706, the same stay; 90 scrolls); the
current-town Magic Shop page from that capture's state row 95 (observed again
at turn 3087327 in this process, recorded on the shelf telemetry of
decision_sequence 51); the ``~f`` skill list of capture 20261020-103021.
Under these walls b8401802 replays the recorded ``("9",
"town:blocked:departure-unsatisfiable")``.
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import (
    STORE_ALCHEMIST, STORE_BLACK, STORE_GENERAL, STORE_HOME, STORE_MAGIC,
    _parse_items, parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.protocol import snapshot_protocol_version
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURE = Path(__file__).parent / "fixtures/idstaff-fundraise-20261020.json.gz"
SHA256 = "c14b485585752ee54ca2789a82aecfc8eeec82b29a392ecb76718772ee9230a9"
SHELF_TURN = 3088237
MAGIC_TURN = 3087327


class IdstaffFundraiseRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(raw))
        cls.skill = json.loads(cls.pin["skill_line"])
        cls.home = json.loads(cls.pin["home_line"])
        assert cls.skill["knowledge"]["category"] == "skill_exp"
        assert cls.home["knowledge"]["category"] == "home"
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.alchemist = parse_snapshot(
            json.loads(cls.pin["alchemist_line"]), cls.monrace).store
        cls.magic = parse_snapshot(
            json.loads(cls.pin["magic_line"]), cls.monrace).store
        cls.detection = next(
            item for item in cls.alchemist.items
            if item.is_treasure_detection_scroll)

    def replay(self):
        """Replay the board of decision_sequence 115; return (policy, board, result)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        policy = _policy(root, self.monrace)
        policy._crossarea_fundraising_enforced = True  # live argv
        policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
        _, boards = _consume_response_sequence(
            self.pin["lines"], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=root / "knowledge.jsonl")
        board = boards[-1]
        policy.prime(board)
        policy._fundraising_mode = "prepare"
        policy._planned_mining_runs = 1
        policy._mining_runs_completed = 0
        policy._identify_staff_mining_plan = True
        policy.consume_home_knowledge(tuple(_parse_items(
            self.home["knowledge"]["items"],
            protocol=snapshot_protocol_version(self.home))))
        policy._town_visit_sale_signatures.add(
            (self.detection.tval, self.detection.sval))
        policy._observe_shelf_evidence(
            replace(board, store=self.alchemist, turn=SHELF_TURN))
        policy._town_supplier_stock[STORE_MAGIC] = self.magic
        policy._town_supplier_stock_observations[STORE_MAGIC] = (
            policy._effective_town_id(board), MAGIC_TURN)
        for store_type in (STORE_HOME, STORE_GENERAL, STORE_BLACK):
            policy._set_town_store_attempted(store_type, board.turn, "visited")
        policy.consume_skill_knowledge(
            {**self.skill, "player": {"level": board.player.level}})
        board = policy.with_known_skill_exp(board)
        key = policy.choose_key(board)
        return policy, board, (str(key), policy.last_reason)

    def test_captured_rows(self):
        self.assertEqual(
            [(d["decision_sequence"], d["key"], d["reason"])
             for d in self.pin["decisions"]],
            [(113, "7", "shop:approach"),
             (114, "\x1b", "home:identify-staff-reserve-unavailable"),
             (115, "9", "town:blocked:departure-unsatisfiable")],
        )
        recorded = self.pin["recorded"]
        self.assertEqual(recorded["departure_block"]["failed"],
                         ["identify_staff_ready"])
        self.assertEqual(recorded["fundraising"]["mode"], "prepare")
        self.assertEqual(recorded["fundraising"]["planned_runs"], 1)
        self.assertEqual(recorded["player"]["gold"], 10595)
        self.assertEqual(recorded["procurement_requirements"], [
            {"item": "Treasure Detection scrolls", "current": 0, "target": 1,
             "missing": 1},
            {"item": "Identify staff charges", "current": 18, "target": 20,
             "missing": 2},
        ])
        self.assertEqual(
            [(entry["store"], entry["category"], entry["observed_turn"],
              entry["absent"])
             for entry in recorded["in_store"]["shelf_evidence_skips"]],
            [(STORE_ALCHEMIST, "fundraising-detection", SHELF_TURN, True),
             (STORE_ALCHEMIST, "mining-detection", SHELF_TURN, True)],
        )
        self.assertEqual(self.pin["sale_sequence"], 52)
        self.assertIn("6巻の 財宝感知の巻物 {@1}を $48で売却しました。",
                      self.pin["sale_messages"])
        self.assertEqual((self.detection.count, self.detection.price), (90, 24))

    def test_stockout_kit_rebuys_the_sold_detection_scroll(self):
        policy, board, result = self.replay()
        # b8401802: ("9", "town:blocked:departure-unsatisfiable") -- the sold
        # class made the Alchemist page "absent" for the mining kit, so no
        # owner was left and the recall gate's identify_staff_ready stopped town.
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(result, ("\x1b`n%.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_ALCHEMIST)
        self.assertTrue(policy._identify_staff_mining_plan)
        self.assertEqual(policy._fundraising_mode, "prepare")
        # On the Alchemist page the kit buys the Treasure Detection scroll.
        wanted = policy._next_purchase(replace(board, store=self.alchemist))
        self.assertEqual((wanted.tval, wanted.sval),
                         (self.detection.tval, self.detection.sval))

    def test_control_churn_guard_kept_without_a_mining_plan(self):
        # Control (constructed): outside a fundraising set the sold detection
        # class stays a refused sell-then-rebuy.
        policy, _board, _result = self.replay()
        self.assertFalse(policy._purchase_churn_rejected(
            STORE_ALCHEMIST, self.detection))
        policy._fundraising_mode = None
        self.assertTrue(policy._purchase_churn_rejected(
            STORE_ALCHEMIST, self.detection))


if __name__ == "__main__":
    unittest.main()
