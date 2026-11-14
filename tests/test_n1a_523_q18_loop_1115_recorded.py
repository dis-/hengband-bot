"""n1-a life 523 (2026-11-15 05:37, warrior Lv35, Q18 『湖の洞窟』, floor (0,35,18)): three loop stops.

Each run (the bot restarted with a fresh policy at (2,18)) held the choke (1,19) its 200 actions
(``choke_enemy_wait_turns``) for the giant squid 482 on (5,26), known by ESP only and beside the
dig (5,25) of the walk ahead.  With the wait spent the squid was still beside the walk ahead of
(1,19), so it sent the walk to the choke behind: (1,19) '1' exit-to-choke onto (2,18); there the
walk ahead ends at the choke (1,19) and the squid was no reason, so '9' exit-walk back.  The
ping-pong guard saw it (``pingpong:quest-strategy:exit-walk/quest-strategy:exit-to-choke``) and
escalated it to the livelock stop; the loop detector replaced the character.

Owner (QUEST_18 formation): 「次の隘路までの道の隣に来る敵がいると分かっている間は進まない」,
「200手の打ち切りで終えた隘路は戻さない」: the bound outwaited the squid, the walk goes on
(quest_find_exit._outwaited).  Game: the squid was never processed, its distance 9 from (1,19)
(monster-update.cpp) being over its vision 8 with its cell never in view (monster-processor.cpp
decide_process_continue), so it never moved.

The boards are the recorded ones (tests/fixtures/q18-life523-20261115.json.gz,
tests/extract_q18_life523_fixture.py: the run's last 135 boards, 131 on (1,19), 4 on (2,18)),
answered through the public ``choose_key`` in a closed loop: each step key moves the player as
the game does, and the board of the player's cell is the next recorded board there.  DECLARED
CONSTRUCTED: a cell the recording has no board for is the last (1,19) board with the player
moved (the squid and the puddles where ESP showed them); the turn goes on 10 game turns a board.
The walk on is posted through the production executor (``_ExecutorInputPort``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from collections import defaultdict, deque
from pathlib import Path

from hengbot import cli, pingpong_guard, quest_find_exit
from hengbot.model import parse_snapshot
from tests.support import recorded as executor_harness
from tests.test_q18_water_cave import (
    DIG_REASON, DIRECTION, HOLD_REASON, STRATEGIES, TO_CHOKE_REASON, WALK_REASON, new_policy, step_key,
)

FIXTURE = Path(__file__).with_name("fixtures") / "q18-life523-20261115.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8", errors="surrogateescape") as _stream:
    BOARDS = json.load(_stream)["boards"]
BY_CELL = defaultdict(list)
for _board in BOARDS:
    BY_CELL[(_board["player"]["y"], _board["player"]["x"])].append(_board)
CHOKE, BEHIND = (1, 19), (2, 18)
SQUID, SQUID_INDEX, SQUID_CELL = 482, 8, (5, 26)
BOUND = int(STRATEGIES[18].engagement_plan["find_exit"]["choke_enemy_wait_turns"])


class N1a523Q18OutwaitedSquidTest(executor_harness.RecordedHarness):

    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    def test_the_recorded_boards(self):
        self.assertEqual({cell: len(rows) for cell, rows in BY_CELL.items()}, {CHOKE: 131, BEHIND: 4})
        for raw in BOARDS:
            squid = [row for row in raw["detected_monsters"] if row["index"] == SQUID_INDEX]
            self.assertEqual([(row["race_id"], row["y"], row["x"], row["asleep"]) for row in squid],
                             [(SQUID, *SQUID_CELL, False)])
        self.assertEqual(BOUND, 200)

    @staticmethod
    def raw_at(position, used, turn, squid_cell=None):
        rows = BY_CELL.get(position)
        if rows:
            raw = copy.deepcopy(rows[used[position] % len(rows)])
            used[position] += 1
        else:
            raw = copy.deepcopy(BY_CELL[CHOKE][-1])
            raw["player"].update(y=position[0], x=position[1])
        if squid_cell is not None:
            for row in raw["detected_monsters"]:
                if row["index"] == SQUID_INDEX:
                    row.update(y=squid_cell[0], x=squid_cell[1])
        raw["turn"] = turn
        return raw

    def walk(self, decisions, squid_cell_of=lambda decision: None):
        """(rows, the decision the CLI cell loop guard tripped on, the ping-pong events, policy,
        the last raw board): each row (cell, key, reason)."""
        used = defaultdict(int)
        start = BY_CELL[CHOKE][0]
        policy = new_policy(copy.deepcopy(start))
        position, turn = CHOKE, start["turn"]
        rows, events, tripped = [], [], None
        recent = deque(maxlen=cli.MULTIPLIER_COMBAT_LOOP_WINDOW)
        last_position = last_player = raw = None
        for decision in range(decisions):
            turn += 10
            raw = self.raw_at(position, used, turn, squid_cell_of(decision))
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = str(policy.choose_key(snapshot))
            rows.append((position, key, policy.last_reason))
            if pingpong_guard.report(policy):
                events.append((decision, pingpong_guard.report(policy)))
            previous_position, last_position = last_position, snapshot.player.position
            previous_player, last_player = last_player, snapshot.player
            if cli._cell_loop_guard_applies(snapshot, policy.last_reason, previous_position,
                                            previous_player):
                recent.append((snapshot.floor_key, position[0], position[1]))
                if tripped is None and cli._is_looping(recent):
                    tripped = decision
            else:
                recent.clear()
            delta = next((offset for offset, value in DIRECTION.items() if value == key), None)
            if delta is not None:
                position = (position[0] + delta[0], position[1] + delta[1])
        return rows, tripped, events, policy, raw

    def test_the_bound_outwaits_the_squid_and_the_walk_goes_on(self):
        rows, tripped, events, policy, _ = self.walk(BOUND + 8)
        # As recorded: the squid beside the walk ahead holds the choke for the whole bound.
        self.assertEqual(rows[:BOUND], [(CHOKE, "5", HOLD_REASON)] * BOUND, rows[BOUND - 3:BOUND + 3])
        # Recorded: '1' exit-to-choke onto (2,18), then '9' back, until the stop.
        self.assertEqual(rows[BOUND], (CHOKE, step_key(CHOKE, (2, 20)), WALK_REASON), rows[BOUND:])
        self.assertEqual([cell for cell, _, _ in rows[BOUND:BOUND + 6]],
                         [CHOKE, (2, 20), (3, 20), (4, 21), (5, 22), (5, 23)], rows[BOUND:])
        self.assertEqual(rows[BOUND + 6][1:], ("T" + step_key((5, 24), (5, 25)), DIG_REASON), rows[BOUND:])
        self.assertNotIn(BEHIND, [cell for cell, _, _ in rows])
        self.assertIsNone(tripped, rows[BOUND:])
        self.assertEqual(events, [])
        self.assertEqual(policy._quest_navigators[18].exit_outwaited, {SQUID_INDEX: SQUID})

    def test_no_cell_rocks_back_and_forth(self):
        rows, tripped, _, _, _ = self.walk(BOUND + 8)
        cells = [cell for cell, _, _ in rows]
        rocks = [index for index in range(2, len(cells)) if cells[index] == cells[index - 2] != cells[index - 1]]
        self.assertEqual(rocks, [], rows[BOUND:])
        self.assertIsNone(tripped)

    def test_control_the_squid_seen_closing_in_sends_the_walk_to_a_choke_again(self):
        """DECLARED CONSTRUCTED: from the bound on, the squid on (5,24), two cells nearer (1,19)
        (game distance 7, was 9): ``approaching`` (owner 2026-11-06) still counts it."""
        rows, _, _, policy, _ = self.walk(BOUND + 1, lambda decision: (5, 24) if decision >= BOUND else None)
        self.assertEqual(rows[BOUND], (CHOKE, step_key(CHOKE, BEHIND), TO_CHOKE_REASON), rows[BOUND - 2:])

    def test_control_before_the_bound_the_squid_still_holds_the_choke(self):
        rows, _, _, policy, _ = self.walk(BOUND)
        self.assertEqual(set(rows), {(CHOKE, "5", HOLD_REASON)})
        self.assertEqual(policy._quest_navigators[18].exit_outwaited, {})

    def test_the_walk_on_is_posted_through_the_executor(self):
        rows, _, _, policy, raw = self.walk(BOUND + 1)
        self.assertEqual(rows[-1], (CHOKE, step_key(CHOKE, (2, 20)), WALK_REASON))
        following = self.later(raw)
        following["player"] = dict(following["player"], y=2, x=20)
        self.assertEqual(self.post(policy, raw, rows[-1][1], [], following), [rows[-1][1]])

    def test_the_outwaited_squid_is_off_the_board_reasons_only(self):
        """The record keeps it out of ``mobile_awake`` only while it is the same monster."""
        rows, _, _, policy, raw = self.walk(BOUND + 1)
        navigator = policy._quest_navigators[18]
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        squid = next(monster for monster in snapshot.detected_monsters if monster.index == SQUID_INDEX)
        self.assertTrue(quest_find_exit._outwaited(navigator, squid))
        other = copy.deepcopy(raw)
        for row in other["detected_monsters"]:
            if row["index"] == SQUID_INDEX:
                row["race_id"] = 443  # the index went to a seahorse
        squid = next(monster for monster in parse_snapshot(other, policy._monrace_knowledge).detected_monsters
                     if monster.index == SQUID_INDEX)
        self.assertFalse(quest_find_exit._outwaited(navigator, squid))


if __name__ == "__main__":
    unittest.main()
