"""The quest search's cast stop waits for the detection spacing (n1-b life-348, Angband 62F board).

Owner 2026-11-08, Q1 「待って唱える」: 「その地点で間隔が来るまで休んで待ち、唱えてから次の地点へ行く。
覆いの抜けがなくなる。待ちの間に敵が来れば今の決まりで対処する。」  Q2 「数えない」: 「今のまま半径30で
地点を決める。安全で強力発動を使えた時は、覆えた分を後から済みに数える。」

The board is the recorded 62F one (tests/test_n1b_62f_quest_cover_1108_recorded.py).  On it the
new-floor row casts the powerful Detection (radius 45) at the start (17,132); the lap is drawn
after it with cast stops of the plain radius 30.  The cast stop (4,166) lies 37 from the start,
inside the first cast's 45 and 590 game turns short of HUNT_REDETECT_GAME_TURNS when the player
stands on it: the spacing (me_powers.redetect_due) has not come.

DECLARED CONSTRUCTED: n1-b's absorbed Detection and Detect Evil with charges (as the 62F test
does); each cast landed (the board after it carries the game's ``_completed_operation_owner``, as
recorded_session_replay writes it); the player's walk to (4,166) (placed there 400 game turns
later); the east frontiers the replayed explore names written off (the 62F test's ``to_the_lap``).
WALLED (after the producer and the consumer under test): the secret-door round and the door
detection (quest_target_search._door_search_key, door_means_key) answer nothing, because on this
board the ground cut off by the earthquake starts a door round at once, which walks away from the
lap; the lap's wait is asked after them, where the lap is what walks.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import io
import time
import unittest
from unittest import mock

import hengbot.policy  # noqa: F401 -- loads the modules in their cycle-safe order
from hengbot import me_powers
from hengbot import quest_target_search as search
from hengbot.cli import (
    STATIONARY_EXEMPT_REASONS, PostingContract, _cell_loop_guard_applies, _ExecutorInputPort,
    _send_decision_key_with_prompt_chain,
)
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot import search_coverage
from hengbot.model import Position, game_distance, parse_snapshot
from tests import test_input_executor as executor_harness
from tests import test_n1b_62f_quest_cover_1108_recorded as recorded
from tests.test_n1c_loops_0336_1102_recorded import REST_PROMPT

# Held as a module, not a name: a test class bound here would be collected and run again.
Recorded, MOVES = recorded.N1b62fQuestCoverRecordedTest, recorded.MOVES  # deleted below

STOP = Position(4, 166)          # a cast stop (radius 30) 37 from the start's cast
START = Position(17, 132)
ABSORBED = {"rod:6": 10, "staff:15": 10}
WALKED = 400                     # game turns from the first cast to standing on STOP
CAST_REASONS = ("me-power:new-floor:detect-all:powerful", "me-power:hunt-target-unseen:detect-all:powerful")


class QuestCoverRedetectWaitTest(executor_harness.ProductionHarness):
    setUpClass = classmethod(Recorded.setUpClass.__func__)
    snapshot = Recorded.snapshot
    choose = Recorded.choose
    policy = Recorded.policy
    to_the_lap = Recorded.to_the_lap

    def following(self, policy, raw, key, landed=False, elapsed=10):
        board = copy.deepcopy(raw)
        board["turn"] += elapsed
        board["messages"] = []
        board.pop("_completed_operation_owner", None)
        if landed:
            board["_completed_operation_owner"] = policy.last_reason
        if key in MOVES:
            board["player"]["y"] += MOVES[key][0]
            board["player"]["x"] += MOVES[key][1]
        return board

    def decide(self, policy, raw):
        policy._recent.clear()  # the same board each time: no oscillation, no livelock
        policy._move_repeat = 0
        return self.choose(policy, raw)

    def at_the_stop(self):
        """(policy, raw, first cast's turn) with the player standing on STOP, the lap drawn after
        the start's powerful cast."""
        policy, raw = self.policy()
        policy._me_staff_sequence = MeStaffSequence(absorbed=dict(ABSORBED))
        key = self.decide(policy, raw)
        self.assertEqual(policy.last_reason, CAST_REASONS[0])
        cast = raw["turn"]
        raw = self.following(policy, raw, key, landed=True)
        self.to_the_lap(policy, raw)
        memory = getattr(policy, search.MEMORY)
        self.assertEqual(memory.stop_radius.get(STOP), 30)
        self.assertGreater(memory.lap_turn, cast)
        self.enterContext(mock.patch.object(search, "_door_search_key", return_value=None))
        self.enterContext(mock.patch.object(search, "door_means_key", return_value=None))
        raw = self.following(policy, raw, None, elapsed=cast + WALKED - raw["turn"])
        raw["player"]["y"], raw["player"]["x"] = STOP.y, STOP.x
        return policy, raw, cast

    def test_before_the_spacing_the_player_rests_on_the_cast_stop(self):
        policy, raw, cast = self.at_the_stop()
        memory = getattr(policy, search.MEMORY)
        key = self.decide(policy, raw)
        self.assertEqual(policy.last_reason, search.REDETECT_WAIT_REASON)
        # 1,000 - 400 game turns, 10 a rest: the rest ends where the spacing comes.
        self.assertEqual(key, "R60\r")
        self.assertNotIn(STOP, memory.seen)
        # The rest goes through the input path as any rest (its count answers the prompt).
        self.post_rest(policy, raw, key, self.following(policy, raw, key, elapsed=600))
        # The loop guard knows the wait as bounded.
        self.assertIn(search.REDETECT_WAIT_REASON, STATIONARY_EXEMPT_REASONS)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertFalse(_cell_loop_guard_applies(board, search.REDETECT_WAIT_REASON))

    def test_a_rest_cut_short_rests_again_for_what_is_left(self):
        policy, raw, cast = self.at_the_stop()
        key = self.decide(policy, raw)
        raw = self.following(policy, raw, key, elapsed=200)  # a monster in view cut it short
        key = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("R40\r", search.REDETECT_WAIT_REASON))
        self.assertNotIn(STOP, getattr(policy, search.MEMORY).seen)

    def test_when_the_spacing_comes_the_cast_is_made_there_then_the_next_stop(self):
        policy, raw, cast = self.at_the_stop()
        memory = getattr(policy, search.MEMORY)
        key = self.decide(policy, raw)
        self.assertEqual(policy.last_reason, search.REDETECT_WAIT_REASON)
        raw = self.following(policy, raw, key, elapsed=cast + me_powers.HUNT_REDETECT_GAME_TURNS - raw["turn"])
        key = self.decide(policy, raw)
        self.assertEqual(policy.last_reason, CAST_REASONS[1])
        self.assertNotIn(STOP, memory.seen)
        raw = self.following(policy, raw, key, landed=True)
        uses = getattr(policy, me_powers.MEMORY).uses
        key = self.decide(policy, raw)
        self.assertEqual([(use.position, use.reason) for use in uses],
                         [(START, CAST_REASONS[0]), (STOP, CAST_REASONS[1])])
        self.assertIn(STOP, memory.seen)
        self.assertEqual(policy.last_reason, search.LOOP_REASON)
        self.assertIn(key, MOVES)
        self.assertNotEqual(memory.goal, STOP)

    def test_a_powerful_cast_counts_its_own_reach(self):
        """Q2: the stops are drawn for 30, and the powerful cast's 45 covers the stops in it."""
        policy, raw, cast = self.at_the_stop()
        memory = getattr(policy, search.MEMORY)
        key = self.decide(policy, raw)
        raw = self.following(policy, raw, key, elapsed=cast + me_powers.HUNT_REDETECT_GAME_TURNS - raw["turn"])
        key = self.decide(policy, raw)
        raw = self.following(policy, raw, key, landed=True)
        self.decide(policy, raw)
        # Telepathy stops (radius 20) that the walk and a plain 30 at STOP would leave grids of,
        # covered by the cast's own 45 (me_powers._cast_radius): seen without being walked to.
        board = self.snapshot(policy, raw)
        shape = (board.height, board.width)
        plain = search_coverage.floor_grids(board) & ~(
            memory.cover.mask(shape) | search_coverage.covered(shape, [((STOP.y, STOP.x), 30)]))
        wide = search_coverage.floor_grids(board) & ~(
            memory.cover.mask(shape) | search_coverage.covered(shape, [((STOP.y, STOP.x), 45)]))
        beyond = [stop for stop in memory.stops if memory.stop_radius[stop] == 20
                  and search_coverage.disc_left(plain, (stop.y, stop.x), 20)
                  and not search_coverage.disc_left(wide, (stop.y, stop.x), 20)]
        self.assertIn(Position(31, 168), beyond)
        self.assertGreaterEqual(len(beyond), 2)
        self.assertEqual([stop for stop in beyond if stop not in memory.seen], [])

    def post_rest(self, policy, raw, key, following):
        game = executor_harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = executor_harness.command_screen(raw["turn"])
        game.screens = [executor_harness.prompt_screen(REST_PROMPT),
                        executor_harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw), copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "quest-cover-redetect-wait", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, (getattr(port.last_result, "reason", None), game.accepted))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, ["R", key[1:]])

    def test_with_no_charge_left_the_stop_is_seen_on_arrival(self):
        """No held means: nothing is waited for (the cast cannot come), as before."""
        policy, raw, cast = self.at_the_stop()
        policy._me_staff_sequence = MeStaffSequence(absorbed={"rod:6": 0, "staff:15": 0})  # DECLARED spent
        self.decide(policy, raw)
        self.assertNotEqual(policy.last_reason, search.REDETECT_WAIT_REASON)
        self.assertIn(STOP, getattr(policy, search.MEMORY).seen)


del Recorded


if __name__ == "__main__":
    unittest.main()
