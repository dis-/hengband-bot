"""#47 / #119: town headroom on the life-394 four-free-slot stop.

Attachment wall: the capture has no Python checkpoint. Attach the recorded
stop board, preceding ~9 answer and fundraising facts to the established
static-game policy helper. Skill census is constructed to isolate town work;
the helper's calibration is not claimed to be this character's. The Home
command interpreter constructs responses after the first changed decision.
"""
from __future__ import annotations

import tests  # noqa: F401 -- runtime-file isolation
import copy
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from hengbot.cli import _consume_response_sequence, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from hengbot.town_pack_headroom import eligible, preservable
from tests import test_input_executor as harness
from tests.support.headroom_home import HeadroomHomeGame
from tests.test_esp_threat_rest_recorded import _policy


FIXTURE = Path(__file__).with_name("fixtures") / "pack-headroom-20261029.json.gz"


class TownPackHeadroomTest(harness.ProductionHarness):
    def attached(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                         "8456076250b68d338d98b017cc562cf73688447aacc7e39864673ba2917ad7c3")
        record = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        policy = _policy(Path(temporary.name), {})
        self.home_answer(policy, record["home"])
        policy._home_page_size = record["home_page"]["store"]["page_size"]
        board = parse_snapshot(record["board"])
        policy.prime(board)
        facts = record["facts"]["fundraising"]
        policy._fundraising_mode = facts["mode"]
        policy._planned_mining_runs = facts["planned_runs"]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return policy, board, record

    def home_answer(self, policy, raw):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        _consume_response_sequence([json.dumps(raw)], policy, lambda key: True, {},
                                  knowledge_ledger_path=Path(directory.name) / "knowledge.jsonl")

    def test_captured_stop_frees_room_through_public_follow(self):
        self.drive_home(charged_staff=False)

    def test_charged_home_staff_is_taken_after_freeing_room_through_public_follow(self):
        self.drive_home(charged_staff=True)

    def drive_home(self, *, charged_staff):
        policy, board, record = self.attached()
        self.assertEqual(len(board.inventory), 19)
        self.assertEqual(record["facts"]["departure_block"]["failed"],
                         ["identify_staff_ready", "equipment_departure_ready"])
        raw = copy.deepcopy(record["board"])
        if charged_staff:
            # The capture's only Home Identify staff is empty. This explicit
            # variant supplies a usable one to pin acquisition after relief.
            for items in (record["home"]["knowledge"]["items"],
                          record["home_page"]["store"]["items"]):
                for item in items:
                    if item["tval"] == 55 and item["sval"] == 5:
                        item.update(name="Identify staff (20 charges)", charges=20, pval=20)
            self.home_answer(policy, record["home"])
        game = HeadroomHomeGame(pack=raw["inventory"],
            equipment={item["slot"]: item for item in raw["equipment"]},
            pages=[copy.deepcopy(record["home_page"]["store"]["items"])],
            inside=False, state_template=raw, home_limit=240)
        game.turn = board.turn
        _, _, executor = self.make(game)
        executor.drain = lambda: [game._state()]
        result = executor.observe_boundary(deadline=time.monotonic() + 5)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                  request_budget=2, policy=policy)
        reasons = []
        minimum_pack = len(game.pack)
        for _ in range(18):
            current = parse_snapshot(result.board)
            key = policy.choose_key(current)
            reason = policy.last_reason
            reasons.append((key, reason))
            self.assertIsNotNone(key, reasons)
            self.assertFalse(reason.startswith("town:blocked:"), reasons)
            _send_new_decision_key(port, json.dumps(result.board), key, None, set(),
                in_store=current.store is not None, snapshot=current,
                decision={"sequence": policy._decision_sequence, "reason": reason, "key": key})
            result = port.last_result
            self.assertIsNotNone(result, reasons)
            self.assertEqual(result.outcome, "completed", (reasons, result.reason, game.trace[-15:]))
            policy.confirm_key_posted(key)
            minimum_pack = min(minimum_pack, len(game.pack))
            if not charged_staff and minimum_pack < 19:
                break  # First changed command and its actual transfer effect.
            if "request-knowledge-scan" in reason:
                # Construct the fresh ~9 catalogue from effects of accepted
                # transfer keys; the original catalogue has changed addresses.
                answer = copy.deepcopy(record["home"])
                answer.update(game._state())
                answer["type"] = "knowledge"
                answer["knowledge"]["items"] = copy.deepcopy(game._items())
                self.home_answer(policy, answer)
            if any(item.get("tval") == 55 and item.get("sval") == 5
                   and item.get("charges", 0) >= 10 for item in game.pack):
                break
        self.assertEqual(reasons[0][1], "home:atomic-deposit", reasons)
        self.assertLess(minimum_pack, 19, reasons)
        if charged_staff:
            self.assertTrue(any(reason == "home:atomic-withdraw" for _, reason in reasons), reasons)
            self.assertTrue(policy._identify_staff_ready(parse_snapshot(game._state())), reasons)
        self.assertLessEqual(len(game.pack), 19)

    def test_four_free_slots_with_full_home_routes_sale_before_shopping(self):
        policy, board, record = self.attached()
        policy._home_capacity_observation = (240, 240, policy._effective_town_id(board))
        self.assertTrue(policy._home_is_full(board))
        key = policy.choose_key(board)
        self.assertIsNotNone(key)
        self.assertIn(policy.last_reason, {"shop:travel", "shop:approach"})
        self.assertEqual(policy._shopping_approach_store_type, 5)
        self.assertFalse(key.startswith("p"))

    def test_unstarted_purchase_yields_to_headroom_even_above_four_free_slots(self):
        policy, board, record = self.attached()
        view = replace(board, inventory=board.inventory[:18])
        page = parse_snapshot(record["home_page"]).store
        view = replace(view, store=replace(page, store_type=5))
        self.assertIsNone(policy._next_purchase(view))

    def test_headroom_keeps_freeing_stacks_above_the_floor(self):
        policy, board, _ = self.attached()
        candidate = next(item for item in board.inventory if item.slot == "b")
        for used in (19, 18, 10):
            with self.subTest(used=used):
                view = replace(board, inventory=board.inventory[:used])
                self.assertTrue(preservable(policy, view, candidate))
                self.assertIsNotNone(policy._find_home_deposit(view))
                self.assertTrue(policy._town_space_deposit_actionable(view))

    def test_reservations_purchases_unknowns_and_junk_stay_protected(self):
        policy, board, _ = self.attached()
        candidate = next(item for item in board.inventory if item.slot == "b")
        self.assertTrue(preservable(policy, board, candidate))
        for item in board.inventory:
            if policy._retention_reservation(board, item):
                self.assertFalse(preservable(policy, board, item))
        for item in board.inventory:
            if item.tval == 55 and item.sval == 5:
                self.assertFalse(preservable(policy, board, item))
        self.assertFalse(preservable(policy, board, replace(candidate, known=False)))
        self.assertFalse(preservable(policy, board, replace(candidate, is_cursed=True)))
        policy._town_visit_purchases.add(policy._item_signature(candidate))
        self.assertFalse(preservable(policy, board, candidate))

    def test_no_headroom_during_recall_or_equipment_work(self):
        policy, board, _ = self.attached()
        self.assertTrue(eligible(policy, board))
        self.assertFalse(eligible(policy, replace(board, player=replace(board.player, recalling=True))))
