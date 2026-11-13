"""n1-b life-393: the Anaguma walk into a quartz vein (2026-11-14).

life-393 (Magic-Eater Lv 37, dungeon 20 45F, 01:40, loop-detected): at (7,185) the Anaguma
plan for a pack of race 272 put its start at (4,182) and its cells up the column to row 0 --
the floor's edge, a permanent wall (floor/cave-generator.cpp make_perm_walls) -- and beyond
(rows -1 to -4) on grids the board did not show, presumed rock.  On the walk the room showed
open floor where the cells were to be dug, and a *Destruction* at (5,183) turned the start into
a quartz vein; the plan was never checked again and ``anaguma:walk`` sent '7' into the vein
twelve times (「石英の鉱脈が行く手をはばんでいる。」) until the loop guard stopped the bot.

The fixes: no tunnel cell lies on or beyond the floor's edge (``anaguma_geometry.interior``),
and on the walk to the start a plan the board no longer fits is released and planned again
from the board (``anaguma._site_lost``).

Recorded (tests/fixtures/n1b-393-394-1114/anaguma-walk-393.json.xz, see
tests/extract_n1b_393_394_1114_fixtures.py): the 18 player-turn boards from turn 3224944, their
decision rows, the absorption record and the plan held at the stop, decided by the public
``choose_key``; the stop board's key is posted through the production decision send and
executor (``_ExecutorInputPort``).

DECLARED RECONSTRUCTED (as test_anaguma_walk_loop_1111_recorded): the skill reply and the
absorbed wand list the process remembered.  The replay after the plan's first walk differs from
the record (it does not see its own keys done); the plans and their keys are compared, and the
stop is decided from the plan held at the stop.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import anaguma, anaguma_geometry as geo, me_capability
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, FaithfulHookGame, ProductionHarness, _policy, command_screen
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-393-394-1114"
STUCK = Position(5, 183)
START = Position(4, 182)
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
DETECT_EVIL = me_capability.names("staff", 15)[0]


def _plan(raw) -> anaguma.Plan:
    tunnel = raw["tunnel"]
    return anaguma.Plan(
        tuple(raw["floor"]),
        geo.Zigzag(Position(*tunnel["start"]), tuple(tunnel["axis"]), tunnel["side"],
                   tuple(Position(*cell) for cell in tunnel["cells"])),
        raw["length"], raw["minimum"], raw["animal"], frozenset(raw["races"]),
        phase=raw["phase"], contact_turn=raw["contact_turn"])


class AnagumaWalk393RecordedTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(lzma.decompress(
            (FIXTURES / "anaguma-walk-393.json.xz").read_bytes()).decode("utf-8", "surrogateescape"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def board(self, raw):
        return parse_snapshot(raw, self.monrace)

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

    def decide(self, policy, board):
        key = policy.choose_key(policy.with_known_skill_exp(board))
        return key, policy.last_reason

    def stop(self):
        """The stop's board decided with the plan held at the stop (the record's policy state)."""
        policy = self.policy()
        self.decide(policy, self.board(self.data["boards"][-2]))
        setattr(policy, anaguma.MEMORY, _plan(self.data["stop_plan"]))
        last = self.data["boards"][-1]
        return (policy, last) + self.decide(policy, self.board(last))

    def post(self, policy, raw, key, screens):
        """``key`` through the production decision send (cli._send_new_decision_key) and the
        executor; the game's accepted keys."""
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [*screens, command_screen(raw["turn"] + 10)]
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=self.board(copy.deepcopy(raw)), posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(port.last_result.outcome, "completed", port.last_result.reason)
        return game.accepted

    # ------------------------------------------------------------ the record

    def test_the_record_walks_into_the_vein_at_the_stop(self):
        walks = [row for row in self.data["decisions"]
                 if row["reason"] == anaguma.REASON_WALK and row["position"] == {"y": 5, "x": 183}]
        self.assertGreaterEqual(len(walks), 12)
        self.assertTrue(all(row["key"] == "7" for row in walks))
        plan = _plan(self.data["stop_plan"])
        self.assertEqual((plan.phase, plan.tunnel.start), ("walk", START))
        self.assertIn(Position(0, 181), plan.cells)                 # the floor's edge
        self.assertTrue(any(cell.y < 0 for cell in plan.tunnel.cells))  # beyond it
        last = self.board(self.data["boards"][-1])
        self.assertEqual(last.player.position, STUCK)
        self.assertFalse(last.grid_at(START).passable)              # the quartz vein

    # ------------------------------------------------------------ the pins

    def test_a_plan_never_digs_on_or_beyond_the_floor_edge(self):
        """The plan made at (7,185) keeps every cell inside the edge."""
        policy = self.policy()
        plans = []
        for raw in self.data["boards"]:
            board = self.board(raw)
            self.decide(policy, board)
            current = anaguma.plan(policy)
            if current is not None:
                plans.append((board, current.tunnel))
        self.assertTrue(plans)
        for board, tunnel in plans:
            for cell in tunnel.cells:
                self.assertTrue(0 < cell.y < board.height - 1 and 0 < cell.x < board.width - 1,
                                (board.turn, tunnel))

    def test_the_replay_does_not_walk_into_the_vein(self):
        policy = self.policy()
        rows = []
        for raw in self.data["boards"]:
            board = self.board(raw)
            rows.append((board.player.position,) + self.decide(policy, board))
        self.assertFalse([row for row in rows if row[0] == STUCK and row[2] == anaguma.REASON_WALK], rows)

    def test_the_plan_held_at_the_stop_is_released_and_not_walked(self):
        """The stop's plan on the stop's board: its start is a vein, so it is released, and the
        board is not answered with the walk into it."""
        policy, raw, key, reason = self.stop()
        last = self.board(raw)
        self.assertEqual(policy._anaguma_last_release, anaguma.SITE_LOST)
        self.assertNotEqual(reason, anaguma.REASON_WALK)
        current = anaguma.plan(policy)
        if current is not None:  # planned again from this board: an open start inside the edge
            self.assertTrue(geo.open_cell(last.grid_at(current.tunnel.start)))
            self.assertIsNotNone(geo.zigzag(last, current.tunnel.start, current.tunnel.axis,
                                            current.tunnel.side, current.length))

    def test_the_stop_board_reaches_the_game_through_the_executor(self):
        """After the release the stop's board is answered with the floor's first Detect Evil
        (the absorbed staff, letter p), which the production executor completes; no '7'."""
        policy, raw, key, reason = self.stop()
        self.assertEqual((reason, key), ("me-power:new-floor:detect-evil", "mAp"))
        accepted = self.post(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("staff", [("p", DETECT_EVIL, 14, 14, 5)])])
        self.assertEqual(accepted, ["m", "A", "p"])


if __name__ == "__main__":
    unittest.main()
