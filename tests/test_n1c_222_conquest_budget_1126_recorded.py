"""The conquest target's budget and the Angband gate (2026-11-26, n1-c life-222's Mountain 50F).

Supervisor 2026-11-26, under the owner's leave of the same day 「…いずれも、ゲーム内選択に関して私の
以前の指示を破ることを許可する。」, narrowing the owner's 2026-11-19 「行き先を変えるのはダンジョンの主
討伐のみとする」 (angband_hold): no conquest while the held character's real blocker is an Angband
depth gate (angband_hold ``depth_gated``), and each target has a budget (conquest_budget: six trips
to its last floor, or two dives that met its guardian and fled or declined it; two given-up targets
end the conquests of the life).

Recorded: n1-c life-222 (Zombie Magic-Eater Lv45, Angband recall landing 80, the 81F speed +25 gate
missing) recalled 119 times to the Mountain 50F for 大鷲王『ソロンドール』 (race 468) from
2026-11-25 07:40 to 15:05.  The town board kept is the one of turn 6754081, back from one of those
trips (tests/fixtures/n1c-222-conquest-budget-1126.json.gz,
tests/extract_n1c_222_conquest_budget_1126_fixture.py); the Mountain 50F boards are the same
capture's (tests/fixtures/n1c-222-destruction-approach-1125.jsonl.gz): its arrival (6850301,
the guardian not shown) and a board showing the guardian (6851521).

DECLARED CONSTRUCTED: Angband's landing lowered to 49 (``at_49``) stands for a character the
Angband gate rule does not hold, so the budget itself is driven; ``last_reason`` set to an
emergency teleport stands for the escape decided on the board that showed the guardian (the live
13:19:55 ``emergency:teleport`` beside him); the given-up dungeons of the last test are written
into the budget.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import gzip
import io
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import angband_hold, conquest_budget
from hengbot.me_device_attacks import observe_lists
from hengbot.model import DUNGEON_ANGBAND, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "n1c-222-conquest-budget-1126.json.gz", "rt", encoding="utf-8") as _stream:
    TOWN = json.load(_stream)
with gzip.open(FIXTURES / "n1c-222-destruction-approach-1125.jsonl.gz", "rt",
               encoding="utf-8") as _stream:
    MOUNTAIN = {raw["turn"]: raw for raw in map(json.loads, _stream)}
LISTS = json.loads((FIXTURES / "n1c-222-me-lists-1125.json").read_text(encoding="utf-8"))["lists"]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

MOUNTAIN_ID = 14
THORONDOR = 468
ARRIVAL = 6850301  # the Mountain 50F arrival, the guardian not shown
SHOWN = 6851521  # the guardian shown by telepathy


def at_49(board):
    """DECLARED CONSTRUCTED (the module docstring): Angband's landing 49."""
    return replace(board, recall_depth=49,
                   dungeon_recall_depths={**board.dungeon_recall_depths, DUNGEON_ANGBAND: 49})


class N1c222ConquestBudgetTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.record_path = Path(self.scratch.name) / conquest_budget.FILE_NAME

    def policy(self):
        policy = _policy(Path(self.scratch.name), MONRACE)
        policy._conquest_ledger_record_path = self.record_path
        for kind in ("staff", "wand", "rod"):
            listed = dict(copy.deepcopy(TOWN), turn=TOWN["turn"] - 1,
                          _magic_eater_power_list={"kind": kind, "rows": LISTS[kind]})
            observe_lists(policy, parse_snapshot(listed, MONRACE))
        return policy

    def board(self, raw, *, held=True):
        board = parse_snapshot(copy.deepcopy(raw), MONRACE)
        return board if held else at_49(board)

    def observe(self, policy, raw, *, held=True):
        board = self.board(raw, held=held)
        with contextlib.redirect_stdout(io.StringIO()):
            policy._observe(board)
        return board

    def trip(self, policy, *, shown=False, fled=False):
        """Town, the Mountain 50F arrival (and a board showing the guardian), town."""
        self.observe(policy, TOWN, held=False)
        self.assertEqual(policy._target_dungeon_id, MOUNTAIN_ID)
        self.observe(policy, MOUNTAIN[ARRIVAL], held=False)
        if shown:
            self.observe(policy, MOUNTAIN[SHOWN], held=False)
            if fled:
                policy.last_reason = "emergency:teleport"
                self.observe(policy, MOUNTAIN[SHOWN], held=False)
        self.observe(policy, TOWN, held=False)

    def test_the_recorded_town_board(self):
        policy = self.policy()
        board = self.board(TOWN)
        self.assertTrue(board.in_town)
        self.assertNotIn(MOUNTAIN_ID, board.conquered_dungeon_ids)
        self.assertTrue(angband_hold.held(policy, board))
        self.assertEqual(policy._dungeon_entry_depth(board, DUNGEON_ANGBAND, via_recall=True), 80)
        self.assertEqual(policy._missing_required_abilities(board, 81, owned=True),
                         frozenset({"speed+25"}))
        self.assertTrue(angband_hold.depth_gated(policy, board))
        self.assertIn(THORONDOR, {monster.race_id for monster in
                                  self.board(MOUNTAIN[SHOWN]).detected_monsters
                                  + self.board(MOUNTAIN[SHOWN]).visible_monsters})

    def test_the_live_conquest_without_the_gate_rule(self):
        policy = self.policy()
        with mock.patch.object(angband_hold, "depth_gated", lambda *_args: False):
            self.observe(policy, TOWN)
        self.assertEqual((policy._target_dungeon_id, policy._target_dungeon_reason),
                         (MOUNTAIN_ID, "conquest"))

    def test_no_conquest_while_the_angband_gate_holds(self):
        policy = self.policy()
        policy._conquest_committed = MOUNTAIN_ID  # the live latch

        self.observe(policy, TOWN)

        # Before: the Mountain (conquest), recalled to 119 times.
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertIsNone(policy._conquest_committed)

    def test_six_trips_give_the_target_up(self):
        policy = self.policy()
        for _ in range(conquest_budget.TRIP_LIMIT - 1):
            self.trip(policy)
        self.assertFalse(conquest_budget.given_up(policy, MOUNTAIN_ID))
        self.trip(policy)

        # Before: the Mountain again, trip after trip.
        self.assertTrue(conquest_budget.given_up(policy, MOUNTAIN_ID))
        self.observe(policy, TOWN, held=False)
        self.assertNotEqual(policy._target_dungeon_id, MOUNTAIN_ID)
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertIsNone(policy._conquest_target(self.board(TOWN, held=False)))

    def test_the_budget_survives_a_restart(self):
        policy = self.policy()
        for _ in range(conquest_budget.TRIP_LIMIT):
            self.trip(policy)
        self.assertTrue(conquest_budget.given_up(policy, MOUNTAIN_ID))

        restarted = self.policy()
        self.observe(restarted, TOWN, held=False)

        # Before: a fresh process forgot every trip and took the Mountain again.
        self.assertTrue(conquest_budget.given_up(restarted, MOUNTAIN_ID))
        self.assertNotEqual(restarted._target_dungeon_id, MOUNTAIN_ID)

    def test_a_trip_that_only_saw_the_guardian_is_one_trip(self):
        policy = self.policy()
        self.trip(policy, shown=True)
        budget = conquest_budget.state(policy)
        self.assertEqual(budget["trips"], {str(MOUNTAIN_ID): 1})
        self.assertEqual(budget["met"], {})

    def test_two_dives_that_fled_the_guardian_give_the_target_up(self):
        policy = self.policy()
        self.trip(policy, shown=True, fled=True)
        self.assertFalse(conquest_budget.given_up(policy, MOUNTAIN_ID))
        self.observe(policy, TOWN, held=False)
        self.observe(policy, MOUNTAIN[ARRIVAL], held=False)
        self.observe(policy, MOUNTAIN[SHOWN], held=False)
        policy.last_reason = "emergency:teleport"
        self.observe(policy, MOUNTAIN[SHOWN], held=False)

        # Given up at the second flight, before the dive ends.
        self.assertTrue(conquest_budget.given_up(policy, MOUNTAIN_ID))
        self.assertEqual(conquest_budget.state(policy)["met"], {str(MOUNTAIN_ID): 2})
        self.observe(policy, TOWN, held=False)
        self.assertNotEqual(policy._target_dungeon_id, MOUNTAIN_ID)

    def test_two_given_up_targets_end_the_conquests(self):
        policy = self.policy()
        conquest_budget.state(policy)["given_up"].extend([3, 7])  # DECLARED CONSTRUCTED
        self.assertTrue(conquest_budget.refuses_new(policy))
        self.observe(policy, TOWN, held=False)
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)

        # One given up: another target (the Mountain) may still be taken.
        self.record_path.unlink()  # a life of its own
        policy = self.policy()
        conquest_budget.state(policy)["given_up"].append(3)
        self.observe(policy, TOWN, held=False)
        self.assertEqual(policy._target_dungeon_id, MOUNTAIN_ID)


if __name__ == "__main__":
    unittest.main()
