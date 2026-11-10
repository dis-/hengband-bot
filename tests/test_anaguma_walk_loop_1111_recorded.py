"""Anaguma keeps a decision on its side (n1-b life-367, 2026-11-11).

n1-b life-367 (Magic-Eater Lv 42), オークの洞窟23階, among forest trolls (FRIENDS) stopped twice
with ``loop-detected`` (00:03:38 and 00:03:47) and was retired: ``anaguma:walk`` from (34,124)
to the plan's start (33,123), then ``seek-loot`` / ``explore`` / ``breakout:seek-frontier``
from (33,123) back to (34,124), twenty times.  The cause: a sleeping ghost yeek (PASS_WALL,
level 7) at (27,106) was detected only from (33,123).  There ``anaguma.key`` released the plan
for the wall-passer; one step back it was out of detection, and a new plan sent the player to
(33,123) again.

The fix (``anaguma._latched``, owner 2026-11-08 「脅威度の段は境に余裕を持たせる（一度決めた側に
固定）」): a wall-passer or runners reading holds its veto for ``RETRY_GAME_TURNS`` after it was
last true, and a plan released on a floor is not made again for the same pack within that
window.

Recorded (tests/fixtures/anaguma-walk-loop-20261111.json.gz, see
tests/extract_anaguma_walk_loop_1111_fixture.py): the 44 player-turn boards before the stop
(turns 5800295-5800471), their decision rows, the absorption record and the plan held at the
stop.  The boards are decided in order by one policy's public ``choose_key``.

DECLARED RECONSTRUCTED: the capture keeps no skill reply (as test_anaguma_recorded), and the
absorbed wand list the process remembered (the Stone to Mud row; the capture keeps the dig's
``anaguma:dig:absorbed-power`` casts but not the list the game displayed).  The utility
decisions (``me-power:...``) are not posted, so the replay's own differ (it does not see them
done); the Anaguma rows are compared.  DECLARED CONSTRUCTED: the boards without the ghost
yeek, a forest troll placed beside the player, the trolls shown afraid, and the turns moved.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import anaguma, me_capability
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "anaguma-walk-loop-20261111.json.gz"
GHOST_YEEK = 1404
FOREST_TROLL = 297
START = Position(33, 123)
BACK = Position(34, 124)


class AnagumaWalkLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def policy(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = self.board(self.data["boards"][0])
        policy.prime(first)
        # DECLARED RECONSTRUCTED (module docstring): the skill reply and the absorbed wand list.
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_staff_sequence = MeStaffSequence(absorbed=dict(self.data["absorbed"]))
        row = {"name": me_capability.names("wand", 6)[0], "current": 10, "max": 20, "fail": 5, "success": 95}
        policy._me_device_lists = {"wand": (first.turn, (row,))}
        return policy

    def board(self, raw, *, ghost=True):
        raw = copy.deepcopy(raw)
        if not ghost:  # DECLARED CONSTRUCTED: the ghost yeek gone
            for field in ("visible_monsters", "detected_monsters"):
                raw[field] = [m for m in raw[field] if m["race_id"] != GHOST_YEEK]
        return parse_snapshot(raw, self.monrace)

    def decide(self, policy, board):
        policy._anaguma_veto = None
        key = policy.choose_key(policy.with_known_skill_exp(board))
        return key, policy.last_reason

    def replay(self, *, ghost=True):
        policy = self.policy()
        return [(raw["turn"], self.board(raw).player.position) + self.decide(policy, self.board(raw, ghost=ghost))
                + (policy._anaguma_veto, anaguma.plan(policy) is not None)
                for raw in self.data["boards"]]

    # ------------------------------------------------------------ the record

    def test_the_record_alternates_walk_and_leave_with_the_ghost_seen_from_the_start_only(self):
        decided = [row for row in self.data["decisions"] if row["reason"] != "loop-detected"]
        walks = [row for row in decided if row["reason"] == anaguma.REASON_WALK]
        self.assertGreaterEqual(len(walks), 20)
        self.assertEqual(self.data["stop_plan"]["tunnel"]["start"], [START.y, START.x])
        self.assertEqual(self.data["stop_plan"]["phase"], "walk")
        for raw in self.data["boards"]:
            board = self.board(raw)
            ghosts = [m for m in board.detected_monsters if m.race_id == GHOST_YEEK]
            if board.player.position == START:
                self.assertEqual(len(ghosts), 1, raw["turn"])
                self.assertIn("PASS_WALL", self.monrace[GHOST_YEEK].flags)
            elif board.player.position == BACK:
                self.assertEqual(ghosts, [], raw["turn"])

    # ------------------------------------------------------------ the pins

    def test_the_replay_makes_no_plan_while_the_ghost_was_seen_in_the_window(self):
        rows = self.replay()
        self.assertFalse([row for row in rows if row[3].startswith("anaguma:")], rows)
        self.assertFalse([row for row in rows if row[5]], rows)
        back = [row for row in rows if row[1] == BACK and row[4] is not None]
        self.assertTrue(back)
        self.assertTrue(all(row[4] in ("wall-passer", "contact") for row in back), back)

    def test_a_released_plan_is_not_made_again_within_the_window(self):
        """A plan released for a real reason (a troll beside the player before the pocket,
        ``contact-before-pocket``) is not made again for the pack until ``RETRY_GAME_TURNS``
        have passed.  DECLARED CONSTRUCTED: the ghost gone, a troll placed beside the player,
        the turns moved."""
        policy = self.policy()
        free = [self.board(raw, ghost=False) for raw in self.data["boards"]]
        back = next(board for board in free[3:] if board.player.position == BACK)
        self.decide(policy, back)
        self.assertIsNotNone(anaguma.plan(policy))
        troll = next(m for m in back.detected_monsters if m.race_id == FOREST_TROLL and not m.asleep)
        beside = Position(BACK.y + 1, BACK.x)
        touched = replace(back, turn=back.turn + 4,
                          detected_monsters=[m for m in back.detected_monsters if m is not troll],
                          visible_monsters=[*back.visible_monsters,
                                            replace(troll, position=beside, distance=1, perception="direct")])
        self.decide(policy, touched)
        self.assertIsNone(anaguma.plan(policy))
        self.assertEqual(policy._anaguma_last_release, "contact-before-pocket")
        released = touched.turn
        for later, planned in ((4, False), (anaguma.RETRY_GAME_TURNS - 1, False), (anaguma.RETRY_GAME_TURNS, True)):
            with self.subTest(later=later):
                self.decide(policy, replace(back, turn=released + later))
                self.assertEqual(anaguma.plan(policy) is not None, planned)
                if not planned:
                    self.assertEqual(policy._anaguma_veto, "retry-window")

    def test_a_runners_reading_holds_its_side(self):
        """Afraid trolls run (monster-sweep-grid.cpp:47-49): no plan.  Their fear gone, the
        veto holds until ``RETRY_GAME_TURNS`` after the last afraid board.  DECLARED
        CONSTRUCTED: the ghost gone, every forest troll shown afraid, the turns moved."""
        policy = self.policy()
        free = [self.board(raw, ghost=False) for raw in self.data["boards"]]
        back = next(board for board in free[3:] if board.player.position == BACK)
        afraid = replace(back, detected_monsters=[
            replace(m, fearful=True) if m.race_id == FOREST_TROLL else m for m in back.detected_monsters])
        self.decide(policy, afraid)
        self.assertEqual(policy._anaguma_veto, "runners")
        for later, planned in ((10, False), (anaguma.RETRY_GAME_TURNS - 1, False), (anaguma.RETRY_GAME_TURNS, True)):
            with self.subTest(later=later):
                self.decide(policy, replace(back, turn=back.turn + later))
                self.assertEqual(anaguma.plan(policy) is not None, planned)
                if not planned:
                    self.assertEqual(policy._anaguma_veto, "runners")


if __name__ == "__main__":
    unittest.main()
