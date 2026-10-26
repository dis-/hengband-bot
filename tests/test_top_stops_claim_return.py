"""Recorded claim-return boards through public policy and follow executor."""
import tests  # noqa: F401
import copy
import gzip
import json
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from tests.test_input_executor import ProductionHarness, FaithfulHookGame, command_screen, prompt_screen

FIXTURE = Path(__file__).parent / "fixtures/top-stops-claim-return.json.gz"


class TopStopsClaimReturnTest(ProductionHarness):
    def test_public_claim_return_preserves_recorded_recall_depth(self):
        cases = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        quests = load_quest_knowledge(Path("C:/hengband/lib/edit/quests"))
        for case in cases:
            with self.subTest(source=case["source"]):
                raw = case["state"]
                board = parse_snapshot(raw, {})
                policy = HengbotPolicy(quest_knowledge=quests)
                # DECLARED CONSTRUCTED: unrelated skill bookkeeping finished;
                # this isolated command board is after the live startup scan.
                policy.consume_skill_knowledge({
                    "player": {"level": board.player.level},
                    "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
                })
                key = policy.choose_key(board)
                self.assertEqual((str(key), policy.last_reason),
                                 (case["decision"]["key"], "fixedquest:claim:return"))
                self.assertEqual(board.dungeon_level, 5)
                self.assertGreater(policy._dungeon_entry_depth(board, 2, via_recall=True), 5)
                game = FaithfulHookGame()
                game.state = copy.deepcopy(raw)
                game.screen = command_screen(raw["turn"])
                # DECLARED CONSTRUCTED: item chooser and post-n command barrier.
                # The intervening confirmation is copied verbatim from capture.
                source = prompt_screen("Read which scroll?")
                source["input_context"] = {"kind": "item", "prompt": "Read which scroll?"}
                after = copy.deepcopy(raw)
                after["player"]["recalling"] = True
                game.screens = [source, case["screen"], command_screen(raw["turn"] + 1)]
                game.states = [copy.deepcopy(raw), copy.deepcopy(raw), after]
                game, _client, executor = self.make(game)
                self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
                port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
                sent, _posted = _send_new_decision_key(
                    port, "top-stops-A", key, None, set(), in_store=False,
                    decision={"sequence": case["decision"]["decision_sequence"], "reason": policy.last_reason},
                    snapshot=board, posting_contract=PostingContract(),
                )
                self.assertTrue(sent)
                self.assertEqual(port.last_result.outcome, "completed", port.last_result.reason)
                self.assertEqual(game.accepted, ["r", str(key)[1], "n"])
                self.assertEqual(game.state["progress"]["recall_depth"], board.recall_depth)
                self.assertTrue(parse_snapshot(game.state, {}).player.recalling)

    def test_claim_owner_does_not_answer_unrelated_confirmation(self):
        game, _client, executor = self.make()
        executor.observe_boundary(deadline=9999999999)
        game.screens = [prompt_screen("Unrelated? [y/n]")]
        from hengbot.input_executor import Operation
        result = executor.submit(Operation(1, "fixedquest:claim:return", "rg", executor.ready_board), deadline=9999999999)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, ["rg"])
