"""n1-c life-140, random quest 40 (鉄獄50階), 2026-11-05 05:41: sealed in rock.

*Destruction* at (19,98) left the player two floor cells (19,97)-(19,98) with rock
on every other side.  The oscillation guard found no way out and set the
navigation exhausted, and the ladder skipped everything on a quest floor, so
every restart ended in livelock:exhausted within 25 decisions with 9 Scrolls of
Teleportation and a Stone to Mud wand (36 charges) in the pack.

Owner 2026-11-05: 「*破壊*後全方位壁なら岩石溶解で脱出すれば良い」: the wand is the way out
(sealed_pocket); Teleportation stays the fallback.

Recorded: the last restart's state rows and decisions
(tests/extract_sealed_pocket_quest_1105_fixture.py).
DECLARED CONSTRUCTED: the pack without the wand; the wand's item prompt, direction prompt
and next board; the melted grid; the permanent rock around; the absorbed power's list.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import sealed_pocket
from hengbot.cli import PostingContract, _ExecutorInputPort, _consume_response_sequence, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SEARCH_LIMIT
from tests.support.recorded import EDIT, _policy
from tests import test_input_executor as executor_pins
from tests.test_me_device_attacks import power_list, row

FIXTURE = Path(__file__).with_name("fixtures") / "sealed-pocket-quest-1105.json.xz"
STOP_TURN = 3971127
READ_PROMPT = "(持ち物:a-z, ESCで中断) どの巻物を読みますか?"
AIM_PROMPT = "(持ち物:a-z, ESCで中断) どの魔法棒で狙いますか? "
DIRECTION_PROMPT = "方向 ('*'でターゲット選択, ESCで中止)? "
POCKET = ((19, 97), (19, 98))
READ_TELEPORT = "rh"  # the recorded pack: h) 9 Scrolls of Teleportation
WAND_SLOT = "l"       # the recorded pack: l) 岩石溶解の魔法棒 (36回分)
TELEPORT_SLOT = "h"
FLOOR_TERRAIN_ROW = [1, 2, 416, 1]  # the board's palette row of a floor grid (terrain 1)
PERMANENT_TERRAIN_ID = 60


def _pin():
    return json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))


def _without_wand(line: str) -> str:
    raw = json.loads(line)
    raw["inventory"] = [item for item in raw["inventory"] if item["sval"] != 6 or item["tval"] != 65]
    for slot, item in zip("abcdefghijklmnopqrstuvwxyz", raw["inventory"]):
        item["slot"] = slot
    return json.dumps(raw, ensure_ascii=False)


def _cell_set(raw, cells, palette_row):
    """The board with ``cells`` of the run-length map set to ``palette_row``."""
    grid_map = raw["grid_map"]
    palette = grid_map["palette"]
    index = palette.index(palette_row) if palette_row in palette else len(palette)
    if index == len(palette):
        palette.append(palette_row)
    runs = []
    for y, x0, length, value in grid_map["runs"]:
        for x in range(x0, x0 + length):
            runs.append([y, x, 1, index if (y, x) in cells else value])
    known = {(y, x) for y, x, _, _ in runs}
    runs += [[y, x, 1, index] for y, x in cells if (y, x) not in known]
    grid_map["runs"] = runs
    return raw


class SealedPocketQuestRecordedTest(executor_pins.ProductionHarness):
    def _replay(self, lines, *, stop_only=False):
        """The recorded restart through choose_key: (policy, last board, last key, per-turn rows)."""
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        policy = _policy(root, monrace)
        policy._crossarea_fundraising_enforced = True  # live argv
        policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
        turns = {}
        for line in lines:
            turns.setdefault(json.loads(line)["turn"], []).append(line)
        skill = next(json.loads(line) for line in lines if '"skill_exp"' in line)
        first = min(turns)
        rows, board, key = {}, None, None
        for turn, segment in sorted(turns.items()):
            if stop_only and turn not in (first, STOP_TURN):
                continue
            _, boards = _consume_response_sequence(
                segment, policy, lambda _key: True, monrace,
                knowledge_ledger_path=root / "knowledge.jsonl")
            board = boards[-1]
            if turn == first:
                policy.prime(board)
                # DECLARED: the ledger sidecar the live restart reloaded; the earlier
                # rows (turns 3969886-3970441) visited each of the two cells and
                # searched it 8 times.
                for y, x in POCKET:
                    policy._search_counts[(y, x)] = SEARCH_LIMIT
                    policy._visit_counts[Position(y, x)] = 2
                # The session's first row asked for the skill list on this board.
                self.assertTrue(policy.choose_key(board).startswith("~f"))
            policy.consume_skill_knowledge({**skill, "player": {"level": board.player.level}})
            board = policy.with_known_skill_exp(board)
            if stop_only and turn == first:
                continue
            key = policy.choose_key(board)
            rows[turn] = (key, policy.last_reason)
        return policy, board, key, rows

    def _send(self, raw_board, policy, board, key, prompts):
        game = executor_pins.FaithfulHookGame()
        game.state = raw_board
        game.screen = executor_pins.command_screen(raw_board["turn"])
        # DECLARED CONSTRUCTED: the prompts and the next board after the command.
        game.screens = [*(executor_pins.prompt_screen(text) for text in prompts),
                        executor_pins.command_screen(raw_board["turn"] + 10)]
        game.states = [dict(raw_board, turn=raw_board["turn"] + 10)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual("".join(game.accepted), key)

    def test_the_stop_board_aims_stone_to_mud(self):
        pin = _pin()
        policy, board, key, _ = self._replay(pin["lines"], stop_only=True)
        self.assertEqual(board.floor_key, (1, 50, 40))
        self.assertEqual(board.player.position, Position(19, 98))
        self.assertEqual(policy.last_reason, sealed_pocket.REASON)
        # Up-left: the line with the fewest grids to known floor that leads on (11 to (7,86)).
        self.assertEqual(key, "a" + WAND_SLOT + "7")
        self.assertFalse(policy._nav_exhausted)
        self._send(json.loads(pin["lines"][-1]), policy, board, key, [AIM_PROMPT, DIRECTION_PROMPT])

    def test_the_exhausted_ladder_melts_before_it_reads_away(self):
        pin = _pin()
        policy, board, _, _ = self._replay(pin["lines"], stop_only=True)
        policy._nav_exhausted = True
        key = policy._navigation_livelock_key(board)
        self.assertEqual(policy.last_reason, sealed_pocket.REASON)
        self.assertEqual(key[:2], "a" + WAND_SLOT)
        self.assertFalse(policy._nav_exhausted)

    def test_the_line_to_known_floor_beats_fewer_walls_to_unknown_ground(self):
        pin = _pin()
        policy, board, _, _ = self._replay(pin["lines"], stop_only=True)
        raw = json.loads(pin["lines"][-1])
        granite = next(entry for entry in raw["grid_map"]["palette"] if entry[0] == 56)
        # DECLARED CONSTRUCTED: two walls to the right, then floor with unknown ground around it.
        _cell_set(raw, {(19, 100)}, granite)
        _cell_set(raw, {(19, 101)}, FLOOR_TERRAIN_ROW)
        policy._sealed_pocket_memory = None
        self.assertEqual(sealed_pocket.key(policy, parse_snapshot(raw)), "a" + WAND_SLOT + "6")

    def test_the_stuck_escape_melts_before_it_leaves_the_floor(self):
        pin = _pin()
        policy, board, _, _ = self._replay(pin["lines"], stop_only=True)
        self.assertEqual(policy._stuck_escape_key(board), "a" + WAND_SLOT + "7")
        self.assertEqual(policy.last_reason, sealed_pocket.REASON)

    def test_with_no_device_the_pocket_is_left_by_teleport(self):
        pin = _pin()
        lines = [_without_wand(line) if '"grid_map"' in line else line for line in pin["lines"]]
        policy, board, key, rows = self._replay(lines)
        recorded = {row["turn"]: row for row in pin["decisions"]}
        for turn, decided in rows.items():
            if turn != STOP_TURN:
                # Without the wand only the stop board is decided differently.
                self.assertEqual(decided, (recorded[turn]["key"], recorded[turn]["reason"]), turn)
        self.assertEqual(policy.last_reason, "livelock:teleport-explore")
        self.assertEqual(key, "r" + TELEPORT_SLOT)
        self.assertFalse(policy._nav_exhausted)
        raw_board = json.loads(lines[-1])
        self._send(raw_board, policy, board, key, [READ_PROMPT])

    def test_a_wall_that_stayed_is_left_and_only_permanent_rock_falls_through(self):
        pin = _pin()
        policy, board, key, _ = self._replay(pin["lines"], stop_only=True)
        aimed = {key}
        # The same board again and again: every line is left after its uses, then none answers.
        for _ in range(8 * 5):
            again = sealed_pocket.key(policy, board)
            if again is None:
                break
            aimed.add(again)
        self.assertIsNone(sealed_pocket.key(policy, board))
        self.assertGreater(len(aimed), 1)

        raw = json.loads(pin["lines"][-1])
        palette = raw["grid_map"]["palette"]
        permanent = next(entry for entry in palette if entry[0] == PERMANENT_TERRAIN_ID)
        around = {(y, x) for y in (18, 19, 20) for x in range(96, 100)} - set(POCKET)
        walled = parse_snapshot(_cell_set(copy.deepcopy(raw), around, permanent))
        self.assertIsNotNone(sealed_pocket.sealed_region(policy, walled))
        policy._sealed_pocket_memory = None
        self.assertIsNone(sealed_pocket.key(policy, walled))

    def test_one_melted_wall_hands_the_floor_back_to_exploration(self):
        pin = _pin()
        policy, board, key, _ = self._replay(pin["lines"], stop_only=True)
        direction = int(key[2:])
        offset = {1: (1, -1), 2: (1, 0), 3: (1, 1), 4: (0, -1), 6: (0, 1), 7: (-1, -1), 8: (-1, 0), 9: (-1, 1)}[direction]
        opened = (19 + offset[0], 98 + offset[1])
        raw = json.loads(pin["lines"][-1])
        raw["turn"] += 10
        melted = parse_snapshot(_cell_set(raw, {opened}, FLOOR_TERRAIN_ROW))
        self.assertTrue(melted.grid_at(Position(*opened)).passable)
        self.assertIsNone(sealed_pocket.sealed_region(policy, melted))
        step = policy.choose_key(melted)
        self.assertEqual(step, str(direction), policy.last_reason)
        self.assertNotEqual(policy.last_reason, sealed_pocket.REASON)

    def test_the_absorbed_power_melts_where_no_wand_is_held(self):
        pin = _pin()
        lines = [_without_wand(line) if '"grid_map"' in line else line for line in pin["lines"]]
        policy, board, _, _ = self._replay(lines, stop_only=True)
        # DECLARED CONSTRUCTED: the displayed absorbed list holds Stone to Mud (wand sval 6).
        policy._me_device_lists = {"wand": (board.turn, tuple(power_list(
            "wand", row("岩石溶解", 5, current=5, count=5))["rows"]))}
        policy._sealed_pocket_memory = None
        policy._nav_exhausted = True
        key = policy._navigation_livelock_key(board)
        self.assertEqual(policy.last_reason, sealed_pocket.REASON + ":absorbed-power")
        self.assertEqual(key, "mBg7")
