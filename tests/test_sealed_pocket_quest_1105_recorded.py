"""n1-c life-140, random quest 40 (鉄獄50階), 2026-11-05 05:41: sealed in rock.

*Destruction* at (19,98) left the player two floor cells (19,97)-(19,98) with rock
on every other side.  The oscillation guard found no way out and set the
navigation exhausted, and the ladder skipped everything on a quest floor, so
every restart ended in livelock:exhausted within 25 decisions with 9 Scrolls of
Teleportation in the pack.  Teleportation stays on the floor, so the quest does
not hold it.

Recorded: the last restart's state rows and decisions
(tests/extract_sealed_pocket_quest_1105_fixture.py).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import PostingContract, _ExecutorInputPort, _consume_response_sequence, _send_new_decision_key
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SEARCH_LIMIT
from test_esp_threat_rest_recorded import EDIT, _policy
from tests import test_input_executor as executor_pins

FIXTURE = Path(__file__).with_name("fixtures") / "sealed-pocket-quest-1105.json.xz"
STOP_TURN = 3971127
READ_PROMPT = "(持ち物:a-z, ESCで中断) どの巻物を読みますか?"
POCKET = ((19, 97), (19, 98))
READ_TELEPORT = "rh"  # the recorded pack: h) 9 Scrolls of Teleportation


class SealedPocketQuestRecordedTest(executor_pins.ProductionHarness):
    def test_the_pocket_is_left_by_teleport_on_the_quest_floor(self):
        pin = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        lines = pin["lines"]
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
        recorded = {row["turn"]: row for row in pin["decisions"]}
        board = None
        for turn, segment in sorted(turns.items()):
            _, boards = _consume_response_sequence(
                segment, policy, lambda _key: True, monrace,
                knowledge_ledger_path=root / "knowledge.jsonl")
            board = boards[-1]
            if turn == min(turns):
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
            key = policy.choose_key(board)
            if turn != STOP_TURN:
                # Only the stop board is decided differently.
                self.assertEqual(
                    (key, policy.last_reason),
                    (recorded[turn]["key"], recorded[turn]["reason"]), turn)

        self.assertEqual(board.floor_key, (1, 50, 40))
        self.assertEqual(policy.last_reason, "livelock:teleport-explore")
        self.assertEqual(key, READ_TELEPORT)
        self.assertFalse(policy._nav_exhausted)

        raw_board = json.loads(lines[-1])
        game = executor_pins.FaithfulHookGame()
        game.state = raw_board
        game.screen = executor_pins.command_screen(raw_board["turn"])
        # DECLARED CONSTRUCTED: the item prompt and the next board after the command.
        game.screens = [executor_pins.prompt_screen(READ_PROMPT),
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
        self.assertEqual(game.accepted, list(key))
