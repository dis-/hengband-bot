"""Executor answers of a caster's cast, study and browse (realm_spells_input, owner 2026-11-26).

Each key goes through the production executor (``_ExecutorInputPort`` over ``OperationExecutor``)
into a model of cmd-action/cmd-spell.cpp for the keys it reads.  The questions and messages are
the live capture's (2026-11-26, a private headless game with the Golem Rogue template):
「どの呪文書を使いますか?」 / 「どの本から学びますか?」 / 「どの本を読みますか?」 as item questions
(``kind: item``, the book's slot as first/last label), the spell question
「(呪文:a-h, '*'で一覧, ESCで中断) どの呪文を唱えますか?」 (``kind: spell``, ``list: true`` with
always_show_list), 「その呪文を唱えるのに十分なマジックポイントがない。」, 「<name>の呪文を学んだ。」.
The failure 「呪文をうまく唱えられなかった！」 and the re-asked study question are the source's
(cmd-spell.cpp:1054, :495).

DECLARED CONSTRUCTED: the game model (one book in slot ``a``; which letters are learnable, fail
or ask a direction), the boards it writes.
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from tests.support import recorded as input_tests
from test_magic_eater_o3 import prompt
from test_spectator_me_powers import raw_board
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor
from hengbot import realm_spells_input
from hengbot.realm_spell_book import BROWSE_REASON, STUDY_REASON

BOOK_PROMPTS = {"m": "どの呪文書を使いますか?", "G": "どの本から学びますか?", "b": "どの本を読みますか?"}
SPELL_PROMPTS = {"m": "(呪文:a-h, '*'で一覧, ESCで中断) どの呪文を唱えますか?",
                 "G": "(呪文:a-h, '*'で一覧, ESCで中断) どの呪文を学びますか?",
                 "b": "(呪文:a-h, '*'で一覧, ESCで中断) どの呪文を読みますか?"}


class SpellGame(input_tests.FaithfulHookGame):
    """do_cmd_cast / do_cmd_study / do_cmd_browse's key reads, one key at a time."""

    capacity = 256

    def __init__(self, *, fails=(), aimed=(), learnable=("c",), mana_short=()):
        super().__init__()
        self.fails, self.aimed, self.learnable, self.mana_short = fails, aimed, learnable, mana_short
        self.mode, self.command, self.message, self.energy_use = "command", None, "", 0
        raw = raw_board(3, turn=5000)
        raw["player"] = dict(raw["player"], y=10, x=10)
        self.state = raw
        self.screen = self.render()

    def key(self, char):
        if self.mode == "command":
            if char not in BOOK_PROMPTS:
                raise AssertionError(f"not a spell command: {char!r}")
            self.command, self.mode, self.message, self.energy_use = char, "book", "", 0
        elif self.mode == "book":
            if char == "\x1b":
                self.mode = "command"
            elif char != "a":
                raise AssertionError(f"book {char!r} not offered")
            else:
                self.mode = "spell"
        elif self.mode == "spell":
            if char == "\x1b":
                self.mode = "command"
            elif self.command == "b":
                raise AssertionError(f"browse answer {char!r}")
            elif self.command == "G":
                if char in self.learnable:
                    self.message, self.mode, self.energy_use = "罠と扉感知の呪文を学んだ。", "command", 100
                else:
                    self.message = "その呪文を学ぶことはできません。"   # get_spell asks again
            elif char in self.mana_short:
                self.message, self.mode = "その呪文を唱えるのに十分なマジックポイントがない。", "command"
            elif char in self.aimed:
                self.mode = "aim"
            else:
                self.message = "呪文をうまく唱えられなかった！" if char in self.fails else ""
                self.mode, self.energy_use = "command", 100
        elif self.mode == "aim":
            if char not in "123456789":
                raise AssertionError(f"direction {char!r}")
            self.mode, self.energy_use = "command", 100

    def render(self):
        if self.mode == "command":
            screen = input_tests.command_screen(self.state["turn"])
            screen["lines"][0] = self.message
            return screen
        if self.mode == "book":
            return prompt(BOOK_PROMPTS[self.command], "item", area="inventory",
                          areas=["inventory"], first_label="a", last_label="a", menu=False)
        if self.mode == "aim":
            return prompt("方向 ('*'でターゲット選択, ESCで中断)? ", "direction",
                          can_choose_target=True)
        screen = prompt(SPELL_PROMPTS[self.command], "spell", browse=self.command == "b",
                        first_label="a", last_label="h", list=True, menu=False)
        screen["lines"][1] = "     名前                    熟練度 Lv   MP 失率 効果"
        screen["lines"][2] = "  a) モンスター感知            [初]  2    2   9% 半径:30"
        if self.message:
            screen["lines"][0] = self.message
        return screen

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
        if self.mode == "command":
            self.state = dict(self.state, turn=self.state["turn"] + self.energy_use // 100)
            self.jsonl.append(dict(self.state))
        self.screen = self.render()


class SpellInputTest(unittest.TestCase):
    def port(self, game):
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        return _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)

    def send(self, game, key, reason):
        port = self.port(game)
        status = port(key, decision={"reason": reason, "sequence": 1})
        self.assertEqual(status, SendResult.SENT, port.last_result.reason)
        return port.executor.ready_board["_completed_operation_receipt"]

    def test_escape_cast_under_the_ladders_reason(self):
        game = SpellGame()
        receipt = self.send(game, "mab", "emergency:phase")
        self.assertEqual(game.accepted, ["m", "a", "b"])
        self.assertIsNone(receipt.get("refusal"))
        self.assertEqual(game.state["turn"], 5001)

    def test_failed_cast_is_a_failed_use(self):
        game = SpellGame(fails=("a",))
        receipt = self.send(game, "maa", "realm-spell:new-floor:detect-monsters")
        self.assertEqual(game.accepted, ["m", "a", "a"])
        self.assertEqual(receipt.get("refusal"), realm_spells_input.CAST_FAILED)

    def test_mana_short_cast_is_refused_without_a_turn(self):
        game = SpellGame(mana_short=("f",))
        receipt = self.send(game, "maf", "emergency:teleport")
        self.assertEqual(receipt.get("refusal"), realm_spells_input.CAST_REFUSED)
        self.assertEqual(game.state["turn"], 5000)

    def test_aimed_cast_sends_its_direction_at_the_direction_question(self):
        game = SpellGame(aimed=("e",))
        self.send(game, "mae6", "realm-spell:unbeatable-in-range:teleport-away")
        self.assertEqual(game.accepted, ["m", "a", "e", "6"])

    def test_study_and_a_refused_study_closed_with_escape(self):
        game = SpellGame()
        receipt = self.send(game, "Gac", STUDY_REASON)
        self.assertEqual((game.accepted, receipt.get("refusal")), (["G", "a", "c"], None))
        game = SpellGame(learnable=())
        receipt = self.send(game, "Gac", STUDY_REASON)
        self.assertEqual(game.accepted, ["G", "a", "c", "\x1b"])
        self.assertEqual(receipt.get("refusal"), realm_spells_input.STUDY_FAILED)

    def test_browse_shows_the_list_and_closes_it_without_a_turn(self):
        game = SpellGame()
        self.send(game, "ba", BROWSE_REASON)
        self.assertEqual(game.accepted, ["b", "a", "\x1b"])
        self.assertEqual(game.state["turn"], 5000)

    def test_study_and_browse_keys_need_their_reason(self):
        self.assertIsNone(realm_spells_input.compile_spell("Gac", "explore"))
        self.assertIsNone(realm_spells_input.compile_spell("ba", "explore"))
        # The Magic-Eater's keys name the kind in uppercase: never a caster's cast.
        self.assertIsNone(realm_spells_input.compile_spell("mAe", "me-power:new-floor:detect-evil"))


if __name__ == "__main__":
    unittest.main()
