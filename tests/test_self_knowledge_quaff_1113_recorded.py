"""The Potions of Self Knowledge and *Enlightenment* are drunk (self-knowledge-quaff-1113).

Owner 2026-11-13 「自己分析の薬を飲む処理が効いてない」: the owner's table
(consumable_policy.json) marks both 「拾って使う」, but USE_UNSUPPORTED kept them out of
the stat-gain quaff because the self-knowledge viewer the quaff opens had no input owner.

Recorded input ``n1c-205-self-knowledge-1113.jsonl.gz``
(tests/extract_n1c_205_self_knowledge_1113_fixture.py): n1-c life-205 carried a
自己分析の薬 (75/58) from turn 2238669 for 2048 boards with no visible monster and never
drank it.
  dungeon/1270  Angband 62F, turn 2239207, slot g; the recorded bot answered ``7`` explore.
  town/3537     the Outpost, turn 2250815, slot i; the recorded bot answered ``3``
                shop:approach.

The viewer (view/display-self-info.cpp display_self_info): screen_save, the heading
prt() at row 1, x=15, 20 entries a page, "-- more --" at x=15 and the closing prompt at
x=13, each read by input_key_with_context(InputKind::ANY_KEY).  *Enlightenment* first
msg_erase()s its message (quaff-effects.cpp star_enlightenment).

DECLARED CONSTRUCTED (named again where built): the viewer screens (source-derived, no
recorded capture exists: no bot ever drank one); the awake enemy, blindness and
confusion of the refusal boards; the *Enlightenment* (75/57) put in the recorded slot;
the consumable-policy-1102 dungeon board's slot b holding the potion.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import consumable_policy
from hengbot.cli import _consume_response_sequence
from hengbot.input_context import InputContextReading, compatible_kinds
from hengbot.input_executor import Continuation, Operation, ScreenKind, classify_screen
from hengbot.model import TVAL_POTION
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import recorded as _recorded
from tests.support.recorded import EDIT, _policy, command_screen, prompt_screen

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "n1c-205-self-knowledge-1113.jsonl.gz"
TABLE_FIXTURE = FIXTURES / "consumable-policy-20261102.jsonl.gz"
SELF_KNOWLEDGE, STAR_ENLIGHTENMENT = 58, 57
REASON = "stat-gain:self-knowledge"
# DECLARED CONSTRUCTED: an awake enemy in view, two grids away.
MONSTER = {"index": 77, "race_id": 24, "hp": 10, "max_hp": 10, "distance": 2, "friendly": False,
           "pet": False, "speed": 110, "name": "enemy", "visible": True, "asleep": False}


def self_knowledge_viewer(*, final=False, japanese=True):
    """DECLARED CONSTRUCTED: display_self_info's page at the source's columns."""
    value = command_screen()
    heading = "        あなたの状態:" if japanese else "     Your Attributes:"
    value["lines"][1] = value["lines"][1].ljust(15) + heading
    value["lines"][2] = " " * 15 + ("現在の体力ランク : 98/100" if japanese
                                    else "Your current Life Rating is 98/100.")
    if final:
        prompt = "[何かキーを押すとゲームに戻ります]" if japanese else "[Press any key to continue]"
        value["lines"][5] = " " * 13 + prompt
        value["cursor"] = {"visible": True, "y": 5, "x": 13}
    else:
        value["lines"][22] = " " * 15 + ("-- 続く --" if japanese else "-- more --")
        value["cursor"] = {"visible": True, "y": 22, "x": 15}
    return value


class SelfKnowledgeViewerScreenTest(unittest.TestCase):
    def test_pages_and_close_prompt_are_classified_in_both_languages(self):
        for japanese in (True, False):
            with self.subTest(japanese=japanese):
                page = classify_screen(self_knowledge_viewer(japanese=japanese))
                self.assertEqual((page.kind, page.row, page.column),
                                 (ScreenKind.SELF_KNOWLEDGE_PAGE, 22, 15))
                final = classify_screen(self_knowledge_viewer(final=True, japanese=japanese))
                self.assertEqual((final.kind, final.row, final.column),
                                 (ScreenKind.SELF_KNOWLEDGE_FINAL, 5, 13))

    def test_heading_without_a_prompt_is_not_answered(self):
        view = self_knowledge_viewer()
        view["lines"][22] = ""
        match = classify_screen(view)
        self.assertEqual((match.kind, match.feature),
                         (ScreenKind.UNKNOWN, "incomplete-self-knowledge-viewer"))

    def test_the_any_key_context_admits_the_viewer(self):
        reading = InputContextReading(source="server", kind="any_key", details={})
        admitted = compatible_kinds(reading)
        self.assertIn(ScreenKind.SELF_KNOWLEDGE_PAGE, admitted)
        self.assertIn(ScreenKind.SELF_KNOWLEDGE_FINAL, admitted)


class SelfKnowledgeExecutorTest(_recorded.ProductionHarness):
    def _quaff(self, screens, owner=REASON):
        game, _client, executor = self.make()
        game.screens = screens
        executor.observe_boundary(deadline=9999999999)
        result = executor.submit(Operation(
            81, owner, "q", executor.ready_board,
            [Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "g", "どの薬を飲みますか?")],
        ), deadline=9999999999)
        return result, game.accepted

    def test_quaff_pages_through_and_closes_the_viewer(self):
        result, accepted = self._quaff([
            prompt_screen("どの薬を飲みますか?"),
            self_knowledge_viewer(),
            self_knowledge_viewer(),
            self_knowledge_viewer(final=True),
            command_screen(6),
        ])
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(accepted, ["q", "g", " ", " ", "\x1b"])

    def test_enlightenment_message_then_viewer(self):
        # star_enlightenment: msg_print, msg_erase (the -more-), then self_knowledge.
        result, accepted = self._quaff([
            prompt_screen("どの薬を飲みますか?"),
            prompt_screen("更なる啓蒙を感じた... -続く-"),
            self_knowledge_viewer(final=True),
            command_screen(6),
        ])
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(accepted, ["q", "g", " ", "\x1b"])

    def test_any_owner_closes_the_viewer(self):
        # An unknown flavour drunk to learn it can be Self Knowledge too.
        result, accepted = self._quaff([
            prompt_screen("どの薬を飲みますか?"),
            self_knowledge_viewer(final=True),
            command_screen(6),
        ], owner="item:quaff-unknown")
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(accepted, ["q", "g", "\x1b"])


class SelfKnowledgeQuaffRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = {record["id"]: record["line"] for record in map(json.loads, stream)}
        with gzip.open(TABLE_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.table_lines = {record["id"]: record["line"] for record in map(json.loads, stream)}
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.policy = _policy(self.directory, self.monrace)

    def _consume(self, raw):
        boards = _consume_response_sequence(
            [json.dumps(raw, ensure_ascii=False)], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl")[1]
        board = boards[-1]
        self.policy._skill_exp_cache = (
            0, 0, board.player.level, self.policy._town_visit_epoch)
        return board

    def _quaff_key(self, raw):
        board = self._consume(raw)
        self.policy.last_reason = None
        return self.policy._stat_gain_quaff_key(board, self.policy._physical_hostiles(board))

    def test_table_rows_are_drunk_on_sight(self):
        for sval in (SELF_KNOWLEDGE, STAR_ENLIGHTENMENT):
            with self.subTest(sval=sval):
                item = consumable_policy.consumables()[(TVAL_POTION, sval)]
                self.assertTrue(item.use)
                self.assertNotIn((TVAL_POTION, sval), consumable_policy.USE_UNSUPPORTED)

    def test_recorded_boards_drink_the_carried_potion(self):
        for record_id, slot in (("dungeon/1270", "g"), ("town/3537", "i")):
            with self.subTest(record_id):
                self.setUp()
                raw = json.loads(self.lines[record_id])
                potion = next(item for item in raw["inventory"] if item["slot"] == slot)
                self.assertEqual((potion["tval"], potion["sval"], potion["aware"]),
                                 (TVAL_POTION, SELF_KNOWLEDGE, True))
                self.assertEqual(self._quaff_key(raw), "q" + slot)
                self.assertEqual(self.policy.last_reason, REASON)

    def test_enlightenment_in_the_recorded_slot_is_drunk(self):
        raw = json.loads(self.lines["dungeon/1270"])
        potion = next(item for item in raw["inventory"] if item["slot"] == "g")
        # DECLARED CONSTRUCTED: *啓蒙*の薬 (75/57) in the recorded slot.
        potion.update(sval=STAR_ENLIGHTENMENT, name="*啓蒙*の薬")
        self.assertEqual(self._quaff_key(raw), "qg")
        self.assertEqual(self.policy.last_reason, REASON)

    def test_not_drunk_with_an_enemy_in_view_blind_or_confused(self):
        def hostile(raw):
            raw["visible_monsters"] = [dict(MONSTER, y=raw["player"]["y"], x=raw["player"]["x"] + 2)]

        def status(name):
            return lambda raw: raw["player"]["status"].__setitem__(name, True)

        for change in (hostile, status("blind"), status("confused")):
            with self.subTest(change):
                self.setUp()
                # DECLARED CONSTRUCTED: the refusal's enemy or status.
                raw = json.loads(self.lines["dungeon/1270"])
                change(raw)
                self.assertIsNone(self._quaff_key(raw))
                self.assertNotEqual(self.policy.last_reason, REASON)

    def test_the_ladder_drinks_it_on_the_safe_dungeon_board(self):
        raw = json.loads(self.table_lines["dungeon/0"])
        for item in raw["inventory"]:
            if item["slot"] in "bi":
                # DECLARED CONSTRUCTED: 自己分析の薬 in slot b, ヒーローの薬 (a carry
                # kind) in slot i, as the table test's stat potion.
                tval, sval, name = ((TVAL_POTION, SELF_KNOWLEDGE, "自己分析の薬") if item["slot"] == "b"
                                    else (TVAL_POTION, 32, "ヒーローの薬"))
                item.update(tval=tval, sval=sval, name=name, count=1)
        board = self._consume(copy.deepcopy(raw))
        self.assertEqual(self.policy.choose_key(board), "qb")
        self.assertEqual(self.policy.last_reason, REASON)


if __name__ == "__main__":
    unittest.main()
