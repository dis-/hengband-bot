"""Quest 25 on n1-c life-211 (2026-11-15): the quylthulg in the sealed pocket, melted open and shot.

The sweep's detection (phase6_sweep, turn 4076115, tests/test_n1c_211_q25_sweep_hold_1115_recorded)
showed a Nexus quylthulg (480) on [7,4], the map's sealed pocket 『Z』: permanent walls and the
granite [9,3].  Owner 2026-11-15 (the answer to 「[9,3] を溶かして撃ってよいか、岩石溶解が無い時は
どうするか」): 「溶かして撃つ・無ければ帰還」.

The rule (quest25_pocket, asked by quest25_battle ``_sweep`` when every cell its detection showed is
one no walk reaches): from the map and the board, a wall known and not permanent with a standable
cell beside it a walk reaches, from which -- the wall melted -- a line of fire reaches the target
(on the shipped map: [9,3] from [10,2]); the walk there; Stone to Mud at the wall (the absorbed power
first, then a carried wand); then the shot at the cell as phase 3 shoots a quylthulg (owner
2026-11-06 「…倒すまたはショートテレポートさせるまで撃つ」), ten shots in a row with no hit, pain or
kill line (``pen_misses_to_escaped``, the owner's 「当たらない撃ちで補う」) meaning it moved, and the
sweep detects again.  With no Stone to Mud: Word of Recall under ``RECALL_REASON`` (the quest fails).

Recorded: the hold's board of turn 4076134 on [5,2] (tests/fixtures/n1c-211-q25-sweep-hold-1115.json.gz)
and the stop's record.  A fresh policy restores the record through the real path and decides through
the public ``choose_key``; the melt and the shot are posted through the production executor.

DECLARED RECONSTRUCTED: the remembered magic-eater lists (tests/test_n1c_208_q25_patrol_1115_recorded),
with the absorbed Stone to Mud (岩石溶解) where a test says so; the record's turn set to the board's.
DECLARED CONSTRUCTED (the case after the reachable quylthulg is gone, as the owner's question put it):
the record remembering [7,4] alone with one quylthulg counted killed; the player moved along the walk;
the board after the melt drawing [9,3] as the floor beside it (the recorded grid map's palette row 1,
[10,1]-[10,2]); the kind prompt, the power lists and the target cursor of cmd-magiceat.cpp and
target-setter.cpp (as tests/test_breeder_area_attack_1103_recorded builds them); the kill and miss
boards; the control without Stone to Mud.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_pocket as pocket
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.model import SV_WAND_STONE_TO_MUD, TVAL_WAND, parse_snapshot
from tests.support import recorded as harness
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests import test_n1c_208_q25_patrol_1115_recorded as life208
from tests import test_n1c_211_q25_absent_wait_1115_recorded as wait
from tests import test_n1c_211_q25_sweep_hold_1115_recorded as hold

geo = battle.geo
SEALED, GRANITE, STAND = (7, 4), (9, 3), (10, 2)
FLOOR_PALETTE = 1            # the recorded grid map's row of [10,1]-[10,2]
FREE_GUIDE = "q止 t決 p自 m近 +次 -前"   # target-setter.cpp:470 (free mode)
STONE_TO_MUD = "岩石溶解"


def lists(*, stone_to_mud=True):
    """DECLARED RECONSTRUCTED (module note)."""
    found = life208.lists()
    found["wand"] = (0, (life208._row(STONE_TO_MUD, current=5, max=5),) if stone_to_mud else ())
    return found


def at_stand(raw=None) -> dict:
    return hold.at(hold.board(hold.HELD_TURN) if raw is None else raw, STAND)


def melted(raw: dict) -> dict:
    """DECLARED CONSTRUCTED: [9,3] drawn as the floor (Stone to Mud leaves floor, KILL_WALL)."""
    board = copy.deepcopy(raw)
    runs = board["grid_map"]["runs"]
    index = next(i for i, run in enumerate(runs) if run[:3] == [GRANITE[0], GRANITE[1], 1])
    runs[index] = [GRANITE[0], GRANITE[1], 1, FLOOR_PALETTE]
    return board


def later(raw: dict, steps: int = 10, messages=()) -> dict:
    board = copy.deepcopy(raw)
    board["turn"] = raw["turn"] + steps
    board["messages"] = list(messages)
    return board


def without_wand(raw: dict) -> dict:
    board = copy.deepcopy(raw)
    board["inventory"] = [item for item in board["inventory"]
                          if (item.get("tval"), item.get("sval")) != (TVAL_WAND, SV_WAND_STONE_TO_MUD)]
    return board


def new_policy(directory, raw, *, device_lists=None, kills_quyl=1):
    fought = hold.record(raw["turn"], detected=(SEALED,))
    fought["battle"]["kills"]["dict"].append([geo.QUYL, kills_quyl])
    policy = wait.new_policy(Path(directory), fought, raw)
    policy._me_device_lists = lists() if device_lists is None else device_lists
    return policy


def decide(policy, raw):
    return wait.decide_past_reads(policy, raw)


def target(y, x):
    return prompt(f"[{FREE_GUIDE}]", "target", look=False, free=True, can_target=True, y=y, x=x)


class _Post(harness.ProductionHarness):

    def post_power(self, policy, raw, key, kind, rows, cursor, following):
        """An absorbed power aimed at a grid, through the executor's prompts (cmd-magiceat.cpp,
        target-setter.cpp's free mode with the published cursor ``cursor``, a list of cells)."""
        game = harness.FaithfulHookGame()
        game.capacity = 256
        game.state = copy.deepcopy(raw)
        game.screen = harness.command_screen(raw["turn"])
        game.screens = [prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"), power_screen(kind, rows),
                        prompt("方向?", "direction", can_choose_target=True),
                        *(target(*cell) for cell in cursor), harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed", port.last_result.reason)
        policy.confirm_key_posted(key)
        return game.accepted


class ThePocketPlanTest(unittest.TestCase):

    def test_the_board_shows_the_granite_and_the_plan_comes_from_the_map(self):
        raw = hold.board(hold.HELD_TURN)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            decide(policy, raw)
            ctx = battle._ctx(policy, snapshot)
            self.assertFalse(battle._sweep_reachable(ctx, SEALED))
            self.assertEqual(pocket.plan(ctx, SEALED), (GRANITE, STAND))
            for cell in ((9, 2), (8, 2), (6, 4), (7, 3), (7, 5)):     # the pocket's other walls
                self.assertFalse(pocket._granite(ctx, cell), cell)


class TheMeltAndShotTest(_Post):

    def test_from_the_hold_it_walks_to_the_stand(self):
        raw = hold.board(hold.HELD_TURN)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            key = decide(policy, raw)
            self.assertEqual((key, policy.last_reason), ("1", pocket.WALK_REASON))
            self.assertEqual(wait.fight(policy).pocket, (SEALED, GRANITE, STAND))

    def test_on_the_stand_the_absorbed_stone_to_mud_melts_the_granite(self):
        raw = at_stand()
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            key = decide(policy, raw)
            self.assertEqual((key, policy.last_reason), ("mBg@9,3", battle.MELT_REASON))
            accepted = self.post_power(policy, raw, key, "wand", [("g", STONE_TO_MUD, 5, 5, 5)],
                                       [STAND, GRANITE], melted(later(raw)))
            self.assertEqual(accepted, ["m", "B", "g", "*", "9", "t"])

    def test_without_the_absorbed_power_the_carried_wand_melts_it(self):
        raw = at_stand()
        wand = next(item for item in raw["inventory"]
                    if (item.get("tval"), item.get("sval")) == (TVAL_WAND, SV_WAND_STONE_TO_MUD))
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw, device_lists=lists(stone_to_mud=False))
            key = decide(policy, raw)
            self.assertEqual((key, policy.last_reason), ("a" + wand["slot"] + "*p9t5\x1b", battle.SHOT_REASON))

    def test_melted_the_quylthulgs_cell_is_shot_and_a_kill_is_counted(self):
        """The cell shot through the executor (the rod list, the cursor walk [10,2] -> [7,4]); the kill
        line counts the second quylthulg, the cell is done and the sweep's detection looks again."""
        raw = melted(at_stand())
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            key = decide(policy, raw)
            self.assertTrue(key.startswith("mC") and key.endswith("@7,4"), key)
            rows = [(chr(ord("a") + index), row["name"], 0, row["max"], 5)
                    for index, row in enumerate(lists()["rod"][1])]
            killed = later(raw, messages=["何かを倒した。"])
            accepted = self.post_power(policy, raw, key, "rod", rows, [STAND, (9, 3), (8, 4), SEALED], killed)
            # The executor answers the list's own letter for the power (アイス・ボール, row m).
            self.assertEqual(accepted[:4], ["m", "C", "m", "*"])
            self.assertEqual(accepted[-1], "t")
            key = decide(policy, killed)
            fight = wait.fight(policy)
            self.assertEqual(fight.kills.get(geo.QUYL), geo.ROSTER[geo.QUYL])
            self.assertIsNone(fight.pocket)
            self.assertEqual((key, policy.last_reason), ("mCg", f"{battle.DETECT_REASON}:detect-all"))

    def test_ten_unanswered_shots_mean_it_moved_and_the_sweep_detects_again(self):
        raw = melted(at_stand())
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw)
            board, key = raw, None
            for _shot in range(10):
                key = decide(policy, board)
                self.assertTrue(key.endswith("@7,4"), key)
                policy.confirm_key_posted(key)
                board = later(board)
            key = decide(policy, board)
            fight = wait.fight(policy)
            self.assertIsNone(fight.pocket)
            self.assertEqual((key, policy.last_reason), ("mCg", f"{battle.DETECT_REASON}:detect-all"))

    def test_without_stone_to_mud_it_reads_recall(self):
        raw = without_wand(at_stand())
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw, device_lists=lists(stone_to_mud=False))
            key = decide(policy, raw)
            self.assertEqual(policy.last_reason, pocket.RECALL_REASON)
            self.assertTrue(key.startswith("r"), key)

    def test_control_a_reachable_quylthulg_is_walked_to_not_melted_for(self):
        """DECLARED CONSTRUCTED: the record remembering [1,15] beside [7,4] (the 09:25 case)."""
        raw = hold.board(hold.HELD_TURN)
        fought = hold.record(raw["turn"], detected=(SEALED, hold.OPEN))
        with TemporaryDirectory() as directory:
            policy = wait.new_policy(Path(directory), fought, raw)
            policy._me_device_lists = lists()
            key = decide(policy, raw)
            self.assertEqual((key, policy.last_reason), ("7", battle.WALK_REASON))
            self.assertIsNone(wait.fight(policy).pocket)


if __name__ == "__main__":
    unittest.main()
