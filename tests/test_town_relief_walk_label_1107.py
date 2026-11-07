"""The full-Home relief's walk is named for itself, not for the last decision.

n1-b life-333 (2026-11-07 03:27:37-03:27:49, town:blocked:owner-retired-burst):
during the Home junk sweep the bot picked up gold in town under the loot walk
("seek-loot", $16 の価値がある銅塊を見つけた).  On the next boards the relief
walked back to Home (_home_full_relief_key -> _shopping_approach_key, offered
work route:store:45,123) while the Home scan was requested, so
_home_relief_names_approach kept "the decision's own reason": the loot label
still standing from the previous decision.  Owned by misc, whose progress
vector measures only the loot target (gone), the walk scored no progress and
misc retired three times.

The board is constructed from policy_fixtures (DECLARED CONSTRUCTED): a town
walk of three cells toward Home, the relief open and the Home scan requested.
"""
import tests  # noqa: F401 -- live runtime-file isolation, also for bare module runs

import unittest
from dataclasses import replace

from policy_fixtures import grid, player
from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    STORE_HOME,
    Position,
    Snapshot,
)
from hengbot.policy import HengbotPolicy


HOME = Position(10, 7)


def board(position):
    return Snapshot(
        player(position.y, position.x, class_id=PLAYER_CLASS_WARRIOR, gold=500),
        {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 8): grid(10, 8),
            HOME: replace(grid(10, 7), store_number=STORE_HOME),
        },
        [],
        floor_key=(0, 0, 0),
        town_flag=True,
        inventory=[],
    )


class ReliefWalkLabelTest(unittest.TestCase):
    def relief_policy(self):
        policy = HengbotPolicy()
        policy._floor_key = (0, 0, 0)
        # DECLARED CONSTRUCTED: the junk sweep's relief is open and the Home
        # list was asked for (the live home:request-knowledge-scan at 03:27:37).
        policy._home_full_relief = {"town": 0, "sweep": True, "remaining": 1}
        policy.consume_home_knowledge(())
        policy._home_knowledge_scan_requested = True
        policy._shopping_approach_store_type = STORE_HOME
        policy._shopping_approach_goal = HOME
        return policy

    def relief_walk(self, policy, previous_reason):
        """The relief's last step on the decision after ``previous_reason``."""
        # The town arrival board (it resets the scan flag), then the scan that
        # the live 03:27:37 decision posted: its flag stays up after the reply.
        policy.choose_key(board(Position(10, 10)))
        policy.confirm_key_posted("~9\x1b\x1b")
        policy.consume_home_knowledge(())
        policy._shopping_approach_store_type = STORE_HOME
        policy._shopping_approach_goal = HOME
        # The previous decision's label, as choose_key's entry records it.
        policy.last_reason = previous_reason
        policy._decision_entry_reason = previous_reason
        # _home_full_relief_key returns _shopping_approach_key(..., "shop:travel"),
        # which names the walk shop:approach exactly when this answers True.
        if policy._home_relief_names_approach("store-router", "shop:travel"):
            policy.last_reason = "shop:approach"
        return True, policy.last_reason

    def test_relief_walk_after_a_loot_pickup_is_the_routers(self):
        policy = self.relief_policy()
        # The previous decision picked up the gold under the loot walk.
        key, reason = self.relief_walk(policy, "seek-loot")
        self.assertTrue(key)
        # Live: "seek-loot" (rung _normal_loot_key#2), owner misc.
        self.assertEqual(reason, "shop:approach")
        arbiter = policy._town_turn_arbiter
        self.assertEqual(arbiter.owner_for_reason(reason), "store-router")

    def test_a_standing_home_scan_label_still_names_the_walk(self):
        # Unchanged: a Home scan's label keeps the walk while its flag is up
        # (tests/test_town_stops_1105_recorded.py, n1-a life-487 row 15).
        policy = self.relief_policy()
        _key, reason = self.relief_walk(policy, "home:request-knowledge-scan")
        self.assertEqual(reason, "home:request-knowledge-scan")

    def test_loot_label_on_a_staged_store_walk_is_measured_as_that_walk(self):
        policy = self.relief_policy()
        vectors = []
        for position in (Position(10, 10), Position(10, 9)):
            policy._decision_sequence += 1
            policy._loot_target = None
            # The store walk staged on this decision under the standing label.
            policy._staged_shop_approach = (
                object(), policy._decision_sequence, STORE_HOME, position, "4", "seek-loot")
            vectors.append(policy._town_arbiter_progress_vector(board(position), "seek-loot"))
        # Live 03:27:46-49: misc's vector held only durable facts once the gold
        # was picked up, so every step scored no progress.
        self.assertNotEqual(vectors[0], vectors[1])
        self.assertEqual(vectors[1][-1][:2], ("locomotion", "misc"))


if __name__ == "__main__":
    unittest.main()
