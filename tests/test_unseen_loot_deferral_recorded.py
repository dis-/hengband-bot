"""Unseen-retreat loot deferral pinned to the 2026-10-06 Orc cave capture."""

import tests  # noqa: F401 -- isolate live runtime files

from types import SimpleNamespace
import unittest

from hengbot.policy_identification import UNSEEN_LOOT_QUIET_TURNS

from hengbot.model import Position
from hengbot.policy import HengbotPolicy


FLOOR = (3, 23, 0)
# Captured decision 35 from bot-decisions.jsonl, 2026-10-06 09:31:
# seek-loot at (11, 61), target (9, 56), followed by unseen:reverse-choke.
RECORDED_SEEK_ROW = {
    "turn": 12913141,
    "reason": "seek-loot",
    "key": "4",
    "position": Position(11, 61),
    "target": Position(9, 56),
    "retreat_direction": (1, 1),
}


class UnseenLootDeferralRecordedTest(unittest.TestCase):
    def _policy(self):
        policy = HengbotPolicy()
        policy._release_claim_goal = lambda *args, **kwargs: None
        policy._guarded_paralyzers = lambda snapshot, hostiles: []
        return policy

    def test_recorded_seek_does_not_reverse_retreat_and_retreat_step_proceeds(self):
        row = RECORDED_SEEK_ROW
        policy = self._policy()
        policy._known_loot = {row["target"]}
        policy._loot_target = row["target"]
        policy._unseen_retreat_floor = FLOOR
        policy._unseen_retreat_direction = row["retreat_direction"]
        policy._walkable_neighbors = lambda snapshot, pos: (
            [Position(10, 60)] if pos == row["position"] else []
        )
        board = SimpleNamespace(
            player=SimpleNamespace(position=row["position"]),
            floor_key=FLOOR,
            turn=row["turn"],
        )

        self.assertIsNone(policy._loot_step(board))
        self.assertIn(row["target"], policy._unseen_deferred_loot)
        policy._open_neighbor_count = lambda snapshot, pos: 8
        policy._walkable_neighbors = lambda snapshot, pos: [Position(12, 62)]
        self.assertEqual(
            policy._unseen_reverse_choke_step(board), Position(12, 62)
        )

    def test_deferred_item_is_picked_up_after_the_quiet_window(self):
        row = RECORDED_SEEK_ROW
        policy = self._policy()
        target = row["target"]
        policy._known_loot = {target}
        policy._deferred_loot = {target}
        policy._unseen_deferred_loot = {target}
        policy._unseen_last_hit_floor = FLOOR
        policy._unseen_last_hit_turn = row["turn"]
        policy._unseen_retreat_floor = None
        policy._unseen_loot_direction = row["retreat_direction"]
        policy._loot_block_reason = lambda snapshot, hostiles: None
        policy._current_floor_item_key = lambda *args, **kwargs: (
            setattr(policy, "last_reason", "pickup") or "g"
        )
        policy._walkable_neighbors = lambda snapshot, pos: [Position(10, 60)]
        while_quiet = SimpleNamespace(
            player=SimpleNamespace(position=row["position"]),
            floor_key=FLOOR,
            turn=row["turn"] + 5,
        )
        self.assertIsNone(policy._loot_step(while_quiet))
        self.assertIn(target, policy._unseen_deferred_loot)
        board = SimpleNamespace(
            player=SimpleNamespace(position=target),
            floor_key=FLOOR,
            turn=row["turn"] + UNSEEN_LOOT_QUIET_TURNS,
            in_town=False,
        )

        self.assertEqual(policy._normal_loot_key(board, []), "g")
        self.assertNotIn(target, policy._unseen_deferred_loot)
        self.assertEqual(policy.last_reason, "pickup")


if __name__ == "__main__":
    unittest.main()
