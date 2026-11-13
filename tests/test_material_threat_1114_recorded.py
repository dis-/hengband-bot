"""n1-c life-207: a single emergency escape read Recall because a summoner was merely visible.

Owner 2026-11-14 (recall-churn-1114 question 1, verbatim 「当てはめる」): the 10-03 rule
(「次のターンに召喚を受ける可能性がない」 summoners are no reason, ``_summoner_may_summon_next_turn``)
applies to the Recall after an emergency escape (``_post_emergency_return_trigger``, trigger
``emergency-material-threat``) too: only a summoner or breeder that can summon or multiply before
the player's next action counts (material_threat).  n1-c life-207 (ガラスの城 60F, 2026-11-14
03:54-04:31) read that Recall ten times, with summoners behind glass walls or out of range.

Recorded:
- tests/fixtures/recall-churn-1114.pkl.xz (tests/extract_recall_churn_1114_fixture.py): the
  landing of 04:26:45 (decisions 4133-4134), a sleeping マスター・イーク at cdis 10 with a line to
  the player: it can summon next turn, and the Recall stays (live 4134 ``rf``).
- tests/fixtures/material-threat-1114.json.xz (tests/extract_material_threat_1114_fixture.py):
  the landing boards of the Recalls of 04:29:05 (アルベリヒ and 水の鬼 at cdis 15 behind glass)
  and 04:31:06 (混沌の王族 at cdis 20, 腐敗ビホルダー at cdis 18 behind glass).

DECLARED CONSTRUCTED: the two later landings are decided from the policy checkpoint of the
04:26:45 landing (decision 4133: the same floor key, right after an emergency Teleportation; no
checkpoint of those dives was copied), each board's game turn set to that landing's; the death
knight of 4133 given a breeder's race; the executor's prompts.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import material_threat
from hengbot.cli import _ExecutorInputPort, SendResult, _consume_response_sequence
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import Position
from hengbot.policy import HengbotPolicy
from tests.support import recorded as executor_pins
from tests.test_floor_visit_memory_1114_recorded import CASE, consumed, live, raw_board
from tests.test_magic_eater_o3 import prompt

FIXTURE = Path(__file__).with_name("fixtures") / "material-threat-1114.json.xz"
LANDINGS = json.loads(lzma.decompress(FIXTURE.read_bytes()))["landings"]
LANDING, RECALL = 4133, 4134       # 04:26:45: the landing and the Recall read on the next board
TRIGGER = "emergency-material-threat"
MASTER_YEEK, DEATH_KNIGHT = 136, 174
FAR_BREEDER, WIDE_BREEDER = 680, 626   # 死のレプラコーン (vision 8), ウボ=サスラの落とし子 (vision 100)
READ_PROMPT = "どの巻物を読みますか? "


def landing(index):
    """(policy, board, live decisions) of a later landing (DECLARED CONSTRUCTED, docstring)."""
    recorded = LANDINGS[index]
    raw = json.loads(recorded["line"])
    raw["turn"] = raw_board(LANDING)["turn"]
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoints"][LANDING])
    with TemporaryDirectory() as scratch:
        _, boards = _consume_response_sequence(
            [json.dumps(raw, ensure_ascii=False) + "\n"], policy, lambda _key: True,
            policy._monrace_knowledge, knowledge_ledger_path=Path(scratch) / "k.jsonl")
    return policy, policy.with_known_skill_exp(boards[-1]), recorded["decisions"]


def summoners(board):
    return [m for m in board.visible_monsters if m.hostile and (m.can_summon or m.can_multiply)]


class MaterialThreat1114RecordedTest(executor_pins.ProductionHarness):
    def test_recorded_scenes(self):
        """Each live Recall followed one escape; the landing's summoners were out of reach."""
        for index, (cdis, names) in enumerate((((15, 15), ("ニーベルング族の王『アルベリヒ』", "水の鬼")),
                                               ((20, 18), ("混沌の王族", "腐敗ビホルダー")))):
            with self.subTest(landing=index):
                policy, board, decisions = landing(index)
                self.assertEqual(decisions[0]["reason"], "emergency:teleport")
                self.assertEqual(decisions[2]["reason"], "return:recall")
                found = summoners(board)
                self.assertEqual(tuple(m.name for m in found), names)
                here = board.player.position
                self.assertEqual(tuple(policy._monster_cast_distance(m.position, here) for m in found), cdis)
                self.assertFalse(any(policy._summoner_may_summon_next_turn(board, m) for m in found))
        policy, board = consumed(LANDING)
        yeek = next(m for m in board.visible_monsters if m.index == MASTER_YEEK)
        self.assertTrue(yeek.asleep)
        self.assertTrue(policy._summoner_may_summon_next_turn(board, yeek))
        self.assertTrue(policy._emergency_escape_pending)
        self.assertEqual(live(RECALL), ("rf", "return:recall"))

    def test_the_out_of_reach_summoners_read_no_recall(self):
        for index in range(len(LANDINGS)):
            with self.subTest(landing=index):
                policy, board, _ = landing(index)
                self.assertTrue(policy._emergency_escape_pending)
                key = policy.choose_key(board)
                self.assertFalse(policy._emergency_escape_pending)
                self.assertNotEqual(policy._last_return_trigger, TRIGGER)
                self.assertFalse(policy._returning_to_town)
                self.assertNotEqual(policy.last_reason, "return:recall")
                self.assertFalse(str(key).startswith("r"), (key, policy.last_reason))

    def test_a_summoner_that_can_summon_next_turn_still_reads_recall(self):
        policy, board = consumed(LANDING)
        policy.choose_key(board)
        self.assertEqual(policy._last_return_trigger, TRIGGER)
        self.assertTrue(policy._returning_to_town)
        policy, board = consumed(RECALL)
        self.assertEqual((policy.choose_key(board), policy.last_reason), live(RECALL))

    def test_a_breeder_counts_when_it_may_multiply_next_turn(self):
        """The death knight behind the glass given a breeder's race (DECLARED CONSTRUCTED)."""
        policy, board = consumed(LANDING)
        knight = next(m for m in board.visible_monsters if m.index == DEATH_KNIGHT)
        self.assertEqual(policy._monster_cast_distance(knight.position, board.player.position), 16)
        for race_id, multiplies in ((FAR_BREEDER, False), (WIDE_BREEDER, True)):
            with self.subTest(race=race_id):
                breeder = replace(knight, race_id=race_id, can_summon=False, can_multiply=True)
                self.assertEqual(material_threat.may_multiply_next_turn(policy, board, breeder),
                                 multiplies)
        breeder = replace(knight, race_id=WIDE_BREEDER, can_summon=False, can_multiply=True)
        crowd = [replace(knight, index=900 + n, position=Position(knight.position.y + dy,
                                                                   knight.position.x + dx))
                 for n, (dy, dx) in enumerate(((0, 1), (1, 0), (1, 1)))]
        crowded = replace(board, visible_monsters=[*board.visible_monsters, *crowd])
        self.assertFalse(material_threat.may_multiply_next_turn(policy, crowded, breeder))

    def test_the_recall_goes_through_the_executor(self):
        policy, board = consumed(RECALL)
        key = policy.choose_key(board)
        raw = copy.deepcopy(raw_board(RECALL))
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [prompt(READ_PROMPT), executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                             "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.accepted, ["r", "f"])


if __name__ == "__main__":
    unittest.main()
