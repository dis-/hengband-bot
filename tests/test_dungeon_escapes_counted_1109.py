"""Pin: the dungeon escapes the registry report found uncounted now count (owner 2026-11-09).

Owner answer to the registry report's questions (2026-11-09, verbatim choice): 「ダンジョンの分だけ
数える」 -- 「ダンジョンの中の逃げだけを数え、荒野での逃げは数えない。」  So the per-dive escape
count (policy_observation, RELOCATING_ESCAPE_REASONS; the second of a dive returns to town) takes:

- Q1 combat:avoid-unprofitable-unique-stairs / -recall: policy._unprofitable_unique_disengage_key
  renames the fruitless fight's counted combat:disengage-stairs / -recall to these;
- Q2 no-wait:escape-scroll: the no-wait rung's Teleportation / Phase Door under a material threat;

and not the wilderness's escapes (Q4).  Q6: summoner:stairs, sent by two producers, counts once per
stair taken.

DECLARED CONSTRUCTED on the recorded adjacent-paralyzer board
``tests/fixtures/incident-paralyzer-adjacent-escape.jsonl`` turn 3305879 (Angband 19F, the board of
test_status_threat_escape_counts_emergency): the board is decided as recorded (status-threat:scroll),
then ``last_reason`` is replaced by the reason under test -- the decision the counter reads on the
next board -- and the next board is constructed: the teleport landed out of sight (a new position),
or the stairs led one floor up (a new floor).  The reason producers themselves are not replayed here:
no recording holds these reasons (the registry report's 674 recorded reasons have none of them).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import unittest
from dataclasses import replace

from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import RELOCATING_ESCAPE_REASONS

# Fixture helpers, not the TestCase (test_policy_structure forbids re-collecting one).
from test_policy_combat import PARALYZER_ESCAPE_KNOWLEDGE, paralyzer_escape_snapshots

ESCAPE_TURN = 3305879
NEWLY_COUNTED = {
    # reason: how its effect shows on the next board
    "combat:avoid-unprofitable-unique-stairs": "floor",
    "combat:avoid-unprofitable-unique-recall": "position",
    "no-wait:escape-scroll": "position",
}


class DungeonEscapesCountedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.knowledge = PARALYZER_ESCAPE_KNOWLEDGE
        cls.board = paralyzer_escape_snapshots(cls.knowledge)[ESCAPE_TURN]

    # -- constructed boards ------------------------------------------------
    def landing(self, board, *, turn_offset: int):
        """CONSTRUCTED: a new position far away, out of sight of every monster."""
        here = board.player.position
        far = max(
            (position for position, grid in board.grids.items()
             if grid.passable and not grid.has_monster and position.distance_to(here) >= 20),
            key=lambda position: (position.distance_to(here), position.y, position.x),
        )
        return replace(board, player=replace(board.player, position=far), visible_monsters=[],
                       detected_monsters=[], turn=board.turn + turn_offset)

    def upper(self, board, *, turn_offset: int):
        """CONSTRUCTED: one floor up, the same grids."""
        return replace(board, floor_key=(board.floor_key[0], board.floor_key[1] - 1, 0),
                       visible_monsters=[], detected_monsters=[], turn=board.turn + turn_offset)

    def moved(self, how, board, *, turn_offset: int):
        return (self.upper if how == "floor" else self.landing)(board, turn_offset=turn_offset)

    def decided_as(self, policy, board, reason):
        """The recorded decision, its reason replaced (DECLARED CONSTRUCTED)."""
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "status-threat:scroll")
        policy.last_reason = reason

    # -- pins --------------------------------------------------------------
    def test_each_newly_counted_reason_counts_once_relocated(self):
        for reason, how in NEWLY_COUNTED.items():
            with self.subTest(reason=reason):
                self.assertIn(reason, RELOCATING_ESCAPE_REASONS)
                policy = HengbotPolicy(monrace_knowledge=self.knowledge)
                self.decided_as(policy, self.board, reason)
                policy.choose_key(self.moved(how, self.board, turn_offset=10))
                # Owner 2026-11-11 「逃げは階が変わればリセット。」: a stair escape is counted
                # for the floor it left (the dive's total), and the new floor starts at 0.
                self.assertEqual(policy._dive_escapes_total, 1)
                self.assertEqual(policy._dive_emergencies, 0 if how == "floor" else 1)
                self.assertFalse(policy._returning_to_town)

    def test_an_unrelocated_board_does_not_count_it(self):
        for reason in NEWLY_COUNTED:
            with self.subTest(reason=reason):
                policy = HengbotPolicy(monrace_knowledge=self.knowledge)
                self.decided_as(policy, self.board, reason)
                policy.choose_key(replace(self.board, turn=self.board.turn + 1))
                self.assertEqual(policy._dive_emergencies, 0)

    def test_the_second_escape_of_the_dive_returns_to_town(self):
        """The first escape status-threat:scroll (counted since 10-02), the second each new one."""
        for reason, how in NEWLY_COUNTED.items():
            with self.subTest(reason=reason):
                policy = HengbotPolicy(monrace_knowledge=self.knowledge)
                policy.choose_key(self.board)
                self.assertEqual(policy.last_reason, "status-threat:scroll")
                first = self.landing(self.board, turn_offset=10)
                policy.choose_key(first)
                self.assertEqual(policy._dive_emergencies, 1)
                # CONSTRUCTED: the paralyzer finds us again on the same floor.
                self.decided_as(policy, replace(self.board, turn=self.board.turn + 20), reason)
                policy.choose_key(self.moved(how, self.board, turn_offset=30))
                # The second escape from the floor returns; a stair escape is the second of
                # the floor it left (owner 2026-11-11: the new floor's count starts at 0).
                self.assertEqual(policy._dive_escapes_total, 2)
                self.assertEqual(policy._dive_emergencies, 0 if how == "floor" else 2)
                self.assertTrue(policy._returning_to_town)
                self.assertEqual(policy._last_return_trigger, "emergency-repeat")

    def test_the_wilderness_escapes_do_not_count(self):
        """Q4: 「荒野での逃げは数えない」 -- even with the effect seen on a dungeon board."""
        for reason in ("wilderness:escape-scroll", "wilderness:recall", "wilderness:flee"):
            with self.subTest(reason=reason):
                policy = HengbotPolicy(monrace_knowledge=self.knowledge)
                self.decided_as(policy, self.board, reason)
                policy.choose_key(self.landing(self.board, turn_offset=10))
                self.assertEqual(policy._dive_emergencies, 0)

    def test_summoner_stairs_from_two_producers_count_once_per_stair(self):
        """Q6: the exposed summoner's '<' (policy) and the immobile summoner exit's '<'
        (policy_combat) are both summoner:stairs.  CONSTRUCTED: the first '<' did not change the
        floor (a board in between), the other producer sends '<' again, then the floor changes;
        on the new floor a third summoner:stairs whose board shows no change counts nothing.
        Owner 2026-11-11 「逃げは階が変わればリセット。」: the stair is counted for the floor it
        left (the dive's total) and the new floor's count starts at 0."""
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        self.decided_as(policy, self.board, "summoner:stairs")
        same = replace(self.board, turn=self.board.turn + 1)
        policy.choose_key(same)
        self.assertEqual(policy._dive_emergencies, 0)
        policy.last_reason = "summoner:stairs"     # the other producer, same stair
        upper = self.upper(self.board, turn_offset=10)
        policy.choose_key(upper)
        self.assertEqual((policy._dive_escapes_total, policy._dive_emergencies), (1, 0))
        policy.last_reason = "summoner:stairs"
        policy.choose_key(replace(upper, turn=upper.turn + 1))
        self.assertEqual((policy._dive_escapes_total, policy._dive_emergencies), (1, 0))
        self.assertFalse(policy._returning_to_town)


if __name__ == "__main__":
    unittest.main()
