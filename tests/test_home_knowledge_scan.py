import json
import inspect
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hengbot.cli import (
    _consume_response_sequence,
    _decoded_board_in_town,
    _decision_record,
    _dispatch_response_lines,
    _newest_snapshot,
)
from hengbot.equipment_optimizer import OwnedEquipmentCatalog
from hengbot.home_errand import HomeErrandRequest, HomeErrandState
from hengbot.model import (
    GridState, InventoryItem, PlayerState, Position, Snapshot, StoreState,
    parse_snapshot,
)
from hengbot.policy import CHARACTER_DUMP_MACRO, HengbotPolicy, STORE_HOME
from hengbot.home_entry_capture import STATE_FIELDS
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from policy_fixtures import store_item


def setUpModule():
    global _knowledge_tmp, _knowledge_patch
    _knowledge_tmp = TemporaryDirectory()
    _knowledge_patch = patch(
        "hengbot.cli.KNOWLEDGE_RESPONSE_LEDGER_PATH",
        Path(_knowledge_tmp.name) / "knowledge-responses.jsonl",
    )
    _knowledge_patch.start()


def tearDownModule():
    _knowledge_patch.stop()
    _knowledge_tmp.cleanup()


def town_with_home() -> Snapshot:
    player_position = Position(10, 10)
    home_position = Position(10, 11)
    grids = {
        player_position: GridState(
            player_position, True, True, False, False, False, False, False
        ),
        home_position: GridState(
            home_position,
            True,
            True,
            False,
            False,
            False,
            False,
            False,
            store_number=STORE_HOME,
        ),
    }
    return Snapshot(
        PlayerState(player_position, 20, 20, 0, 0, 16),
        grids,
        [],
        turn=542954,
        town_flag=True,
    )


def confirm_outside_after_home_leave(
    policy: HengbotPolicy, snapshot: Snapshot
) -> None:
    policy._home_knowledge_scan_leave_turn = snapshot.turn - 1


def home_response() -> dict:
    return {
        "type": "knowledge",
        "knowledge": {
            "category": "home",
            "menu_key": "9",
            "items": [
                {
                    "slot": 3,
                    "name": "Long Sword",
                    "count": 1,
                    "tval": 23,
                    "sval": 17,
                    "aware": True,
                    "known": True,
                    "fully_known": True,
                    "is_equipment": True,
                    "to_h": 4,
                    "to_d": 5,
                    "damage_dice": {"num": 2, "sides": 5},
                },
                {
                    "slot": 8,
                    "name": "Arrows",
                    "count": 20,
                    "tval": 17,
                    "sval": 1,
                    "aware": True,
                    "known": True,
                },
            ],
        },
        "player": {"position": {"y": 10, "x": 10}},
    }


def board_response(snapshot: Snapshot) -> dict:
    return {
        "type": "player_turn",
        "turn": snapshot.turn,
        "player": {"position": {"y": 10, "x": 10}},
        "floor": {
            "dungeon_id": 0 if snapshot.in_town else 1,
            "level": 0 if snapshot.in_town else 1,
            "in_town": snapshot.in_town,
        },
    }


def home_digger_response() -> dict:
    response = home_response()
    response["knowledge"]["items"] = [
        {
            "slot": slot,
            "name": name,
            "count": count,
            "tval": 20,
            "sval": sval,
            "aware": True,
            "known": True,
            "fully_known": True,
            "is_equipment": True,
            "pval": pval,
            "to_h": to_h,
            "to_d": to_d,
            "damage_dice": {"num": 1, "sides": 2},
        }
        for slot, name, count, sval, pval, to_h, to_d in (
            (1, "Shovel", 4, 1, 0, 0, 0),
            (2, "Pick", 3, 4, 0, 0, 0),
            (3, "Mattock", 2, 5, 0, 0, 0),
            (4, "Dwarven Pick (1d2) (+9,+7) (+4)", 5, 4, 4, 9, 7),
        )
    ]
    return response


class HomeKnowledgeScanTest(unittest.TestCase):
    @staticmethod
    def _scan_policy():
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((("a", "captured", 17, 1),))
        snapshot = town_with_home()
        confirm_outside_after_home_leave(policy, snapshot)
        return policy, snapshot

    def test_pin_a1_one_loss_stops_then_new_visit_rearms(self):
        policy, town = self._scan_policy()
        self.assertEqual(policy.choose_key(town), "~9\x1b\x1b")
        policy.confirm_key_posted("~9\x1b\x1b")

        decisions = []
        for _ in range(8):
            decisions.append((policy.last_reason, policy.choose_key(town)))
            decisions[-1] = (policy.last_reason, decisions[-1][1])
            if policy.last_reason.startswith("town:blocked"):
                break
        self.assertNotIn("~9\x1b\x1b", [key for _reason, key in decisions])
        self.assertEqual(decisions[-1], ("town:blocked:owner-retired", "5"))
        self.assertTrue(policy._home_knowledge_scan_inflight)
        self.assertEqual(policy._home_knowledge_scan_epoch, town.turn)

        dungeon = Snapshot(
            town.player, town.grids, [], turn=town.turn + 10, town_flag=False,
            floor_key=(1, 1, 0),
        )
        policy.choose_key(dungeon)
        self.assertIsNone(policy._town_visit_epoch)
        self.assertIsNone(policy._home_knowledge_scan_epoch)
        self.assertFalse(policy._home_knowledge_scan_inflight)
        town2 = Snapshot(
            town.player, town.grids, [], turn=town.turn + 20, town_flag=True,
        )
        self.assertEqual(policy.choose_key(town2), "~9\x1b\x1b")
        self.assertEqual(policy.last_reason, "home:request-knowledge-scan")
        self.assertEqual(policy._town_visit_epoch, town2.turn)

    def test_pin_a2_late_response_is_accepted_and_settled(self):
        policy, town = self._scan_policy()
        self.assertEqual(policy.choose_key(town), "~9\x1b\x1b")
        policy.confirm_key_posted("~9\x1b\x1b")
        later = Snapshot(
            town.player, town.grids, [], turn=town.turn + 1, town_flag=True,
        )
        _dispatch_response_lines(
            [json.dumps(board_response(later))], policy, Mock(return_value=True)
        )
        self.assertNotEqual(policy.choose_key(later), "~9\x1b\x1b")
        self.assertTrue(policy._home_knowledge_scan_inflight)

        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "knowledge.jsonl"
            _dispatch_response_lines(
                [json.dumps(home_response())], policy, Mock(return_value=True),
                knowledge_ledger_path=ledger,
            )
            row = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertTrue(row["accepted"])
        self.assertTrue(row["inflight_at_arrival"])
        self.assertTrue(row["outstanding_at_arrival"])
        self.assertTrue(row["settled"])
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(policy._home_scan_source, "~9")
        self.assertIsNone(policy._home_knowledge_scan_epoch)

    def test_pin_a2_exit_and_reentry_reject_prior_visit_response(self):
        for reenter in (False, True):
            with self.subTest(reenter=reenter):
                policy, town = self._scan_policy()
                self.assertEqual(policy.choose_key(town), "~9\x1b\x1b")
                policy.confirm_key_posted("~9\x1b\x1b")
                dungeon = Snapshot(
                    town.player, town.grids, [], turn=town.turn + 10,
                    town_flag=False, floor_key=(1, 1, 0),
                )
                lines = [json.dumps(board_response(dungeon))]
                town2 = Snapshot(
                    town.player, town.grids, [], turn=town.turn + 20,
                    town_flag=True,
                )
                if reenter:
                    lines.append(json.dumps(board_response(town2)))
                lines.append(json.dumps(home_response()))
                with TemporaryDirectory() as directory:
                    ledger = Path(directory) / "knowledge.jsonl"
                    _dispatch_response_lines(
                        lines, policy, Mock(return_value=True),
                        knowledge_ledger_path=ledger,
                    )
                    row = json.loads(ledger.read_text(encoding="utf-8"))
                self.assertFalse(row["accepted"])
                self.assertFalse(row["inflight_at_arrival"])
                self.assertIsNone(row["request_epoch"])
                self.assertFalse(policy._home_knowledge_current)
                if reenter:
                    self.assertEqual(row["visit_epoch_at_arrival"], town2.turn)
                    self.assertEqual(policy.choose_key(town2), "~9\x1b\x1b")
                else:
                    self.assertIsNone(row["visit_epoch_at_arrival"])

    def test_pin_a2_unsolicited_home_response_is_rejected(self):
        policy = HengbotPolicy()
        town = town_with_home()
        policy.choose_key(town)
        # The producer has proposed a request, but no key was posted.
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "knowledge.jsonl"
            _dispatch_response_lines(
                [json.dumps(home_response())], policy, Mock(return_value=True),
                knowledge_ledger_path=ledger,
            )
            row = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertFalse(row["accepted"])
        self.assertFalse(row["settled"])
        self.assertFalse(policy._home_knowledge_current)
        self.assertEqual(row["visit_epoch_at_arrival"], town.turn)

    def test_pin_a2_superseded_response_settles_before_second_request(self):
        """All protocol state comes from choose/confirm/dispatch; no fixture wall."""
        policy, town = self._scan_policy()
        self.assertEqual(policy.choose_key(town), "~9\x1b\x1b")
        policy.confirm_key_posted("~9\x1b\x1b")
        token = policy._home_knowledge_scan_epoch

        outside1 = replace(town, turn=town.turn + 1)
        _dispatch_response_lines(
            [json.dumps(board_response(outside1))], policy, Mock(return_value=True)
        )
        self.assertNotEqual(policy.choose_key(outside1), "~9\x1b\x1b")

        one = store_item("a", 23, 17, name="Long Sword")
        page1 = replace(
            town, turn=town.turn + 2,
            store=StoreState(STORE_HOME, [one], stock_num=1, page_top=0,
                             page_size=12),
        )
        _dispatch_response_lines(
            [json.dumps(board_response(page1))], policy, Mock(return_value=True)
        )
        policy.choose_key(page1)
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(policy._home_scan_source, "observed-home-page")
        self.assertFalse(policy._home_knowledge_scan_inflight)
        self.assertEqual(policy._home_knowledge_scan_epoch, token)

        two = store_item("b", 17, 1, name="Arrows", count=20)
        page2 = replace(
            page1, turn=town.turn + 3,
            store=StoreState(STORE_HOME, [one, two], stock_num=2, page_top=0,
                             page_size=12),
        )
        _dispatch_response_lines(
            [json.dumps(board_response(page2))], policy, Mock(return_value=True)
        )
        policy.choose_key(page2)
        self.assertTrue(policy._home_knowledge_invalidated)
        self.assertFalse(policy._home_knowledge_current)
        self.assertEqual(policy._home_knowledge_items, ())
        self.assertEqual(policy._home_knowledge_scan_epoch, token)

        outside2 = replace(town, turn=town.turn + 4)
        outside3 = replace(town, turn=town.turn + 5)
        for outside in (outside2, outside3):
            _dispatch_response_lines(
                [json.dumps(board_response(outside))], policy,
                Mock(return_value=True),
            )
            self.assertNotEqual(policy.choose_key(outside), "~9\x1b\x1b")

        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "knowledge.jsonl"
            _dispatch_response_lines(
                [json.dumps(home_response())], policy, Mock(return_value=True),
                knowledge_ledger_path=ledger,
            )
            stale_row = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertFalse(stale_row["accepted"])
        self.assertFalse(stale_row["inflight_at_arrival"])
        self.assertTrue(stale_row["outstanding_at_arrival"])
        self.assertTrue(stale_row["settled"])
        self.assertFalse(policy._home_knowledge_current)
        self.assertTrue(policy._home_knowledge_invalidated)
        self.assertEqual(policy._home_knowledge_items, ())
        self.assertIsNone(policy._home_scan_item_count)
        self.assertIsNone(policy._home_scan_source)
        self.assertIsNone(policy._home_knowledge_scan_epoch)

        outside4 = replace(town, turn=town.turn + 6)
        self.assertEqual(policy.choose_key(outside4), "~9\x1b\x1b")
        policy.confirm_key_posted("~9\x1b\x1b")
        _dispatch_response_lines(
            [json.dumps(home_response())], policy, Mock(return_value=True)
        )
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(policy._home_scan_source, "~9")
        self.assertEqual(len(policy._home_knowledge_items), 2)

    def test_pin_legacy_restore_rejects_uncorrelated_home_response(self):
        """Fixture was emitted by HEAD's real checkpoint writer after choose/confirm."""
        fixture = (
            Path(__file__).parent / "fixtures"
            / "legacy-town-owner-request-head.b64"
        )
        policy = restore_checkpoint(HengbotPolicy, fixture.read_text(encoding="ascii"))
        self.assertIsNone(policy._home_knowledge_scan_epoch)
        self.assertFalse(policy._home_knowledge_scan_inflight)
        self.assertFalse(policy._home_knowledge_current)
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "knowledge.jsonl"
            _dispatch_response_lines(
                [json.dumps(home_response())], policy, Mock(return_value=True),
                knowledge_ledger_path=ledger,
            )
            row = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertFalse(row["accepted"])
        self.assertFalse(policy._home_knowledge_current)

    def test_pin_current_restore_preserves_correlated_request(self):
        policy = HengbotPolicy()
        town = town_with_home()
        self.assertEqual(policy.choose_key(town), "~9\x1b\x1b")
        policy.confirm_key_posted("~9\x1b\x1b")
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertEqual(restored._town_visit_epoch, town.turn)
        self.assertEqual(restored._home_knowledge_scan_epoch, town.turn)
        self.assertTrue(restored._home_knowledge_scan_inflight)
        _dispatch_response_lines(
            [json.dumps(home_response())], restored, Mock(return_value=True)
        )
        self.assertTrue(restored._home_knowledge_current)
        self.assertIsNone(restored._home_knowledge_scan_epoch)

    def test_pin_restore_fields_and_town_decoder_match_snapshot_contract(self):
        self.assertIn("_town_visit_epoch", STATE_FIELDS)
        self.assertIn("_home_knowledge_scan_epoch", STATE_FIELDS)
        cases = (
            ({"floor": {"dungeon_id": 0, "level": 0}}, True),
            ({"floor": {"dungeon_id": 1, "level": 1}}, False),
            ({"floor": {"dungeon_id": 0, "level": 0, "in_town": False}}, False),
            ({}, True),
        )
        for data, expected in cases:
            with self.subTest(data=data):
                self.assertEqual(_decoded_board_in_town(data), expected)

    def test_plain_town_requests_home_knowledge_before_any_home_visit(self):
        policy = HengbotPolicy()

        key = policy.choose_key(town_with_home())

        self.assertEqual(key, "~9\x1b\x1b")
        self.assertEqual(policy.last_reason, "home:request-knowledge-scan")
        self.assertEqual(policy._home_processing_seen_pages, set())
        self.assertIsNone(policy._home_knowledge_scan_leave_turn)

    def test_stalled_capture_requests_home_knowledge_and_completes(self):
        capture = (
            Path(__file__).parents[1]
            / "incident-captures"
            / "20260731-063654-loop-detected"
            / "decision-tail.jsonl"
        )
        if capture.exists():
            with capture.open("rb") as stream:
                stream.seek(max(0, capture.stat().st_size - 256 * 1024))
                tail = stream.read().decode("utf-8", errors="replace")
            self.assertIn('"reason": "home:seek-processing-page"', tail)

        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((("a", "captured", 17, 1),))
        snapshot = town_with_home()
        confirm_outside_after_home_leave(policy, snapshot)
        self.assertEqual(policy.choose_key(snapshot), "~9\x1b\x1b")
        self.assertEqual(policy.last_reason, "home:request-knowledge-scan")
        self.assertFalse(policy._home_knowledge_scan_requested)
        self.assertTrue(policy.confirm_key_posted("~9\x1b\x1b"))

        sent = []
        consumed = _dispatch_response_lines(
            [json.dumps(home_response())], policy, sent.append
        )

        self.assertEqual(consumed, 1)
        self.assertEqual(sent, [])
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertEqual(policy._home_scan_source, "~9")
        self.assertEqual(policy._home_scan_item_count, 2)
        self.assertNotEqual(policy.last_reason, "home:scan-catalog-page")
        self.assertNotEqual(policy.choose_key(snapshot), "~9")

    def test_response_types_never_become_board_snapshots(self):
        for response_type in ("knowledge", "look", "character"):
            with self.subTest(response_type=response_type):
                line = json.dumps({"type": response_type, "player": {}})
                self.assertIsNone(_newest_snapshot([line], {}))

    def test_unsolicited_character_and_look_responses_send_no_key(self):
        policy = HengbotPolicy()
        for response_type in ("character", "look"):
            with self.subTest(response_type=response_type):
                send = Mock(return_value=True)

                consumed = _dispatch_response_lines(
                    [json.dumps({"type": response_type})], policy, send
                )

                self.assertEqual(consumed, 1)
                send.assert_not_called()

    def test_periodic_character_dump_response_adds_no_keys(self):
        policy = HengbotPolicy()
        policy.request_character_dump()
        key = policy._periodic_character_dump_key(town_with_home(), "6")
        self.assertEqual(key, CHARACTER_DUMP_MACRO)
        self.assertEqual(policy.last_reason, "periodic:character-dump")
        sent = list(key)

        consumed = _dispatch_response_lines(
            [json.dumps({"type": "character"})], policy, sent.append
        )

        self.assertEqual(consumed, 1)
        self.assertEqual(sent, list(CHARACTER_DUMP_MACRO))

    def test_real_shaped_payload_preserves_slots_and_item_identity(self):
        policy = HengbotPolicy()
        policy._home_knowledge_scan_inflight = True
        _dispatch_response_lines(
            [json.dumps(home_response())], policy, Mock(return_value=True)
        )

        owned = policy._equipment_catalog.items
        self.assertEqual(len(owned), 1)
        self.assertEqual(owned[0].origin, "home")
        self.assertEqual(owned[0].item.slot, "3")
        self.assertEqual(owned[0].item.name, "Long Sword")
        self.assertEqual(owned[0].item.damage_dice_num, 2)

    def test_consumption_posts_no_additional_menu_close(self):
        policy = HengbotPolicy()
        policy._home_knowledge_scan_inflight = True
        send = Mock(return_value=True)

        _dispatch_response_lines(
            [json.dumps(home_response())], policy, send
        )

        send.assert_not_called()

    def test_empty_response_is_authoritative_despite_prior_page_size(self):
        policy = HengbotPolicy()
        policy._home_page_size = 52
        policy._home_errand.file(
            HomeErrandRequest(("missing", 23, 17), 1, "capture", "weapon"),
            knowledge_current=False,
        )
        policy.confirm_key_posted("~9\x1b\x1b")
        response = home_response()
        response["knowledge"]["items"] = []
        sent = []

        _dispatch_response_lines([json.dumps(response)], policy, sent.append)

        self.assertEqual(sent, [])
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(policy._home_knowledge_valid_before, 0)
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertFalse(policy._home_knowledge_invalidated)
        self.assertEqual(policy._home_errand.state, HomeErrandState.COMPOSABLE)

    def test_full_sequence_helper_delivers_every_response_and_snapshot_in_order(self):
        policy = HengbotPolicy()
        policy._home_knowledge_scan_inflight = True
        board = {
            "type": "player_turn",
            "player": {"y": 10, "x": 10, "hp": 20, "max_hp": 20},
        }
        store = {
            "type": "store",
            "player": {"y": 10, "x": 10, "hp": 20, "max_hp": 20},
            "store": {"store_type": STORE_HOME, "items": [], "stock_num": 0,
                      "page_top": 0, "page_size": 52},
        }
        lines = [json.dumps(row) for row in (
            board,
            store,
            home_response(),
            {"type": "look", "look": {"grids": []}},
            {"type": "character", "character": {}},
        )]
        sent = []

        _decoded, snapshots = _consume_response_sequence(
            lines, policy, sent.append
        )

        self.assertEqual([snapshot.store is not None for snapshot in snapshots], [False, True])
        self.assertEqual(policy._home_scan_item_count, 2)
        self.assertEqual(sent, [])

    def test_full_sequence_replay_uses_three_recorded_batches_for_six_lines(self):
        lines = [json.dumps(row) for row in (
            {"type": "player_turn", "turn": 1, "player": {"y": 10, "x": 10, "hp": 20, "max_hp": 20}},
            {"type": "player_turn", "turn": 2, "player": {"y": 10, "x": 10, "hp": 20, "max_hp": 20}},
            home_response(),
            {"type": "player_turn", "turn": 3, "player": {"y": 10, "x": 10, "hp": 20, "max_hp": 20}},
            {"type": "look", "turn": 3, "look": {"grids": []}},
            {"type": "player_turn", "turn": 4, "player": {"y": 10, "x": 10, "hp": 20, "max_hp": 20}},
        )]
        ledger = [{"line_count": 2}, {"line_count": 2}, {"line_count": 2}]

        def run(grouped):
            policy = HengbotPolicy()
            policy._home_knowledge_scan_inflight = True
            decision_keys = []

            def decide(_decoded, snapshots):
                decision_keys.append(
                    f"{len(snapshots)}:{policy._home_scan_item_count}"
                )

            with TemporaryDirectory() as directory:
                if grouped:
                    _consume_response_sequence(
                        lines, policy, lambda _key: None,
                        batch_ledger=ledger, batch_callback=decide,
                        knowledge_ledger_path=Path(directory) / "knowledge.jsonl",
                    )
                else:
                    for start in range(0, 6, 2):
                        decoded, snapshots = _consume_response_sequence(
                            lines[start:start + 2], policy, lambda _key: None,
                            knowledge_ledger_path=Path(directory) / "knowledge.jsonl",
                        )
                        decide(decoded, snapshots)
            return decision_keys

        self.assertEqual(run(True), run(False))
        self.assertEqual(run(True), ["2:None", "1:2", "1:2"])

    def test_board_after_post_keeps_request_pending(self):
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((("a", "captured", 17, 1),))
        snapshot = town_with_home()
        confirm_outside_after_home_leave(policy, snapshot)
        self.assertEqual(policy.choose_key(snapshot), "~9\x1b\x1b")
        policy.confirm_key_posted("~9\x1b\x1b")

        # An ordinary board does not prove that the uncorrelated response was lost.
        policy.choose_key(snapshot)

        self.assertTrue(policy._home_knowledge_scan_inflight)
        self.assertTrue(policy._home_knowledge_scan_requested)
        self.assertNotEqual(policy.last_reason, "home:request-knowledge-scan")
        self.assertEqual(policy._home_knowledge_scan_epoch, snapshot.turn)

    def test_real_capture_leave_barrier_clears_before_request_is_posted(self):
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((('a', 'captured', 20, 4),))
        snapshot = town_with_home()
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
        policy._store_leave_inflight = (
            policy._decision_sequence, snapshot.turn, STORE_HOME
        )
        policy._home_knowledge_scan_leave_turn = snapshot.turn

        # Reconstruct the 15:46:42 ordering: the first outside decision still
        # belongs to the unconfirmed Home leave and must not select any ~ key.
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: leave-barrier wrapper handling is isolated from the downstream town decision
        policy._decide = Mock(return_value="6")
        store_leave_was_inflight = policy._store_leave_inflight is not None
        self.assertEqual(policy.choose_key(snapshot), "6")
        suppress = (
            store_leave_was_inflight
            and policy._store_leave_inflight is not None
        )
        self.assertFalse(suppress)
        self.assertFalse(policy._home_knowledge_scan_requested)

        # A later turn confirms that the following decision is outside the
        # store loop, so the request is actually posted.
        snapshot = Snapshot(
            snapshot.player,
            snapshot.grids,
            snapshot.visible_monsters,
            turn=snapshot.turn + 1,
            town_flag=True,
        )
        self.assertEqual(policy.choose_key(snapshot), "~9\x1b\x1b")
        self.assertTrue(policy.confirm_key_posted("~9\x1b\x1b"))
        self.assertTrue(policy._home_knowledge_scan_inflight)

    def test_unposted_or_replaced_request_does_not_consume_latch(self):
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((('a', 'captured', 20, 4),))
        snapshot = town_with_home()
        confirm_outside_after_home_leave(policy, snapshot)

        self.assertEqual(policy.choose_key(snapshot), "~9\x1b\x1b")
        self.assertFalse(policy._home_knowledge_scan_requested)
        self.assertFalse(policy._home_knowledge_scan_inflight)
        self.assertEqual(policy.choose_key(snapshot), "~9\x1b\x1b")

    def test_no_rerequest_while_request_is_unsettled(self):
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((('a', 'captured', 20, 4),))
        snapshot = town_with_home()
        confirm_outside_after_home_leave(policy, snapshot)

        self.assertEqual(policy.choose_key(snapshot), "~9\x1b\x1b")
        policy.confirm_key_posted("~9\x1b\x1b")
        policy.choose_key(snapshot)
        self.assertNotEqual(policy.choose_key(snapshot), "~9\x1b\x1b")
        self.assertTrue(policy._home_knowledge_scan_requested)
        _dispatch_response_lines(
            [json.dumps(home_response())], policy, Mock(return_value=True)
        )
        self.assertTrue(policy._home_knowledge_current)
        self.assertNotEqual(policy.choose_key(snapshot), "~9\x1b\x1b")

    def test_real_capture_interleaved_surface_page_does_not_request_scan(self):
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((('a', 'captured', 20, 4),))
        position = Position(45, 123)
        snapshot = Snapshot(
            PlayerState(position, 596, 596, 0, 0, 27),
            {
                position: GridState(
                    position,
                    True,
                    True,
                    False,
                    False,
                    False,
                    False,
                    False,
                    store_number=STORE_HOME,
                )
            },
            [],
            turn=2407269,
            town_flag=True,
        )
        # TEST_FAKERY_LINT_ALLOW: private-state-injected: test begins from a protocol state whose subsequent handling is the subject
        policy._store_leave_inflight = (
            policy._decision_sequence, 2407269, STORE_HOME
        )
        policy._home_knowledge_scan_leave_turn = 2407269
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: interleaved-capture bookkeeping is isolated from the downstream town decision
        policy._decide = Mock(return_value="5")

        # Real 17:43:56-17:44:08 shape: a Home page was followed by a
        # store=None page on (45,123), with the post-leave turn unchanged.
        self.assertEqual(snapshot.player.position, Position(45, 123))
        self.assertEqual(policy.choose_key(snapshot), "5")
        self.assertNotEqual(policy.choose_key(snapshot), "~9")
        self.assertFalse(policy._home_knowledge_scan_requested)

    def test_visit_without_confirmed_outside_context_never_waits_for_scan(self):
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((('a', 'captured', 20, 4),))
        snapshot = town_with_home()
        policy._home_knowledge_scan_leave_turn = snapshot.turn
        # TEST_FAKERY_LINT_ALLOW: public-path-replaced: scan-request retry accounting is isolated from the downstream town decision
        policy._decide = Mock(return_value="6")

        keys = [policy.choose_key(snapshot) for _ in range(4)]

        self.assertEqual(keys, ["~9\x1b\x1b"] * 4)
        self.assertNotIn("5", keys)

    def test_scan_source_and_count_are_recorded(self):
        record = _decision_record(
            town_with_home(),
            "\x1b",
            "home:knowledge-scan-complete",
            home_scan={"source": "~9", "item_count": 2},
        )
        self.assertEqual(record["home_scan"], {"source": "~9", "item_count": 2})

    def test_store_page_metadata_is_parsed_for_address_verification(self):
        snapshot = parse_snapshot({
            "player": {"y": 10, "x": 10, "hp": 20, "max_hp": 20},
            "store": {
                "store_type": STORE_HOME,
                "items": [],
                "stock_num": 101,
                "page_top": 52,
                "page_size": 52,
            },
        })

        self.assertEqual(
            (snapshot.store.stock_num, snapshot.store.page_top, snapshot.store.page_size),
            (101, 52, 52),
        )

    def test_knowledge_response_records_all_101_items_and_source(self):
        response = home_response()
        template = response["knowledge"]["items"][0]
        response["knowledge"]["items"] = [
            {**template, "slot": slot, "name": f"Home equipment {slot}", "sval": slot}
            for slot in range(101)
        ]
        policy = HengbotPolicy()
        policy._home_knowledge_scan_inflight = True

        _dispatch_response_lines([json.dumps(response)], policy, Mock(return_value=True))

        self.assertEqual(policy._home_scan_source, "~9")
        self.assertEqual(policy._home_scan_item_count, 101)
        self.assertEqual(len(policy._equipment_catalog.items), 101)

    def test_complete_response_exposes_all_fourteen_home_diggers(self):
        policy = HengbotPolicy()
        policy._home_knowledge_scan_inflight = True

        consumed = _dispatch_response_lines(
            [json.dumps(home_digger_response())], policy, Mock(return_value=True)
        )

        home_diggers = [
            owned.item
            for owned in policy._equipment_catalog.items
            if owned.origin == "home" and owned.item.tval == 20
        ]
        self.assertEqual(consumed, 1)
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertEqual(policy._home_scan_source, "~9")
        self.assertEqual(sum(item.count for item in home_diggers), 14)
        self.assertTrue(policy._has_withdrawable_digging_tool(town_with_home()))
        self.assertEqual(max(item.pval for item in home_diggers), 4)


class CompleteHomeCatalogTest(unittest.TestCase):
    def test_complete_scan_replaces_page_staging(self):
        catalog = OwnedEquipmentCatalog()
        policy = HengbotPolicy()
        policy._home_knowledge_scan_inflight = True
        _dispatch_response_lines(
            [json.dumps(home_response())], policy, Mock(return_value=True)
        )
        catalog.complete_home_scan(
            owned.item for owned in policy._equipment_catalog.items
        )

        self.assertTrue(catalog.home_scan_complete)
        self.assertEqual([owned.item.name for owned in catalog.items], ["Long Sword"])


if __name__ == "__main__":
    unittest.main()
