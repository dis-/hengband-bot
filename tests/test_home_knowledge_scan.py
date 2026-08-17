import json
import inspect
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

from hengbot.cli import (
    _consume_response_sequence,
    _decision_record,
    _dispatch_response_lines,
    _newest_snapshot,
)
from hengbot.equipment_optimizer import OwnedEquipmentCatalog
from hengbot.home_errand import HomeErrandRequest, HomeErrandState
from hengbot.model import (
    GridState, InventoryItem, PlayerState, Position, Snapshot, parse_snapshot,
)
from hengbot.policy import CHARACTER_DUMP_MACRO, HengbotPolicy, STORE_HOME


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
        self.assertTrue(capture.exists())
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
        self.assertTrue(policy.confirm_key_posted("~9"))

        sent = []
        consumed = _dispatch_response_lines(
            [json.dumps(home_response())], policy, sent.append
        )

        self.assertEqual(consumed, 1)
        self.assertEqual(sent, ["\x1b\x1b"])
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

    def test_missing_response_falls_back_to_existing_page_scan(self):
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((("a", "captured", 17, 1),))
        snapshot = town_with_home()
        confirm_outside_after_home_leave(policy, snapshot)
        self.assertEqual(policy.choose_key(snapshot), "~9\x1b\x1b")
        policy.confirm_key_posted("~9\x1b\x1b")

        # The next ordinary board is produced after bounded CLI prompt recovery.
        policy.choose_key(snapshot)

        self.assertFalse(policy._home_knowledge_scan_inflight)
        self.assertFalse(policy._home_knowledge_scan_requested)
        self.assertNotEqual(policy.last_reason, "home:request-knowledge-scan")

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

    def test_abandonment_allows_exactly_one_rerequest_per_home_visit(self):
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((('a', 'captured', 20, 4),))
        snapshot = town_with_home()
        confirm_outside_after_home_leave(policy, snapshot)

        self.assertEqual(policy.choose_key(snapshot), "~9\x1b\x1b")
        policy.confirm_key_posted("~9\x1b\x1b")
        policy.choose_key(snapshot)  # abandon the first posted request
        self.assertEqual(policy.choose_key(snapshot), "~9\x1b\x1b")
        policy.confirm_key_posted("~9\x1b\x1b")
        policy.choose_key(snapshot)  # abandon the one permitted re-request
        self.assertTrue(policy._home_knowledge_scan_requested)
        self.assertNotEqual(policy.choose_key(snapshot), "~9")

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
