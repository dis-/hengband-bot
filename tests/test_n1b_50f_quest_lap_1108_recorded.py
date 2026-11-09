"""n1-b life-348, Angband 50F, RANDOM quest 40 (『黄衣の王』, race 735), 2026-11-08 14:5x-15:42.

Owner 2026-11-08: 「n1-b loopを調べて」「現在50Fでループ中」.

Recorded (tests/extract_n1b_50f_quest_lap_1108_fixture.py): the floor's arrival boards (game turn
3034110 on) show the explore walking to the two closed doors south of the start room, (34,127)
and (34,130), and six 'o' answered "鍵をはずせなかった。" (3034281-3034336; DOOR_OPEN_LIMIT
writes a door off after three), eight searches at (33,129), and from 3034339 the
``quest-search:loop`` circuit over (25..31, 132..154).  The decision tail (15:28:56-15:42) is
6,204 ``quest-search:loop`` rows on that circuit.  The ledger's magic mappings (29,133) and
(26,162), radius 30, leave every walkable grid of the start side explored; the rest of the
floor's frontiers (47 on the replayed board) lie past the two locks (exe_open: a failed pick is
the 2% floor at worst, action/open-close-execution.cpp).

DECLARED CONSTRUCTED: the player's walk (the player moved as the key says, the board otherwise
the same; a door stays closed), the answer to each pick (the recorded "鍵をはずせなかった。",
"中断しました。" of 3034281, or the stuck answer or none where a test says so), the ledger
installed on the policy, and the bound patched small in the bound test.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import hengbot.policy  # noqa: F401 -- loads the modules in their cycle-safe order
from hengbot import locked_doors
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.exploration_ledger import ExplorationLedger
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy
from tests.support import recorded
from tests.support.recorded import FaithfulHookGame, command_screen

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-50f-quest-lap-1108.json.xz"
DOORS = {(34, 127), (34, 130)}
LOOP, PICK, SEEK = "quest-search:loop", locked_doors.PICK_REASON, locked_doors.SEEK_REASON
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1),
         "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
STUCK_ANSWER = ["ドアはがっちりと閉じられているようだ。"]


def _pin():
    return json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))


class N1b50fQuestLapRecordedTest(recorded.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.pin = _pin()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.answer = next(row["messages"] for row in cls.pin["arrival"] if row["turn"] == 3034281)

    def policy(self, at=None):
        raw = copy.deepcopy(self.pin["board"])
        if at is not None:
            raw["player"]["y"], raw["player"]["x"] = at
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        ledger = Path(directory.name) / "exploration-ledger.json"
        ledger.write_text(json.dumps(self.pin["ledger"]), encoding="utf-8")
        policy._exploration_ledger = ExplorationLedger(ledger)  # DECLARED: the live ledger
        policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy, raw

    def choose(self, policy, raw):
        return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))

    def following(self, raw, key, answer=None, reason=None):
        """The board after ``key``; ``answer`` is the reply to an 'o' (the recorded one by
        default), or a callable of the decision's reason that returns it."""
        board = copy.deepcopy(raw)
        board["turn"] += 10
        board["messages"] = []
        if key.startswith("o"):
            reply = answer(reason) if callable(answer) else answer
            board["messages"] = list(self.answer if reply is None else reply)
        elif key in MOVES:
            board["player"]["y"] += MOVES[key][0]
            board["player"]["x"] += MOVES[key][1]
        return board

    def run_board(self, policy, raw, decisions, answer=None):
        """(position, key, reason) of each decision, the board after the last."""
        rows = []
        for _ in range(decisions):
            key = self.choose(policy, raw)
            rows.append(((raw["player"]["y"], raw["player"]["x"]), key, policy.last_reason))
            raw = self.following(raw, key, answer, policy.last_reason)
        return rows, raw

    def post(self, policy, raw, key):
        following = self.following(raw, key)
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                             "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), key)

    # -- the recording -------------------------------------------------------

    def test_recorded_lap_after_five_failed_picks(self):
        floor = self.pin["board"]["floor"]
        self.assertEqual((floor["dungeon_id"], floor["level"], floor["quest_id"], floor["width"]),
                         (1, 50, 40, 198))
        picks = [(row["y"], row["x"]) for row in self.pin["arrival"]
                 if "鍵をはずせなかった。" in row["messages"]]
        self.assertEqual(picks, [(33, 128)] * 3 + [(33, 129)] * 3)
        reasons = [row["reason"] for row in self.pin["decisions"]]
        self.assertEqual(reasons.count(LOOP), 6204)
        self.assertLessEqual(set(reasons), {
            LOOP, "me-power:hunt-target-unseen:detect-all:powerful", "survival:mana-absorb"})
        cells = {(row["position"]["y"], row["position"]["x"]) for row in self.pin["decisions"]}
        self.assertTrue(all(25 <= y <= 31 and 132 <= x <= 154 for y, x in cells), cells)
        self.assertEqual(self.pin["ledger"]["mapped_areas"], [[26, 162, 30], [29, 133, 30]])

    # -- the fix -------------------------------------------------------------

    def test_written_off_locks_are_picked_not_lapped(self):
        """The explore's three picks a door, then the search keeps picking (revert: the lap)."""
        policy, raw = self.policy(at=(33, 130))
        rows, raw = self.run_board(policy, raw, 30)
        explore_picks = [(at, key) for at, key, reason in rows if reason == "explore" and key[0] == "o"]
        self.assertEqual(explore_picks, [((33, 130), "o2")] * 3 + [((33, 128), "o1")] * 3)
        self.assertEqual(policy._blocked_doors, DOORS)
        reasons = [reason for _, _, reason in rows]
        self.assertNotIn(LOOP, reasons)
        self.assertEqual(rows[-1], ((33, 128), "o1", PICK))
        # Every later pick was answered "failed to pick the lock": only the first counts (the
        # board before it answered a search).
        self.assertEqual(getattr(policy, locked_doors.MEMORY).unanswered, {(34, 127): 1})
        key = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("o1", PICK))
        self.post(policy, raw, key)

    def test_the_recorded_lap_board_walks_to_the_lock(self):
        """On the recorded last board, once both locks are written off, the walk goes south."""
        policy, raw = self.policy(at=(33, 130))
        _, _ = self.run_board(policy, raw, 8)  # the explore's picks write both doors off
        self.assertEqual(policy._blocked_doors, DOORS)
        raw = copy.deepcopy(self.pin["board"])  # back on the recorded board, (27,142)
        raw["turn"] += 1000
        # DECLARED: the walk back is not replayed, so its cells are not in the recent window
        # (two cells in it read as an oscillation, whose searches answer first).
        policy._recent.clear()
        rows, raw = self.run_board(policy, raw, 14)
        self.assertEqual({reason for _, _, reason in rows[:-1]}, {SEEK})
        self.assertEqual(rows[-1][1:], ("o2", PICK))
        self.assertEqual(rows[-1][0], (33, 130))

    def test_stuck_doors_are_left_to_the_lap(self):
        policy, raw = self.policy(at=(33, 130))
        rows, _ = self.run_board(policy, raw, 30, answer=STUCK_ANSWER)
        self.assertEqual(policy._blocked_doors, DOORS)
        self.assertEqual(locked_doors.stuck(policy, parse_snapshot(copy.deepcopy(raw), self.monrace)), DOORS)
        reasons = [reason for _, _, reason in rows]
        self.assertNotIn(PICK, reasons)
        self.assertIn(LOOP, reasons)

    def test_a_door_never_answered_as_a_lock_is_left_to_the_lap(self):
        """An 'o' the game gave no answer to shows no lock: the cap stands (the sealed pocket
        test boards answer so)."""
        policy, raw = self.policy(at=(33, 130))
        rows, _ = self.run_board(policy, raw, 30, answer=[])
        self.assertEqual(policy._blocked_doors, DOORS)
        reasons = [reason for _, _, reason in rows]
        self.assertNotIn(PICK, reasons)
        self.assertIn(LOOP, reasons)

    def test_unanswered_picks_end_at_the_bound(self):
        policy, raw = self.policy(at=(33, 130))
        # The explore's picks are answered as recorded; the search's picks get no answer.
        with mock.patch.object(locked_doors, "QUEST_SEARCH_DOOR_PICK_LIMIT", 2):
            rows, _ = self.run_board(policy, raw, 50,
                                     answer=lambda reason: [] if reason == PICK else None)
        picks = [(at, key) for at, key, reason in rows if reason == PICK]
        self.assertEqual(sorted(set(picks)), [((33, 128), "o1"), ((33, 129), "o3")])
        self.assertEqual(len(picks), 4)
        self.assertEqual(getattr(policy, locked_doors.MEMORY).unanswered, {(34, 127): 2, (34, 130): 2})
        last_pick = max(index for index, (_, _, reason) in enumerate(rows) if reason == PICK)
        self.assertTrue(rows[last_pick + 1:])
        self.assertNotIn(PICK, {reason for _, _, reason in rows[last_pick + 1:]})


if __name__ == "__main__":
    unittest.main()
