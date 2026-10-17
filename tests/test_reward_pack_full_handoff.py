from __future__ import annotations

import tests  # noqa: F401
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "reward-pack-full-20261017.jsonl.gz"


def captured_rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def captured_reward_board():
    board = next(row for row in captured_rows() if row.get("type") == "player_turn")
    return parse_snapshot(board)


class RewardPackFullHandoffTest(unittest.TestCase):
    def test_captured_board_releases_reward_to_existing_overflow_owner(self):
        rows = captured_rows()
        evidence = next(row for row in rows if "decision_sequence" in row)
        self.assertEqual(evidence["policy_commit"], "9ec39c05")
        self.assertEqual(evidence["decision_sequence"], 8436)
        self.assertEqual(evidence["reason"], "fixedquest:reward-pack-full")
        self.assertEqual(evidence["key"], "5")
        self.assertEqual(evidence["claim"], {
            "owner": "quest-request", "rung": "_fixed_quest_key#2"
        })

        snapshot = captured_reward_board()
        self.assertEqual(snapshot.turn, 961478)
        self.assertEqual((snapshot.player.position.y, snapshot.player.position.x), (31, 99))
        self.assertEqual(snapshot.player.gold, 8514)
        self.assertEqual(snapshot.player.level, 23)
        self.assertEqual(snapshot.quests[22].status, 4)
        self.assertEqual(len(snapshot.inventory), 23)

        policy = HengbotPolicy()
        policy._fixed_quest_reward_pending = 22

        key = policy._fixed_quest_key(snapshot, [])
        self.assertIsNone(key)
        self.assertEqual(policy.last_reason, "fixedquest:reward-pack-full")

        key = policy._town_overflow_destroy_key(snapshot)
        self.assertEqual(key, "01ka")
        self.assertEqual(policy.last_reason, "town:destroy-overflow")
        target = next(item for item in snapshot.inventory if item.slot == "a")
        self.assertEqual((target.tval, target.sval), (96, 0))
        self.assertFalse(policy._item_is_procurement_protected(snapshot, target))
        self.assertTrue(policy._entire_stack_is_surplus(snapshot, target))

    def test_reward_is_picked_up_when_a_slot_is_free(self):
        snapshot = captured_reward_board()
        position = snapshot.player.position
        current = snapshot.grid_at(position)
        self.assertIsNotNone(current)
        # DECLARED CONSTRUCTED: expose the allowlisted reward on the captured
        # reward tile to exercise the ordinary one-slot pickup control.
        grids = dict(snapshot.grids)
        grids[position] = replace(current, object_count=1)
        board = replace(snapshot, grids=grids, inventory=snapshot.inventory[:-1])
        policy = HengbotPolicy()
        policy._fixed_quest_reward_pending = 22

        key = policy._fixed_quest_reward_key(board, 22)
        self.assertEqual(key, "g")
        self.assertEqual(policy.last_reason, "fixedquest:reward-pickup")

    def test_undestroyable_items_are_not_sold_or_destroyed(self):
        snapshot = captured_reward_board()
        policy = HengbotPolicy()
        # DECLARED CONSTRUCTED: mark each captured signature undestroyable,
        # modelling a pack whose remaining items are all protected from disposal.
        policy._undestroyable_sigs = {
            policy._item_signature(item) for item in snapshot.inventory
        }

        self.assertIsNone(policy._find_low_level_sale(snapshot))
        self.assertIsNone(policy._find_book_sale(snapshot))
        self.assertIsNone(policy._find_device_sale(snapshot))
        key = policy._town_overflow_destroy_key(snapshot)
        self.assertEqual(key, "5")
        self.assertEqual(policy.last_reason, "town:blocked:overflow-no-legal-disposal")


if __name__ == "__main__":
    unittest.main()
