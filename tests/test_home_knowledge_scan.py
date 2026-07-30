import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from hengbot.cli import (
    _decision_record,
    _dispatch_response_lines,
    _newest_snapshot,
)
from hengbot.equipment_optimizer import OwnedEquipmentCatalog
from hengbot.model import GridState, PlayerState, Position, Snapshot
from hengbot.policy import HengbotPolicy, STORE_HOME


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


class HomeKnowledgeScanTest(unittest.TestCase):
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
        self.assertEqual(policy.choose_key(snapshot), "~9")
        self.assertEqual(policy.last_reason, "home:request-knowledge-scan")

        sent = []
        consumed = _dispatch_response_lines(
            [json.dumps(home_response())], policy, sent.append
        )

        self.assertEqual(consumed, 1)
        self.assertEqual(sent, ["\x1b"])
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertEqual(policy._home_scan_source, "~9")
        self.assertEqual(policy._home_scan_item_count, 2)
        self.assertNotEqual(policy.last_reason, "home:seek-processing-page")

    def test_response_types_never_become_board_snapshots(self):
        for response_type in ("knowledge", "look", "character"):
            with self.subTest(response_type=response_type):
                line = json.dumps({"type": response_type, "player": {}})
                self.assertIsNone(_newest_snapshot([line], {}))

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

    def test_consumption_exits_menu_with_no_additional_key(self):
        policy = HengbotPolicy()
        policy._home_knowledge_scan_inflight = True
        send = Mock(return_value=True)

        _dispatch_response_lines(
            [json.dumps(home_response())], policy, send
        )

        send.assert_called_once_with("\x1b")

    def test_missing_response_falls_back_to_existing_page_scan(self):
        policy = HengbotPolicy()
        policy._next_required_store_type = lambda _snapshot: STORE_HOME
        policy._home_processing_seen_pages.add((("a", "captured", 17, 1),))
        snapshot = town_with_home()
        self.assertEqual(policy.choose_key(snapshot), "~9")

        # The next ordinary board is produced after bounded CLI prompt recovery.
        policy.choose_key(snapshot)

        self.assertFalse(policy._home_knowledge_scan_inflight)
        self.assertTrue(policy._home_knowledge_scan_requested)
        self.assertNotEqual(policy.last_reason, "home:request-knowledge-scan")

    def test_scan_source_and_count_are_recorded(self):
        record = _decision_record(
            town_with_home(),
            "\x1b",
            "home:knowledge-scan-complete",
            home_scan={"source": "~9", "item_count": 2},
        )
        self.assertEqual(record["home_scan"], {"source": "~9", "item_count": 2})


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
