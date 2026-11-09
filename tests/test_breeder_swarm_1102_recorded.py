"""breeder-swarm-1102: the recorded n1-c life-098 Software bug swarm (2026-11-02).

n1-c life-098 (Magic-Eater, Lv31, 412 max HP) on 鉄獄24階, random quest 41
(the quest floor's exit is locked), 00:10-00:14: ソフトウェア・バグ (race 246,
4 HP, speed +10, one 1d2 bite, MULTIPLY) grew from 1 to 42.

(a) The breeders were latched as a breakthrough floor (``state 2``), whose
    weakness suppression (``_strategic_subset``: max blow < 5% of max HP) hid
    the bugs biting from every side, and the quest lock leaves the
    breakthrough no exit.  789 decisions beside a bug searched, broke out and
    wandered through 952 bites (HP 412 -> 166, five Potions of Healing).
    Owner rule 「生存処理を優先しなければキャラクタは死亡する。当然の結果。」:
    a weak breeder that strikes from beside the player is fought.
(b) The latch lived in the process only: after the loop-detected stop of
    00:10:35 (turn 2200908) the restarted process (00:10:42) began the floor
    in state 1 and fired bolts (``ranged:fire``) into the 22 bugs until the
    latch re-armed at 00:11:00.  The latch is carried beside the decision
    log (breeder_floor_record).
(c) Owner 2026-11-02 「攻撃用の物資は制限しない。ただし、20ターンで数が減らせない
    なら逃走を選択する。」: the first bug came into view at turn 2199675; the
    recorded build latched the floor eight actions later (state-2 ``search``
    at 2199751, the five-kill growth switch).  Now the floor is latched when
    20 player actions (boards whose game turn advanced) end with no fewer
    breeders than the window began with (breeder_stalemate), and the window
    survives a restart.  Owner 2026-11-07 「クエストの無い階でも、20回は増える敵に
    攻撃を始めてから数える。」: the window opens on the board that shows the first
    attack landed (turn 2199693, the first bug killed, two bugs on the board
    before), not on the first bug seen, so the floor latches at turn 2199896.

Fixture: tests/fixtures/breeder-swarm-20261102.json.gz
(tests/extract_breeder_swarm_1102_fixture.py).  Every decision is the public
``choose_key``; posted keys go through the production executor port
(test_me_nokey_1031_recorded.PostedKey).
DECLARED RECONSTRUCTED: the capture's policy state holds
``_fixed_quest_speed_attempted`` true (the quest's Potion of Speed was already
drunk; the restarted process drank it at turn 2200918, the board its policy
is primed on); the swarm boards and the stopped process's restart boards start with the floor latched (their recorded
``search`` / ``breakout:*`` answers are the latch's; the latch itself is not
in the diagnostic policy state).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hengbot.breeder_stalemate import FLEE_AFTER_PLAYER_ACTIONS
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy
from tests.support import recorded as executor_pins
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops
from tests.support.recorded import READ_PROMPT


FIXTURE = Path(__file__).with_name("fixtures") / "breeder-swarm-20261102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
SOFTWARE_BUG = 246
QUEST_FLOOR = (1, 24, 41)


def recorded():
    return {row["turn"]: (row["reason"], row["key"]) for row in CASE["decisions"]}


def new_policy(boards):
    policy = loops.new_policy(dict(CASE, boards=boards), CASE["skill"],
                              monraces=CASE["monraces"])
    # DECLARED RECONSTRUCTED (module docstring).
    policy._fixed_quest_speed_attempted = True
    return policy


def board(policy, raw):
    return parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)


class PostedSwarmKey(nokey.PostedKey):
    def drive(self, policy, boards):
        return loops.MeStaffLoopsRecordedTest.drive(self, policy, boards)

    def post(self, policy, raw, key):
        """A read is answered by the scroll chooser (cmd-read.cpp)."""
        if not key.startswith("r"):
            return super().post(policy, raw, key)
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(READ_PROMPT),
                        executor_pins.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, list(key))


class BitingSwarmRecordedTest(PostedSwarmKey):
    """(a) beside biting weak breeders on a latched quest floor: melee."""

    def test_recorded_rows_searched_beside_the_biting_bugs(self):
        rows = recorded()
        searched = [raw for raw in CASE["swarm"] if rows[raw["turn"]][0] == "search"]
        self.assertEqual(len(searched), 8)
        policy = new_policy(CASE["swarm"])
        for raw in searched:
            snapshot = board(policy, raw)
            self.assertEqual(snapshot.floor_key, QUEST_FLOOR)
            adjacent = [m for m in snapshot.visible_monsters
                        if m.race_id == SOFTWARE_BUG and m.distance <= 1]
            self.assertGreaterEqual(len(adjacent), 6, raw["turn"])
            self.assertTrue(policy._is_weak_breeder(snapshot, adjacent[0]))
        self.assertTrue(any("ソフトウェア・バグに噛まれた。" in message
                            for raw in searched for message in raw["messages"]))

    def test_latched_quest_floor_melees_the_biting_bugs(self):
        boards = CASE["swarm"][1:]
        policy = new_policy(boards)
        policy._breeder_breakthrough_floor = QUEST_FLOOR
        rows = self.drive(policy, boards)
        for raw, key, reason in rows:
            self.assertEqual(reason, "melee", (raw["turn"], key))
        self.assertEqual(policy._breeder_breakthrough_floor, QUEST_FLOOR)


STOP_TURN, RESTART_SKILL_TURN = 2200908, 2200918


class RecordedRestart(PostedSwarmKey):
    """The restart record beside a temporary decision log."""

    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.record = Path(directory.name) / "breeder-floor.json"

    def restarted_policy(self, boards):
        """A new process: the CLI points the record path before its first board."""
        record = self.record

        class Restarted(ConservativePolicy):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._breeder_floor_record_path = record

        with mock.patch.object(loops, "ConservativePolicy", Restarted):
            return new_policy(boards)


class RestartKeepsTheLatchRecordedTest(RecordedRestart):
    """(b) the restarted process keeps the floor in state 2."""

    def test_recorded_restart_fired_bolts(self):
        rows = recorded()
        after = [raw["turn"] for raw in CASE["restart"] if raw["turn"] > RESTART_SKILL_TURN]
        self.assertEqual({rows[turn][0] for turn in after}, {"ranged:fire"})
        # The stopped process: latched (state 2) breakouts.
        self.assertEqual({rows[raw["turn"]][0] for raw in CASE["restart"]
                          if raw["turn"] < STOP_TURN},
                         {"breakout:least-visited", "no-wait:melee"})
        # The restarted one drank the quest's Potion of Speed, then fired.
        self.assertEqual(rows[RESTART_SKILL_TURN], ("quest:quaff-speed", "qa"))

    def test_restart_on_the_latched_floor_stays_in_state_2(self):
        stopped = [raw for raw in CASE["restart"] if raw["turn"] < STOP_TURN]
        restarted = [raw for raw in CASE["restart"] if raw["turn"] >= RESTART_SKILL_TURN]
        previous = new_policy(stopped)
        previous._breeder_floor_record_path = self.record
        previous._breeder_breakthrough_floor = QUEST_FLOOR
        for raw in stopped:
            previous.confirm_key_posted(loops.decide(previous, raw))
        self.assertTrue(self.record.exists())
        policy = self.restarted_policy(restarted)
        self.assertEqual(policy._breeder_breakthrough_floor, QUEST_FLOOR)
        rows = self.drive(policy, restarted[1:])
        for raw, key, reason in rows:
            self.assertFalse(reason.startswith("ranged:"), (raw["turn"], key, reason))
        self.assertEqual(policy._breeder_breakthrough_floor, QUEST_FLOOR)


ENGAGED_TURN, RECORDED_LATCH_TURN = 2199675, 2199751
FIRST_KILL_TURN, FLEE_TURN = 2199693, 2199896  # owner 2026-11-07: counted from the first attack


class TwentyActionFlightRecordedTest(RecordedRestart):
    """(c) the window counts from the first attack (now 100 attacks, owner 2026-11-09)."""

    def test_recorded_rows_latched_after_eight_actions(self):
        rows = recorded()
        turns = [raw["turn"] for raw in CASE["engage"]]
        self.assertEqual(turns[0], ENGAGED_TURN)
        self.assertEqual(turns.index(RECORDED_LATCH_TURN), 8)
        self.assertEqual(turns.index(FIRST_KILL_TURN), 2)
        self.assertEqual(turns.index(FLEE_TURN), 22)
        exp = [raw["player"]["exp"] for raw in CASE["engage"]]
        self.assertEqual(exp[:3], [exp[0], exp[0], exp[0] + 3])  # the first kill's experience
        self.assertEqual(rows[RECORDED_LATCH_TURN], ("search", "s"))
        counts = [sum(m["race_id"] == SOFTWARE_BUG for m in raw["visible_monsters"])
                  for raw in CASE["engage"]]
        self.assertEqual(counts[0], 1)
        self.assertTrue(all(count >= 1 for count in counts))

    def latched_turns(self, policy, boards):
        rows = self.drive(policy, boards)
        return [(raw["turn"], policy_floor) for (raw, _key, _reason), policy_floor
                in zip(rows, self._latches)]

    def drive(self, policy, boards):
        self._latches = []
        rows = []
        for raw in boards:
            rows.extend(super().drive(policy, [raw]))
            self._latches.append(policy._breeder_breakthrough_floor)
        return rows

    def assert_no_flight_inside_the_window(self, turns):
        # Owner 2026-11-09 「加えて判断の窓を長く取る。20回は短いようだ。」→「100回」: under the
        # 20-attack window these boards latched at FLEE_TURN (the window from two bugs ended at
        # its 20th attack with more); under 100 that window is still open on the last board.
        for turn, latch in turns:
            self.assertIsNone(latch, turn)

    def test_the_recorded_boards_stay_inside_one_window(self):
        self.assertEqual(FLEE_AFTER_PLAYER_ACTIONS, 100)
        policy = new_policy(CASE["engage"])
        turns = self.latched_turns(policy, CASE["engage"])
        self.assert_no_flight_inside_the_window(turns)
        self.assertEqual((policy._breeder_engagement_start_count,
                          policy._breeder_engagement_actions), (2, 21))
        rows = self.drive(new_policy(CASE["engage"]), CASE["engage"][:22])
        for raw, key, reason in rows:
            self.assertIn(reason, {"melee", "ranged:fire"}, (raw["turn"], key))

    def test_restart_keeps_the_engagement_window(self):
        boards = CASE["engage"]
        previous = new_policy(boards)
        previous._breeder_floor_record_path = self.record
        before = self.latched_turns(previous, boards[:10])
        policy = self.restarted_policy(boards[10:])
        after = self.latched_turns(policy, boards[10:])
        self.assert_no_flight_inside_the_window(before + after)
        self.assertEqual((policy._breeder_engagement_start_count,
                          policy._breeder_engagement_actions), (2, 21))

if __name__ == "__main__":
    unittest.main()
