"""Quest 25 on n1-b life-416 (2026-11-23 00:50-01:19): the sweep held on a quylthulg no stand could shoot, recorded.

n1-b life-416 (Magic-Eater Lv39) on Quest 25 『幽霊屋敷』, the plan's sweep (battle phase 8,
phase6_sweep).  Turn 2507372 killed the first Nexus quylthulg (480) on the north corridor; turn
2507389 cast the absorbed Rod of Detection (``me-power:quest25-sweep:detect-all``) from [8,21] and
the board of turn 2507392 showed the second one, lightly wounded, on [8,3] -- the sealed pocket of
the map's 『Z』 (rows 6-9, columns 2-5: permanent walls and the granite [9,3]).  No walk reaches it,
so the sweep asked the pocket's plan (quest25_pocket, owner 2026-11-15 「溶かして撃つ・無ければ帰還」).
The plan looked only for a stand beside the granite with a line of fire to the target: from
[10,2] the line to [8,3] crosses the permanent [9,2], [10,3]/[10,4]/[9,4] are permanent, the rest
lie inside the pocket.  No plan, so the sweep held (``quest-strategy:hold`` '5') on [8,21] for
90,000 game turns until the server's ``stall:floor-dwell:quest-strategy:hold`` (turn 2598087).

The fix (quest25_pocket ``plan`` / ``fire_cell``): a target no line from the stand reaches is shot
from the melted wall's own cell -- the stand melts [9,3], the player steps onto it and shoots [8,3]
beside it.  The sweep no longer counts the melted cell beside the target as a reach (quest25_battle
``_sweep_reachable``), so the pocket's plan keeps the shot.  Where no wall opens a line from either
cell the hold had no end (owner 2026-11-19 「来ないなら待ち続けない」): the named stop
``quest:blocked:quest25-sealed-pocket-no-line``.

Recorded: tests/fixtures/n1b-416-q25-sealed-hold-1123.json.gz
(tests/extract_n1b_416_q25_sealed_hold_1123_fixture.py): the boards and decisions of turns
2507060-2507600 and 2597900-2598087 and the battle record at the stop.  A fresh policy restores the
record through the real path and decides through the public ``choose_key``.

DECLARED RECONSTRUCTED: the remembered magic-eater lists (the boards do not carry them): the rows of
tests/test_n1c_211_q25_sealed_quylthulg_1115_recorded.lists, with the absorbed Stone to Mud (岩石溶解;
the process cast it as ``mBg`` at turn 2432163 on Castle 64F) or, where a test says so, without it.
DECLARED CONSTRUCTED: the player moved to the stand [10,2] or onto [9,3]; [9,3] drawn as floor after
the melt (the board's own floor palette, row [10,1]) or as a permanent wall (the control).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_pocket as pocket
from hengbot.model import parse_snapshot
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS
from tests import test_n1c_211_q25_absent_wait_1115_recorded as wait
from tests.test_n1c_211_q25_sealed_quylthulg_1115_recorded import lists

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-416-q25-sealed-hold-1123.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

geo = battle.geo
DETECTED = 2507392       # the board after the sweep's detection: the quylthulg on [8,3]
STOP = 2598087           # the server's stall stop
TARGET, GRANITE, STAND = (8, 3), (9, 3), (10, 2)
FLOOR_PALETTE = 1        # the board's palette row of the floor [10,1]-[10,2]
PERMANENT_PALETTE = 0    # the board's palette row of the permanent walls [9,2], [10,3]
# By value as well, so the test fails by assertion on the code before the fix.
STEP_IN = getattr(pocket, "STEP_IN_REASON", "quest25:step-into-melted")
NO_LINE = getattr(pocket, "NO_LINE_REASON", "quest:blocked:quest25-sealed-pocket-no-line")


def board(turn):
    return copy.deepcopy(next(raw for raw in CASE["window"]["boards"] if raw["turn"] == turn))


def recorded(turn):
    return [(row["reason"], row["key"]) for row in CASE["window"]["decisions"] if row["turn"] == turn]


def at(raw, cell):
    """DECLARED CONSTRUCTED: the player on ``cell``."""
    moved = copy.deepcopy(raw)
    moved["player"] = dict(moved["player"], y=cell[0], x=cell[1])
    return moved


def drawn(raw, cell, palette):
    """DECLARED CONSTRUCTED: ``cell`` drawn with the board's palette row ``palette``."""
    moved = copy.deepcopy(raw)
    runs = moved["grid_map"]["runs"]
    index = next(i for i, run in enumerate(runs) if run[:3] == [cell[0], cell[1], 1])
    runs[index] = [cell[0], cell[1], 1, palette]
    return moved


def later(raw, steps):
    """DECLARED CONSTRUCTED: the next board of the sequence (the turn moved on, no messages)."""
    moved = copy.deepcopy(raw)
    moved["turn"] = raw["turn"] + steps
    moved["messages"] = []
    return moved


def new_policy(directory, raw, *, stone_to_mud=True):
    record = dict(CASE["battle_record"], turn=raw["turn"])
    policy = wait.new_policy(Path(directory), record, raw)
    policy._me_device_lists = lists(stone_to_mud=stone_to_mud)   # DECLARED RECONSTRUCTED
    return policy


def ctx_of(policy, raw):
    return battle._ctx(policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))


class TheRecordingTest(unittest.TestCase):

    def test_the_detection_showed_the_quylthulg_in_the_pocket_and_the_sweep_held(self):
        self.assertEqual(recorded(DETECTED - 3), [("me-power:quest25-sweep:detect-all", "mCg")])
        self.assertEqual(recorded(DETECTED), [("quest-strategy:hold", "5")])
        shown = [(m["race_id"], m["y"], m["x"]) for m in board(DETECTED)["detected_monsters"]]
        self.assertIn((geo.QUYL, *TARGET), shown)
        record = CASE["battle_record"]["battle"]
        self.assertEqual(battle.PHASE_NAMES[record["phase"]], "sweep")
        self.assertEqual(record["detected"], {"tuple": [{"tuple": list(TARGET)}]})
        self.assertIsNone(record["pocket"])
        self.assertEqual(dict(record["kills"]["dict"])[geo.QUYL], 1)
        self.assertEqual(recorded(STOP - 7), [("quest-strategy:hold", "5")])
        stop = board(STOP)
        self.assertEqual((stop["player"]["y"], stop["player"]["x"]), (8, 21))

    def test_no_stand_beside_the_granite_has_a_line_but_the_melted_cell_does(self):
        raw = board(STOP)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            ctx = ctx_of(policy, raw)
            self.assertFalse(battle._sweep_reachable(ctx, TARGET))
            opened = {**ctx.open_terrain(), GRANITE: "floor"}
            self.assertFalse(pocket.quest_exposure.projectable(opened, STAND, TARGET))
            self.assertEqual(pocket.plan(ctx, TARGET), (GRANITE, STAND))
            self.assertEqual(getattr(pocket, "fire_cell", lambda *_: STAND)(ctx, TARGET, GRANITE, STAND), GRANITE)


class TheMeltStepInAndShotTest(unittest.TestCase):

    def test_the_stop_board_walks_to_the_stand(self):
        raw = board(STOP)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            key = wait.decide_past_reads(policy, raw)
            self.assertEqual(policy.last_reason, pocket.WALK_REASON)
            self.assertIn(key, tuple("12346789"))
            self.assertEqual(wait.fight(policy).pocket, (TARGET, GRANITE, STAND))

    def test_without_stone_to_mud_the_stop_board_reads_recall(self):
        raw = board(STOP)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw, stone_to_mud=False)
            key = wait.decide_past_reads(policy, raw)
            self.assertEqual(policy.last_reason, pocket.RECALL_REASON)
            self.assertTrue(key.startswith("r"), key)

    def test_on_the_stand_the_granite_is_melted(self):
        raw = at(board(STOP), STAND)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            key = wait.decide_past_reads(policy, raw)
            self.assertEqual((key, policy.last_reason), ("mBg@9,3", battle.MELT_REASON))

    def test_melted_the_player_steps_onto_the_melted_cell(self):
        raw = drawn(at(board(STOP), STAND), GRANITE, FLOOR_PALETTE)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            key = wait.decide_past_reads(policy, raw)
            self.assertEqual((key, policy.last_reason), ("9", STEP_IN))

    def test_one_policy_walks_melts_steps_in_and_shoots(self):
        """The sequence on one policy: the stop board, the stand, the melt drawn, the melted cell."""
        stop = board(STOP)
        steps = (
            (stop, pocket.WALK_REASON),
            (later(at(stop, STAND), 10), battle.MELT_REASON),
            (later(drawn(at(stop, STAND), GRANITE, FLOOR_PALETTE), 20), STEP_IN),
        )
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, stop)
            for raw, reason in steps:
                key = wait.decide_past_reads(policy, raw)
                self.assertEqual(policy.last_reason, reason, key)
                policy.confirm_key_posted(key)
            raw = later(drawn(at(stop, GRANITE), GRANITE, FLOOR_PALETTE), 30)
            key = wait.decide_past_reads(policy, raw)
            self.assertTrue(key.endswith("@8,3"), (key, policy.last_reason))
            self.assertEqual(wait.fight(policy).pocket, (TARGET, GRANITE, STAND))


class ControlTest(unittest.TestCase):

    def test_control_no_wall_opens_a_line_is_a_named_stop(self):
        """DECLARED CONSTRUCTED: [9,3] drawn as a permanent wall: no melt opens the pocket."""
        raw = drawn(board(STOP), GRANITE, PERMANENT_PALETTE)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            key = wait.decide_past_reads(policy, raw)
            self.assertIsNone(pocket.plan(ctx_of(policy, raw), TARGET))
            self.assertEqual((key, policy.last_reason), ("5", NO_LINE))
        self.assertIn(NO_LINE, POLICY_FINAL_STOP_REASONS)


if __name__ == "__main__":
    unittest.main()
