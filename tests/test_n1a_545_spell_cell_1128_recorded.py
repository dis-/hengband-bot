"""A caster's Teleport Away aimed at a cell answers its direction prompt (n1-a life-545, 1128).

n1-a life-545 (Amberite Rogue CL42, Sorcery, HP 865/865) waited for recall on Angband 90F with its
*Destruction* spent; 『邪神ヘレッコス』 (race 1419), awake and known only by detection, stood at
(33,111).  The SENSED_THREAT occasion (me_powers.sensed_threat_key, owner 2026-11-22 「撃つ」) chose
the Sorcery Teleport Away ``mbe@32,110`` (``realm-spell:sensed-t1-in-line:teleport-away``): the
beam aimed at the cell (32,110), whose line passes the monster (me_powers.beam_cell).  The
caster's cast key had no ``@y,x`` form (realm_spells_input._CAST_KEY), so no menu use compiled
it, and the executor stopped at the game's direction prompt with
``stuck-prompt ... ctx=direction ... reason=unowned direction`` (2026-11-28 19:53:09).

The game (target/target-getter.cpp:69-100 get_aim_dir): ``*`` starts target_set; a monster is
targeted only when target_able (target/target-preparation.cpp:34-59: shown and projectable), ``p``
moves to the free mode at the player (target/target-setter.cpp:323-334), where ``t`` makes any
grid the target (:476-490; a grid target is always okay, target/target.cpp:32-35).  The Sorcery
Teleport Away (realm/realm-sorcery.cpp:205-219) fires fire_beam(AWAY_ALL) through project_hook,
which adds PROJECT_THRU (spell-kind/spells-launcher.cpp:224-228,262-267): the beam runs past the
aimed cell, as the Magic-Eater's absorbed Teleport Away's (the device walk me_device_attacks_input
``aim_or_target`` / ``walk_to_goal``, which the caster's cast now shares).

Recorded (tests/extract_n1a_545_spell_cell_1128_fixture.py, ``n1a-545-spell-cell-1128``): the
player-turn boards 8259778-8259826 of that 90F floor, the latest ``spell_list`` of each book before
them, and the stop's control screen (the direction prompt).  Replayed through ``choose_key`` from
a fresh production policy (partial state: the window's remembered map and memories only; the
replay posts no key to a game, so the floor memory never sees a cast's outcome).

DECLARED CONSTRUCTED: the game model of the executor test (the book and spell questions, the
target prompt's screens and its cursor moves, and the command screen after the cast), written from
the source lines above; the direction prompt is the recorded screen.
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_powers, realm_spells
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor
from hengbot.me_menu_uses import compile_menu_key
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_KEYS
from tests.support import recorded as input_tests
from tests.support.recorded import EDIT, _policy
from test_magic_eater_o3 import prompt

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-spell-cell-1128.jsonl.xz"
STOP = 8259826                    # the board the live bot decided ``mbe@32,110`` on
LIVE_KEY = "mbe@32,110"
REASON = "realm-spell:sensed-t1-in-line:teleport-away"
SENSED = Position(33, 111)        # 『邪神ヘレッコス』, awake, detected only
AIMED = (32, 110)
TARGET_GUIDE = "[q止 t決 p自 m近 +次 -前]"
MOVES = {key: delta for delta, key in DIRECTION_KEYS.items()}


def _rows():
    lines = lzma.decompress(FIXTURE.read_bytes()).decode("utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


class CellCastGame(input_tests.FaithfulHookGame):
    """do_cmd_cast's key reads for the Sorcery book in slot ``b`` and its spell ``e``, then
    get_aim_dir and target_set (the source lines of the module docstring), one key at a time."""

    capacity = 256

    def __init__(self, board, direction_screen):
        super().__init__()
        self.state, self.direction_screen = board, direction_screen
        self.player = (board["player"]["y"], board["player"]["x"])
        self.mode, self.cursor, self.free, self.target = "command", None, False, None
        self.screen = self.render()

    def key(self, char):
        if self.mode == "command":
            if char != "m":
                raise AssertionError(f"not a cast: {char!r}")
            self.mode = "book"
        elif self.mode == "book":
            if char != "b":
                raise AssertionError(f"book {char!r}")
            self.mode = "spell"
        elif self.mode == "spell":
            if char != "e":
                raise AssertionError(f"spell {char!r}")
            self.mode = "aim"
        elif self.mode == "aim":
            # target-getter.cpp:89-97: only '*' (or ' ', '\r') starts target_set here: no target
            # is set, so '5'/'t' ring the bell; a digit fires along its direction.
            if char != "*":
                raise AssertionError(f"direction answer {char!r}")
            self.mode, self.cursor, self.free = "target", self.player, False
        elif self.mode == "target":
            if char == "p":
                self.cursor, self.free = self.player, True
            elif char == "t" and self.free:
                self.target, self.mode = self.cursor, "command"
                self.state = dict(self.state, turn=self.state["turn"] + 1)
                self.jsonl.append(dict(self.state))
            elif char in MOVES and self.free:
                dy, dx = MOVES[char]
                self.cursor = (self.cursor[0] + dy, self.cursor[1] + dx)
            else:
                raise AssertionError(f"target answer {char!r} (free={self.free})")

    def render(self):
        if self.mode == "command":
            return input_tests.command_screen(self.state["turn"])
        if self.mode == "book":
            return prompt("どの呪文書を使いますか?", "item", area="inventory", areas=["inventory"],
                          first_label="a", last_label="b", menu=False)
        if self.mode == "spell":
            screen = prompt("(呪文:a-h, '*'で一覧, ESCで中断) どの呪文を唱えますか?", "spell",
                            browse=False, first_label="a", last_label="h", list=True, menu=False)
            screen["lines"][2] = "  e) テレポート・アウェイ      [初] 23   12  15% 距離:42"
            return screen
        if self.mode == "aim":
            return copy.deepcopy(self.direction_screen)
        return prompt(TARGET_GUIDE, "target", look=False, free=self.free, can_target=True,
                      y=self.cursor[0], x=self.cursor[1])

    def _consume(self, *, pump_frontend=True):
        if pump_frontend and self.frontend_fifo:
            self.term_fifo.extend(self.frontend_fifo)
            self.frontend_fifo.clear()
        if not self.term_fifo:
            return
        raw = "".join(self.term_fifo)
        self.term_fifo.clear()
        for char in raw:
            self.key(char)
        self.screen = self.render()


class N1a545SpellCell1128RecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        rows = _rows()
        cls.lists = [row for row in rows if row.get("type") == "spell_list"]
        cls.boards = [row for row in rows if row.get("type") == "player_turn"]
        cls.direction = next(row["screen"] for row in rows if row.get("type") == "control_screen")
        cls.scratch = TemporaryDirectory()
        cls.decided = cls.replay()

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    @classmethod
    def replay(cls):
        """(key, reason, policy, board) of the stop board, the window replayed through choose_key
        with each spell_list handed to realm_spells.observe_list as cli does."""
        policy = _policy(Path(cls.scratch.name), cls.monrace)
        first = parse_snapshot(copy.deepcopy(cls.boards[0]), cls.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        for row in _rows():
            if row.get("type") == "spell_list":
                realm_spells.observe_list(policy, dict(row))
                continue
            if row.get("type") != "player_turn":
                continue
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(row), cls.monrace))
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            if row["turn"] == STOP:
                return key, policy.last_reason, policy, board
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError("the stop board is not in the fixture")

    def port(self, game):
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        return _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)

    # -- the decision: the same key as live, aimed at a cell whose line passes the monster ------

    def test_the_recorded_board_decides_the_cell_cast(self):
        key, reason, policy, board = self.decided
        self.assertEqual((key, reason), (LIVE_KEY, REASON))
        detected = next(monster for monster in board.detected_monsters
                        if monster.position == SENSED)
        self.assertFalse(detected.asleep)
        self.assertEqual(me_powers.beam_cell(policy, board, board.player.position, SENSED),
                         Position(*AIMED))

    def test_the_cast_key_compiles_with_its_cell(self):
        key, reason, _policy_, _board_ = self.decided
        plan = compile_menu_key(key, reason)
        self.assertIsNotNone(plan, "no menu use owns the caster's cell cast")
        prefix, steps = plan
        self.assertEqual((prefix, steps[0].book, steps[0].letter, steps[0].goal),
                         ("m", "b", "e", AIMED))

    # -- the executor: the recorded direction prompt is answered and the cell targeted ---------

    def test_the_executor_answers_the_recorded_direction_prompt(self):
        key, reason, _policy_, _board_ = self.decided
        board = next(row for row in self.boards if row["turn"] == STOP)
        self.assertEqual(self.direction["input_context"]["kind"], "direction")
        game = CellCastGame(copy.deepcopy(board), self.direction)
        port = self.port(game)
        status = port(key, decision={"reason": reason, "sequence": 1})
        self.assertEqual(status, SendResult.SENT, port.last_result.reason)
        receipt = port.executor.ready_board["_completed_operation_receipt"]
        self.assertIsNone(receipt.get("refusal"))
        # From the player (36,115) to (32,110): '*', 'p' to the free mode, four up-left, one left.
        self.assertEqual(game.accepted, ["m", "b", "e", "*", "p", "7", "7", "7", "7", "4", "t"])
        self.assertEqual(game.target, AIMED)
        self.assertEqual(game.state["turn"], STOP + 1)


if __name__ == "__main__":
    unittest.main()
