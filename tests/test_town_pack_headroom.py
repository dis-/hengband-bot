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
from hengbot.model import parse_snapshot, TVAL_POTION, SV_POTION_INC_STR
from hengbot.town_pack_headroom import eligible, preservable, find_sale, find_deposit
from hengbot.town_terminal import rung_terminal, terminal_admission
from tests import test_input_executor as harness
from tests.support.headroom_home import HeadroomHomeGame
from tests.test_esp_threat_rest_recorded import _policy


FIXTURE = Path(__file__).with_name("fixtures") / "pack-headroom-20261029.json.gz"


class TownPackHeadroomTest(harness.ProductionHarness):
    def attached(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                         "abe02da62290becae19a1b8c24a516f1b1563f21783af6947a124056e9068671")
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
        policy, after, record = self.drive_home(charged_staff=False)
        # The actual recorded supplier (not Home) has a 16-charge staff.
        # Carry the interpreter's observed transfer effect to that shelf.
        page = parse_snapshot(record["magic_page"]).store
        before = replace(parse_snapshot(record["board"]), store=page)
        self.assertIsNone(policy._next_purchase(before))
        selected = policy._next_purchase(replace(after, store=page))
        self.assertIsNotNone(selected)
        self.assertEqual((selected.tval, selected.sval, selected.charges), (55, 5, 16))

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
        self.assertEqual(minimum_pack, 12, reasons)  # Seven released stacks, not just the floor.
        if charged_staff:
            self.assertTrue(any(reason == "home:atomic-withdraw" for _, reason in reasons), reasons)
            self.assertTrue(policy._identify_staff_ready(parse_snapshot(game._state())), reasons)
        self.assertLessEqual(len(game.pack), 19)
        final = parse_snapshot(game._state())
        for reservation in record["facts"]["retention_reservations"]:
            retained = sum(item.count for item in final.inventory
                           if list(policy._item_signature(item)) == reservation["signature"])
            self.assertGreaterEqual(retained, reservation["reservation"], reservation)
        return policy, final, record

    def test_beneficial_use_precedes_shelving(self):
        policy, board, _ = self.attached()
        gain = replace(board.inventory[1], tval=TVAL_POTION, sval=SV_POTION_INC_STR,
                       name="Strength", count=1)
        view = replace(board, inventory=[gain, board.inventory[3]])
        self.assertEqual(policy._town_space_deposit_key(view), "qb")
        self.assertEqual(policy.last_reason, "stat-gain:quaff")

    def test_terminal_relief_shares_the_early_owners_beneficial_use_priority(self):
        policy, board, _ = self.attached()
        gain = replace(board.inventory[1], slot="t", name="Strength", count=1,
                       tval=TVAL_POTION, sval=SV_POTION_INC_STR)
        view = replace(board, inventory=[*board.inventory, gain])
        self.assertEqual(len(view.inventory), 20)
        self.assertEqual(policy._town_overflow_destroy_key(view, try_relief=True), "qt")
        self.assertEqual(policy.last_reason, "stat-gain:quaff")

    def test_overflow_waits_for_its_posted_home_census_instead_of_blocking(self):
        policy, board, _ = self.attached()
        extra = replace(board.inventory[1], slot="t", inscription="spare")
        view = replace(board, inventory=[*board.inventory, extra])
        policy._invalidate_home_observation()
        request = policy._town_overflow_destroy_key(view, try_relief=True)
        self.assertEqual(policy.last_reason, "home:request-knowledge-scan")
        self.assertTrue(policy.confirm_key_posted(request))
        self.assertEqual(policy._town_overflow_destroy_key(
            replace(view, turn=view.turn + 1), try_relief=True), "")
        self.assertEqual(policy.last_reason, "home:scan-await-observation")
        self.assertIsNone(policy._town_blocked_reason)

    def test_four_free_slots_with_full_home_routes_sale_before_shopping(self):
        policy, board, record = self.attached()
        policy._home_capacity_observation = (240, 240, policy._effective_town_id(board))
        self.assertTrue(policy._home_is_full(board))
        key = policy.choose_key(board)
        self.assertIsNotNone(key)
        self.assertIn(policy.last_reason, {"shop:travel", "shop:approach"})
        self.assertEqual(policy._shopping_approach_store_type, 5)
        self.assertFalse(key.startswith("p"))

    def test_refused_or_bounded_home_allows_sale_fallback(self):
        policy, board, _ = self.attached()
        candidate = next(item for item in board.inventory if item.slot == "b")
        policy._home_rejected_deposits.add(policy._item_signature(candidate))
        self.assertEqual(find_sale(policy, board), candidate)
        policy._home_rejected_deposits.clear()
        policy._town_visit_ledger.unsatisfied_passes[7] = policy._town_store_visit_limit(7)
        policy._town_visit_ledger.blocked_stores.add(7)
        self.assertFalse(policy._town_space_deposit_actionable(board))
        self.assertEqual(find_sale(policy, board), candidate)

    def test_optional_surplus_can_use_a_visited_outlet_until_it_refuses_sale(self):
        policy, board, _ = self.attached()
        view = replace(board, inventory=board.inventory[:14])
        candidate = next(item for item in view.inventory if item.slot == "b")
        policy._home_capacity_observation = (240, 240, policy._effective_town_id(view))
        policy._town_store_attempted[5] = view.turn
        self.assertEqual(policy._town_organization_sale_store(view, candidate), 5)
        policy._store_sale_refused.add(5)
        self.assertNotEqual(policy._town_organization_sale_store(view, candidate), 5)

    def test_junk_is_destroyed_without_home_deposit(self):
        policy, board, _ = self.attached()
        junk = replace(board.inventory[1], name="Junk", tval=3, sval=0, count=1)
        view = replace(board, inventory=[junk])
        self.assertIsNotNone(policy._junk_class(view, junk))
        self.assertIsNone(find_deposit(policy, view))
        key = policy._town_space_deposit_key(view)
        self.assertTrue(key.endswith("kb"), key)
        self.assertEqual(policy.last_reason, "inventory:destroy-worthless-junk")

    def test_zero_slot_home_merge_keeps_its_existing_owner(self):
        policy, board, _ = self.attached()
        carried = next(item for item in board.inventory if item.slot == "c")
        incoming = replace(carried, slot="home", count=1)
        policy._home_knowledge_items = (*policy._home_knowledge_items, incoming)
        policy._home_pending_item = policy._item_signature(incoming)
        policy._home_pending_quantity = 1
        self.assertFalse(eligible(policy, board))
        self.assertIsNone(policy._town_space_deposit_key(board))

    def test_posted_home_operation_is_not_preempted(self):
        policy, board, _ = self.attached()
        policy.choose_key(board)
        self.assertIsNotNone(policy._home_atomic_deposit_pending)
        self.assertFalse(eligible(policy, board))

    def test_queued_nonstacking_withdrawal_yields_to_deposit_before_spending_a_slot(self):
        policy, board, _ = self.attached()
        staff = next(item for item in policy._home_knowledge_items
                     if item.tval == 55 and item.sval == 5)
        staff = replace(staff, name="Identify staff (20 charges)", charges=20, pval=20)
        policy._home_knowledge_items = tuple(staff if item.tval == 55 and item.sval == 5
                                             else item for item in policy._home_knowledge_items)
        policy._home_pending_item = policy._item_signature(staff)
        policy._home_pending_quantity = 1
        view = replace(board, inventory=board.inventory[:18])
        policy.choose_key(view)
        self.assertEqual(policy.last_reason, "home:atomic-deposit")
        self.assertIsNone(policy._home_atomic_withdraw_pending)

    def test_bounty_priority_also_applies_when_home_is_full(self):
        policy, board, _ = self.attached()
        policy._home_capacity_observation = (240, 240, policy._effective_town_id(board))
        bounty = replace(board.inventory[1], slot="t", is_bounty=True)
        view = replace(board, inventory=[*board.inventory, bounty])
        terminal = rung_terminal(policy, "_town_space_deposit_key", view)
        self.assertIsNotNone(terminal)
        self.assertFalse(terminal_admission(policy, view, terminal).admitted)

    def test_unstarted_purchase_yields_to_headroom_even_above_four_free_slots(self):
        policy, board, record = self.attached()
        page = parse_snapshot(record["home_page"]).store
        ware = replace(page.items[0], letter="a", name="Teleport", tval=70,
                       sval=9, count=99, price=1, known=True, aware=True)
        essentials = [item for item in board.inventory
                      if item.slot in {"a", "c", "e", "f", "j", "n", "o", "p", "q", "r", "s"}]
        clean = replace(board, inventory=essentials,
                        store=replace(page, store_type=5, items=[ware]))
        self.assertEqual(policy._next_purchase(clean), ware)
        surplus = next(item for item in board.inventory if item.slot == "b")
        self.assertIsNone(policy._next_purchase(replace(clean, inventory=[*essentials, surplus])))

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
