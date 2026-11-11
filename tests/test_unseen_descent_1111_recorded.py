"""n1-a life-508 08:45 (Mountain 43F): the descent walked back into an unseen caster's area.

Recorded: tests/fixtures/n1a-508-1111/unseen-descent-0845.json.gz (tests/extract_n1a_508_1111_fixtures.py).

A hidden caster's Magic Missiles landed at (11,140); after each ``unseen:reverse-choke`` the descent
(``seek-downstairs``) walked back onto that cell toward the down stairs at (6,171) / (7,158), both past
it, until loop-detected three times (08:45:37, 08:45:49, 08:45:56) and the life was retired.  Explore
and loot keep out of that area (user 2026-10-06 「後ずさりは今のまま・拾いを諦める」,
_in_unseen_attack_area); the descent did not.  Every decision is the public ``choose_key`` of one
fresh policy fed the recorded boards in order.  DECLARED: the later board of the last pin is the
recorded one, a quiet window on (no message, turn advanced).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot.model import Position, parse_snapshot
from hengbot.policy_identification import UNSEEN_LOOT_QUIET_TURNS
from tests.test_empty_wand_1110_recorded import MOVES, case, decide, recorded, replay


class UnseenDescentRecordedTest(unittest.TestCase):
    """3. life-508 08:45, Mountain 43F: the descent walked back into the unseen caster's area."""

    HIT = Position(11, 140)
    BACK = 5075712  # (10,137): recorded seek-downstairs '6', the first walk back after a hit

    @classmethod
    def setUpClass(cls):
        cls.case = case("unseen-descent-0845")

    def test_recorded_scene(self):
        rows = recorded(self.case)
        self.assertEqual(rows[self.BACK], ("6", "seek-downstairs"))
        self.assertEqual([tuple(cell) for cell in self.case["terrain"]["downstairs"]],
                         [(6, 171), (7, 158)])
        hits = [row["turn"] for row in self.case["rows"]
                if (row["player"]["y"], row["player"]["x"]) == (self.HIT.y, self.HIT.x)
                and any("マジック・ミサイル" in message for message in row["messages"])]
        self.assertGreaterEqual(len(hits), 5)
        backs = [turn for turn, (key, reason) in rows.items() if reason == "seek-downstairs"
                 and turn >= self.BACK]
        self.assertGreaterEqual(len(backs), 10)

    def test_the_descent_does_not_walk_back_into_the_area(self):
        before, _, _, _ = replay(self.case, self.BACK - 12)  # the board before (10,137)
        expired = set(before._nav_ledger.expired_targets("descend"))
        policy, races, raw, decisions = replay(self.case, self.BACK)
        key, reason = decisions[self.BACK]
        board = parse_snapshot(copy.deepcopy(raw), races)
        self.assertNotIn(reason, ("seek-downstairs", "approach-descent"))
        self.assertEqual(policy._descent_refusal_reason, "unseen-attack-area")
        for stair in (Position(6, 171), Position(7, 158)):
            self.assertTrue(policy._in_unseen_attack_area(board, stair))
        # Nothing expires for the area: (7,158) stays a target ((6,171) the fresh replay's
        # earlier stall had expired before the hit).
        self.assertEqual(set(policy._nav_ledger.expired_targets("descend")), expired)
        self.assertNotIn(Position(7, 158), expired)
        self.assertIn(key, MOVES)
        dy, dx = MOVES[key]
        here = board.player.position
        self.assertFalse(policy._in_unseen_attack_area(board, Position(here.y + dy, here.x + dx)))

    def test_once_the_area_lifts_the_stair_is_a_target_again(self):
        policy, races, raw, _ = replay(self.case, self.BACK)
        later = dict(copy.deepcopy(raw), turn=raw["turn"] + UNSEEN_LOOT_QUIET_TURNS + 10, messages=[])
        decide(policy, races, later)
        self.assertIn(policy.last_reason, ("seek-downstairs", "approach-descent"))
        self.assertIsNone(policy._descent_refusal_reason)


if __name__ == "__main__":
    unittest.main()
