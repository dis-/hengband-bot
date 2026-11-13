"""The left-cell registry, its reader and the ping-pong guard (owner 2026-11-13 「1と2だけ」).

DECLARED CONSTRUCTED: every board here is built by hand (a four-cell corridor on a dungeon
floor, tests.policy_fixtures); no capture is replayed (the owner rejected part 3, a suite of the
old captures).  The walker test goes through the public ``choose_key``; the registry, reader and
guard tests call the modules' own functions with constructed policies and boards.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import engagement_avoid_seal, kill_all_patrol, left_cells, pingpong_guard, retreat_veto_life
from hengbot.cli import _loop_stop_due, _write_decision
from hengbot.loop_detection import LOOP_WINDOW
from hengbot.model import Position, Snapshot
from hengbot.policy import HengbotPolicy
from tests.policy_fixtures import grid, player

FLOOR = (3, 19, 0)
P, Q = Position(27, 93), Position(26, 93)


def corridor(position=P, *, turn=1000, floor=FLOOR):
    """(28,93)-(27,93)-(26,93)-(25,93), an item at the far end (the corridor of the warning tests)."""
    grids = {
        Position(28, 93): grid(28, 93),
        Position(27, 93): grid(27, 93),
        Position(26, 93): grid(26, 93),
        Position(25, 93): grid(25, 93, objects=1, unsafe=True),
    }
    return Snapshot(player(position.y, position.x, hp=606, max_hp=606, level=31), grids, [],
                    floor_key=floor, turn=turn)


class RegistryTest(unittest.TestCase):
    def test_retreat_lifetime_is_the_engagement_claim(self):
        policy, board = HengbotPolicy(), corridor()
        monster = mock.Mock(index=7, race_id=348)
        monster.name = "dark elven lord"
        recorded = left_cells.leave(policy, board, (P,), owner="threat:avoid-engagement",
                                    threats=(monster,))
        self.assertEqual(recorded, frozenset({P}))
        self.assertIn(P, policy._engagement_owned_avoid_cells)
        self.assertIn(P, policy._engagement_avoid_cells)
        self.assertEqual(getattr(policy, retreat_veto_life.MEMORY).owners[P], {(7, 348)})
        self.assertEqual(left_cells.who_left(policy, P), {"threat:avoid-engagement"})
        self.assertIn(P, left_cells.refused(policy, board))

    def test_policy_claim_goes_through_the_registry(self):
        policy, board = HengbotPolicy(), corridor()
        policy._claim_engagement_avoid_cells((P,), snapshot=board, owner="flee")
        self.assertEqual(left_cells.who_left(policy, P), {"flee"})

    def test_boards_lifetime_ends_after_its_decisions(self):
        policy, board = HengbotPolicy(), corridor()
        policy._decision_sequence = 10
        left_cells.leave(policy, board, (Q,), owner="pingpong:a/b", boards=3)
        self.assertNotIn(Q, policy._engagement_avoid_cells)  # not the claim's storage
        policy._decision_sequence = 13
        self.assertIn(Q, left_cells.refused(policy, board))
        policy._decision_sequence = 14
        self.assertNotIn(Q, left_cells.refused(policy, board))

    def test_game_turns_lifetime_ends_by_the_clock(self):
        policy = HengbotPolicy()
        left_cells.leave(policy, corridor(turn=1000), (Q,), owner="unseen:reverse-choke",
                         game_turns=50)
        self.assertIn(Q, left_cells.refused(policy, corridor(turn=1049)))
        self.assertNotIn(Q, left_cells.refused(policy, corridor(turn=1050)))

    def test_floor_change_forgets_bounded_records(self):
        policy = HengbotPolicy()
        left_cells.leave(policy, corridor(), (Q,), owner="pingpong:a/b", boards=40)
        self.assertNotIn(Q, left_cells.refused(policy, corridor(floor=(3, 20, 0))))
        left_cells.leave(policy, corridor(floor=(3, 20, 0)), (P,), owner="x", boards=40)
        self.assertEqual(getattr(policy, left_cells.MEMORY).floor_key, (3, 20, 0))
        self.assertNotIn(Q, getattr(policy, left_cells.MEMORY).bounded)

    def test_a_record_that_seals_the_player_is_not_made(self):
        policy, board = HengbotPolicy(), corridor()
        with mock.patch.object(engagement_avoid_seal, "seals", return_value=True) as seals:
            recorded = left_cells.leave(policy, board, (P,), owner="detected:prepare-choke",
                                        threats=(), step=Q)
        seals.assert_called_once_with(policy, board, P, Q)
        self.assertEqual(recorded, frozenset())
        self.assertNotIn(P, policy._engagement_avoid_cells)


class ReaderTest(unittest.TestCase):
    def test_survival_walks_do_not_read_bounded_records(self):
        policy, board = HengbotPolicy(), corridor()
        left_cells.leave(policy, board, (Q,), owner="pingpong:a/b", boards=40)
        left_cells.leave(policy, board, (Position(28, 93),), owner="flee")
        with left_cells.survival_walks(policy):
            self.assertEqual(left_cells.refused(policy, board), {Position(28, 93)})
        self.assertEqual(left_cells.refused(policy, board), {Q, Position(28, 93)})

    def test_bounded_records_that_enclose_the_player_are_not_read(self):
        policy, board = HengbotPolicy(), corridor()
        left_cells.leave(policy, board, (Q,), owner="pingpong:a/b", boards=40)
        # A way on over the records, none without them: the walk is the only way out.
        with mock.patch.object(engagement_avoid_seal, "_way_on",
                               side_effect=lambda policy, snapshot, start, closed: not closed):
            self.assertNotIn(Q, left_cells.refused(policy, board))
        policy._decision_sequence += 1  # a new decision: the cached reading is not reused
        with mock.patch.object(engagement_avoid_seal, "_way_on", return_value=True):
            self.assertIn(Q, left_cells.refused(policy, board))

    def test_walk_veto_holds_the_registry(self):
        policy, board = HengbotPolicy(), corridor()
        left_cells.leave(policy, board, (Q,), owner="pingpong:a/b", boards=40)
        policy._build_grid_index(board)
        self.assertIn(Q, policy._walk_veto(board))

    def test_seek_loot_does_not_step_back_into_a_left_cell(self):
        """Through choose_key: the loot walk steps '8' toward the item; with (26,93) left by
        another owner it does not."""
        control, policy = HengbotPolicy(), HengbotPolicy()
        for each in (control, policy):  # the first board is the floor's arrival (memories reset)
            self.assertEqual(each.choose_key(corridor()), "8")
        self.assertEqual(control.choose_key(corridor()), "8")
        self.assertEqual(control.last_reason, "seek-loot")
        left_cells.leave(policy, corridor(), (Q,), owner="pingpong:explore/seek-loot", boards=40)
        self.assertNotEqual(policy.choose_key(corridor()), "8")

    def test_quest_patrol_walk_refuses_a_left_cell(self):
        policy, board = HengbotPolicy(), corridor()
        policy._build_grid_index(board)
        far = lambda cell: cell == (25, 93)  # noqa: E731
        self.assertEqual(kill_all_patrol._toward(policy, board, far), Q)
        left_cells.leave(policy, board, (Q,), owner="pingpong:a/b", boards=40)
        self.assertIsNone(kill_all_patrol._toward(policy, board, far))


class GuardTest(unittest.TestCase):
    def _walk(self, policy, moves, *, start=P, turn=1000):
        """Feed ``observe`` the boards of ``moves`` [(owner, position after)], as choose_key would:
        the previous decision's reason, then the board the move produced."""
        board = corridor(start, turn=turn)
        pingpong_guard.observe(policy, board)
        reports = []
        for owner, position in moves:
            policy._decision_entry_reason = owner
            policy._decision_sequence += 1
            turn += 10
            board = corridor(position, turn=turn)
            pingpong_guard.observe(policy, board)
            reports.append(pingpong_guard.report(policy))
        return board, reports

    def alternation(self, a="explore", b="seek-loot"):
        return [(a, Q), (b, P), (a, Q), (b, P)]

    def test_two_round_trips_give_the_first_owner_its_left_cell(self):
        policy = HengbotPolicy()
        board, reports = self._walk(policy, self.alternation())
        self.assertEqual(reports, [None, None, None, "pingpong:explore/seek-loot"])
        self.assertIn(P, left_cells.refused(policy, board))  # the cell explore left
        self.assertEqual(left_cells.who_left(policy, P), {"pingpong:explore/seek-loot"})
        self.assertTrue(pingpong_guard.holds_loop_stop(policy, board))
        policy._decision_sequence += LOOP_WINDOW
        self.assertTrue(pingpong_guard.holds_loop_stop(policy, board))
        policy._decision_sequence += 1
        self.assertFalse(pingpong_guard.holds_loop_stop(policy, board))
        self.assertNotIn(P, left_cells.refused(policy, board))

    def test_one_round_trip_is_a_hand_over(self):
        policy = HengbotPolicy()
        _board, reports = self._walk(policy, self.alternation()[:3])
        self.assertEqual(reports, [None, None, None])

    def test_the_higher_ranked_owner_wins(self):
        """The step back's owner ranks higher (the ladder asks it first): the cell it left, q."""
        policy = HengbotPolicy()
        ranks = iter([20, 5, 20, 5])
        with mock.patch.object(pingpong_guard, "_previous_rank", side_effect=lambda _p: next(ranks)):
            board, reports = self._walk(policy, self.alternation("explore", "threat:avoid-engagement"))
        self.assertEqual(reports[-1], "pingpong:explore/threat:avoid-engagement")
        self.assertIn(Q, left_cells.refused(policy, board))
        self.assertNotIn(P, left_cells.refused(policy, board))

    def test_a_survival_reason_is_never_refused(self):
        policy = HengbotPolicy()
        board, reports = self._walk(policy, self.alternation("explore", "flee"))
        self.assertEqual(reports, [None] * 4)
        self.assertFalse(left_cells.refused(policy, board))
        self.assertFalse(pingpong_guard.holds_loop_stop(policy, board))

    def test_a_relocation_is_not_a_walk(self):
        policy = HengbotPolicy()
        far = Position(28, 93)
        moves = [("explore", Q), ("seek-loot", P), ("explore", Q), ("seek-loot", far)]
        _board, reports = self._walk(policy, moves)  # (26,93)->(28,93) is two cells
        self.assertEqual(reports, [None] * 4)

    def test_the_same_pair_again_escalates_to_the_livelock_leave(self):
        policy = HengbotPolicy()
        board, reports = self._walk(policy, self.alternation())
        self.assertFalse(policy._nav_exhausted)
        board, reports = self._walk(policy, self.alternation(), turn=board.turn)
        self.assertEqual(reports[-1], "pingpong-escalate:explore/seek-loot")
        self.assertTrue(policy._nav_exhausted)
        policy.last_reason = "explore"
        with mock.patch.object(policy, "_navigation_livelock_key", return_value="r_") as leave:
            self.assertEqual(pingpong_guard.after_ladder(policy, board, "8"), "r_")
        leave.assert_called_once_with(board)
        policy.last_reason = "flee"  # the survival rungs always win
        with mock.patch.object(policy, "_navigation_livelock_key", return_value="r_"):
            self.assertEqual(pingpong_guard.after_ladder(policy, board, "2"), "2")

    def test_no_escalation_without_a_window_given(self):
        policy = HengbotPolicy()
        board = corridor()
        with mock.patch.object(policy, "_navigation_livelock_key", return_value="r_") as leave:
            self.assertEqual(pingpong_guard.after_ladder(policy, board, "8"), "8")
        leave.assert_not_called()

    def test_loop_detector_is_held_inside_the_window_only(self):
        policy = HengbotPolicy()
        cells = [(FLOOR, 27, 93), (FLOOR, 26, 93)] * (LOOP_WINDOW // 2)
        board = corridor()
        self.assertTrue(_loop_stop_due(cells, LOOP_WINDOW, policy, board))
        board, _reports = self._walk(policy, self.alternation())
        self.assertFalse(_loop_stop_due(cells, LOOP_WINDOW, policy, board))
        policy._decision_sequence += LOOP_WINDOW + 1
        self.assertTrue(_loop_stop_due(cells, LOOP_WINDOW, policy, board))

    def test_the_event_is_in_the_decision_log(self):
        policy = HengbotPolicy()
        board, _reports = self._walk(policy, self.alternation())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            _write_decision(path, board, "8", "explore", policy)
            row = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(row["pingpong"], "pingpong:explore/seek-loot")

    def test_reasons_registry_names_the_survival_reasons(self):
        from hengbot import reasons
        self.assertTrue(reasons.survival("flee"))
        self.assertTrue(reasons.survival("emergency:teleport"))
        self.assertTrue(reasons.survival("sensed-t1:walk"))
        self.assertFalse(reasons.survival("seek-downstairs"))
        self.assertFalse(reasons.survival("explore"))
        self.assertFalse(reasons.survival("threat:avoid-engagement"))
        self.assertFalse(reasons.survival(None))


if __name__ == "__main__":
    unittest.main()
