"""A character one floor past the 81F speed gate recalls to Angband and works 80F (n1-b life-419).

Recorded (tests/extract_n1b_419_speed_ceiling_1127_fixture.py, ``n1b-419-speed-ceiling-1127``):
the town-arrival checkpoint of 2026-11-27 12:26:11 (Zombie Magic-Eater CL50, HP 1128, permanent
speed +17, gold 60,015).  Angband's saved recall depth was 81 (a Teleport Level from 80F), so the
81F row's speed +25 refused every Angband recall: row 10 stepped off for
town:unsafe-recall-fallback and row 40 read Word of Recall to the Castle (``rgf``), as all 221
recalls between 2026-11-26 13:20 and 11-27 12:37 went to the Mountain 50F or the Castle 64-65F.
With the speed ceiling (angband_cap, supervisor 2026-11-27) row 40 reads Word of Recall to Angband
(``rga``).  Since owner 2026-11-28 (「80Fから90Fまでは危険度に大きな変化はない。80Fで足りなければもう少し
深く潜っても良い。」) the +25 row starts at 91F: the cap is 90F, the saved 81 is an admitted landing
(the 70F row's +10, met by the permanent +17), and the 91F landing is the one climbed from.

Rows 0-9 replay the recorded keys (full state).  Row 10 decides the departure's character dump
the recorded row 11 posted, so from row 11 the recorded boards trail the new decisions by one
row (partial state); rows 12-39 still post the recorded keys.

DECLARED CONSTRUCTED: ``test_the_landing_floor_is_climbed_from`` moves the row-40 board onto
Angband 90F-92F (``floor_key`` and the town flag only), and the ceiling's constants and the reset answer are read
on their own.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_cap, angband_hold, deep_climb
from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import SPEED_GATE_DEPTH, SPEED_GATE_LABEL, SPEED_GATE_LABELS
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-419-speed-ceiling-1127"
FALLBACK_ROW = 10
FALLBACK = ("7", "town:entrance-step-off:town:unsafe-recall-fallback")
DUMP = ("Cf\ry\x1b\x1b", "town:character-dump")
RECALL_ROW = 40
RECORDED_RECALL = ("rgf", "town:recall-to-alt-dungeon")
ANGBAND_RECALL = ("rga", "town:recall-to-angband")


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class SpeedCeiling419RecordedTest(unittest.TestCase):
    def replay(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, journal, steps = load(FIXTURE, Path(scratch.name))
        self.assertEqual((journal[FALLBACK_ROW]["key"], journal[FALLBACK_ROW]["reason"]), FALLBACK)
        self.assertEqual((journal[RECALL_ROW]["key"], journal[RECALL_ROW]["reason"]),
                         RECORDED_RECALL)
        decided = []
        for recorded, supply in steps[:RECALL_ROW]:
            row = recorded["row"]
            key, reason = decide(policy, supply())
            if row < FALLBACK_ROW or row > FALLBACK_ROW + 1:
                self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), row)
            decided.append((row, key, reason))
            post(policy, key)
        board = steps[RECALL_ROW][1]()
        return policy, board, decided

    def test_the_departure_recalls_to_angband(self):
        policy, board, decided = self.replay()
        self.assertEqual(decided[FALLBACK_ROW][1:], DUMP)
        self.assertEqual(decided[FALLBACK_ROW + 1][2], "depart:inn-refill:destruction:approach")
        self.assertFalse([row for row in decided if "unsafe-recall-fallback" in row[2]])
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 81)
        self.assertEqual(decide(policy, board), ANGBAND_RECALL)
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertEqual(angband_cap.cap(DUNGEON_ANGBAND, policy), 90)
        self.assertTrue(policy._recall_destination_safe(board, DUNGEON_ANGBAND))

    def test_no_lord_hunt_while_the_ceiling_holds(self):
        policy, board, _decided = self.replay()
        # The saved 81 lies under the 90F ceiling since owner 2026-11-28; the ceiling holding the
        # character keeps it depth-gated (supervisor 2026-11-28), as the 80F ceiling did.
        self.assertTrue(angband_hold.depth_gated(policy, board))
        self.assertIsNone(policy._conquest_target(board))

    def test_the_landing_floor_is_climbed_from(self):
        policy, board, _decided = self.replay()
        angband_cap.observe(policy, board)
        for depth in (91, 92):
            floor = replace(board, floor_key=(DUNGEON_ANGBAND, depth, 0), town_flag=False)
            self.assertTrue(angband_cap.climbing(floor, policy), depth)
            gaps = policy._missing_required_abilities(floor, depth)
            self.assertIn(SPEED_GATE_LABEL, gaps)
            # On 91F the speed gap starts no town return (the climb answers it); deeper floors
            # keep it (the ordinary resist-gap return).
            self.assertEqual(bool(deep_climb.floor_gaps(policy, floor, gaps) & SPEED_GATE_LABELS),
                             depth > 91, depth)
        for depth in (81, 85):
            floor = replace(board, floor_key=(DUNGEON_ANGBAND, depth, 0), town_flag=False)
            self.assertFalse(angband_cap.climbing(floor, policy), depth)
            self.assertFalse(policy._missing_required_abilities(floor, depth) & SPEED_GATE_LABELS,
                             depth)
        ceiling = replace(board, floor_key=(DUNGEON_ANGBAND, 90, 0), town_flag=False)
        self.assertFalse(angband_cap.climbing(ceiling, policy))
        self.assertTrue(angband_cap.capped(ceiling, 91, policy))
        # Only the landing one floor past the ceiling is admitted: 92 keeps its gap.
        self.assertFalse(angband_cap.landing_gaps(
            policy, board, DUNGEON_ANGBAND, 91, {SPEED_GATE_LABEL}))
        self.assertEqual(angband_cap.landing_gaps(
            policy, board, DUNGEON_ANGBAND, 92, {SPEED_GATE_LABEL}), {SPEED_GATE_LABEL})
        # A stair down from the dungeon keeps its gap (town only).
        self.assertEqual(angband_cap.landing_gaps(
            policy, ceiling, DUNGEON_ANGBAND, 91, {SPEED_GATE_LABEL}), {SPEED_GATE_LABEL})


class SpeedCeilingConstantsTest(unittest.TestCase):
    def test_the_ring_of_speed_is_made_under_the_ceiling(self):
        # Owner 2026-11-28: the ceiling (90F) is below the ring's allocation depth (80F), so the
        # hunt floors 80-90F lie above it (angband_cap.ring_hunt_floor).
        self.assertEqual(SPEED_GATE_DEPTH, 91)
        self.assertLessEqual(angband_cap.RING_OF_SPEED_DEPTH, SPEED_GATE_DEPTH - 1)

    def test_recall_on_the_ceiling_floor_resets_the_saved_depth(self):
        def board(level, saved):
            return {"floor": {"dungeon_id": DUNGEON_ANGBAND, "level": level, "quest_id": 0},
                    "progress": {"dungeon_recall_depths": {str(DUNGEON_ANGBAND): saved}}}
        self.assertTrue(angband_cap.reset_recall_depth(board(90, 91), deepest=90))
        self.assertFalse(angband_cap.reset_recall_depth(board(89, 91), deepest=90))
        self.assertFalse(angband_cap.reset_recall_depth(board(90, 90), deepest=90))
        self.assertFalse(angband_cap.reset_recall_depth(board(90, 91)))
        self.assertFalse(angband_cap.reset_recall_depth(board(90, 91), lifted=True, deepest=90))


if __name__ == "__main__":
    unittest.main()
