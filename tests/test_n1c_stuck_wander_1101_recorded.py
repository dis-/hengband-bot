"""D60 (#47): why n1-c life-098 wandered on 鉄獄12階 instead of leaving (2026-11-01).

Owner 2026-11-01: 「n1-cがダンジョン内でstuck:wanderしていた理由」.  life-098
(Lv21 Magic-Eater, build bot-461b75b92) was on the floor of runtime RANDOM
quest 43 with the breeder breakthrough latched on it (earlier breeder fights on
the floor).  An emergency teleport (19:58:44) put it in a pocket west of the
known up-stairs (4,81).  The kill-quest exit lock holds every exit until the
stall boundary (_quest_floor_exit_locked: a runtime RANDOM quest is given up
once ``_stuck_escape_streak`` reaches STUCK_ESCAPE_LIMIT = 60).  On the 61st
decision the breakthrough, ranked above the town return, took it: its Recall
asked only whether any quest was active, so it stepped toward the up-stairs
instead (``breeder-breakthrough:seek-upstairs``); that step reset the streak
and the lock closed again.  One step every 61 decisions (recorded rows 9057 and
9118, 60 ``stuck:wander`` rows between), until livelock-exhausted at 20:02:40.
After the restart (no latch) the 61st decision was the town return's Recall
(``return:recall`` 'ri', pack-full) and the character left.

Fixture: tests/fixtures/n1c-stuck-wander-1101.json.gz
(tests/extract_n1c_stuck_wander_1101_fixture.py).  Every decision is the public
``choose_key``; posted keys go through the production executor port.
DECLARED RECONSTRUCTED: the remembered terrain is the capture's policy-state
``terrain`` (written 400 game turns after the first board, the player still in
the same pocket); the breakthrough latch names this floor (only a latched floor
emits ``breeder-breakthrough:*``, recorded rows 9057/9118); the streak before
row 9118 is the 60 stuck rows 9058-9117 (59 counted, the observation of row
9118 counts the 60th) with ``last_reason`` the recorded ``stuck:wander``.
DECLARED CONSTRUCTED: the walk case takes the Scrolls of Word of Recall out of
both boards (a character that cannot read Recall must still walk out).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.cli import SendResult, _ExecutorInputPort, _transport_key
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import STUCK_ESCAPE_LIMIT
from tests.support import recorded as executor_pins
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-stuck-wander-1101.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
RELEASE_TURN, ARRIVAL_TURN = 1188007, 1188021
UPSTAIRS = Position(4, 81)
READ_PROMPT = "どの巻物を読みますか? "
TV_SCROLL, SV_RECALL = 70, 11
WALK = {"breeder-breakthrough:seek-upstairs", "breeder-breakthrough:seek-frontier"}


def without_recall(raw):
    raw = copy.deepcopy(raw)
    raw["inventory"] = [item for item in raw["inventory"]
                        if (item["tval"], item.get("sval")) != (TV_SCROLL, SV_RECALL)]
    return raw


def recorded_policy(boards, *, streak):
    """The live policy at the board of row 9118 (see DECLARED RECONSTRUCTED)."""
    case = dict(CASE, boards=boards)
    policy = loops.new_policy(case, CASE["skill"], monraces=CASE["monraces"])
    terrain = CASE["terrain"]
    for name in ("known_t", "marked_t", "floor_t", "wall_t", "door_t", "rubble_t"):
        cells = getattr(policy, f"_remembered_{name}")
        cells.clear()
        cells.update(tuple(cell) for cell in terrain[name])
    policy._remembered_upstairs.clear()
    policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
    policy._breeder_breakthrough_floor = parse_snapshot(
        copy.deepcopy(boards[0]), policy._monrace_knowledge).floor_key
    policy._stuck_escape_streak = streak
    policy.last_reason = "stuck:wander"
    return policy


class StuckWanderRecordedTest(executor_pins.ProductionHarness):
    def post(self, policy, raw, key, following, screens=()):
        game = executor_pins.FaithfulHookGame()
        game.capacity = 256
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [*screens, executor_pins.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual("".join(game.accepted), _transport_key(key, True))
        policy.confirm_key_posted(key)
        return port.last_result.board

    def test_recorded_rows(self):
        rows = {row["decision_sequence"]: row for row in CASE["decisions"]}
        between = [rows[sequence]["reason"] for sequence in range(9058, 9118)]
        self.assertEqual(len(between), STUCK_ESCAPE_LIMIT)
        self.assertEqual(set(between), {"stuck:wander"})
        self.assertEqual((rows[9118]["turn"], rows[9118]["reason"], rows[9118]["key"]),
                         (RELEASE_TURN, "breeder-breakthrough:seek-upstairs", "1"))
        self.assertEqual(rows[9119]["turn"], ARRIVAL_TURN)
        self.assertEqual(rows[9119]["reason"], "stuck:wander")
        board = CASE["boards"][0]
        self.assertEqual(board["floor"]["quest_id"], 43)
        self.assertFalse(board["player"]["recalling"])
        self.assertIn([UPSTAIRS.y, UPSTAIRS.x], CASE["terrain"]["upstairs"])
        self.assertEqual(sum(item["count"] for item in board["inventory"]
                             if (item["tval"], item.get("sval")) == (TV_SCROLL, SV_RECALL)), 9)

    def test_released_quest_lock_reads_recall_on_the_latched_floor(self):
        boards = copy.deepcopy(CASE["boards"])
        policy = recorded_policy(boards, streak=STUCK_ESCAPE_LIMIT - 1)
        raw = boards[0]
        key = loops.decide(policy, raw)
        # Recorded (unfixed): breeder-breakthrough:seek-upstairs '1', the lock
        # closing again on the next board.
        self.assertEqual((policy.last_reason, key[:1]), ("breeder-breakthrough:recall", "r"))
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10,
                         messages=["回りの大気が張りつめてきた..."])
        following["player"]["recalling"] = True
        board = self.post(policy, raw, key, following,
                          [executor_pins.prompt_screen(READ_PROMPT)])
        self.assertTrue(board["player"]["recalling"])

    def test_control_the_held_lock_keeps_the_quest_floor(self):
        boards = copy.deepcopy(CASE["boards"])
        policy = recorded_policy(boards, streak=STUCK_ESCAPE_LIMIT - 2)
        key = loops.decide(policy, boards[0])
        self.assertFalse(policy.last_reason.startswith("breeder-breakthrough:"), key)
        self.assertNotEqual(key[:1], "r")

    def test_without_recall_the_breakthrough_walk_keeps_the_release(self):
        boards = [without_recall(raw) for raw in CASE["boards"]]
        policy = recorded_policy(boards, streak=STUCK_ESCAPE_LIMIT - 1)
        first, arrival = boards
        key = loops.decide(policy, first)
        self.assertEqual((policy.last_reason, key), ("breeder-breakthrough:seek-upstairs", "1"))
        board = self.post(policy, first, key, arrival)
        self.assertEqual((board["player"]["y"], board["player"]["x"]), (15, 13))
        # Recorded (unfixed): the step reset the streak, the lock closed and
        # row 9119 was stuck:wander '4' at this same arrival board.
        key = loops.decide(policy, board)
        self.assertIn(policy.last_reason, WALK, key)
        self.assertGreaterEqual(policy._stuck_escape_streak, STUCK_ESCAPE_LIMIT)


if __name__ == "__main__":
    unittest.main()
