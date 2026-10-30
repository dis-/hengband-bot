"""D30 follow-ups: the owner's three rules of 2026-10-31 on recorded boards.

1. 「逃げた階に戻らないための決定なので帰還後はリセットされるべき」: the
   escape-by-stairs descent cooldown ends once the character is back in town
   (n1-a life-440: status-threat:stairs from Yeek 1F, then stuck:wander
   with descent_refusal descent-cooldown until a forced departure waited out).
2. 「条件未達になったなら条件を満たすための行動を取る必要がある」: a committed
   forced departure whose minimum no longer holds is handed back to the
   ordinary owners (n1-a life-427: a town fight left HP below full and the
   repetition rungs waited until the named-block stop).
3. 「自宅にいるなら先に不要物を仕舞う」: a Home take that does not fit the town
   pack budget, the mana eater's food take included, first shelves unneeded
   stacks (n1-b life-256 Home page, 19 of 23 slots used).

Boards and catalogues are recorded; replies to newly posted keys and the
marked state below are constructed.  Every decision goes through the public
chooser, and posted keys through the production executor.
Fixture: tests/extract_town_followups_fixture.py.
"""
import tests  # noqa: F401 -- runtime-file isolation

import copy
import gzip
import hashlib
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    PostingContract, _consume_response_sequence, _ExecutorInputPort, _send_new_decision_key,
)
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from tests import test_input_executor as harness
from tests.test_esp_threat_rest_recorded import _policy


FIXTURE = Path(__file__).with_name("fixtures") / "town-followups-20261031.json.gz"
FIXTURE_SHA256 = "2f9c35484db1fc8aa4fea9d9db1f8fb590106fe651af15cdbf5d7b56941e8814"


class TownFollowupsRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == FIXTURE_SHA256
        cls.cases = json.loads(gzip.decompress(data))

    def policy(self, case):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        races = {}
        for key, facts in case["monraces"].items():
            facts = dict(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            races[int(key)] = MonraceKnowledge(**facts)
        return _policy(Path(self.directory.name), races)

    def answer(self, policy, row):
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        _consume_response_sequence([json.dumps(row)], policy, lambda key: True, {},
                                   knowledge_ledger_path=Path(self.directory.name) / "k.jsonl")

    def decide(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        # DECLARED CONSTRUCTED: the skill census, as in the other town replays.
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return board, policy.choose_key(board)

    def post(self, policy, raw, key):
        """Send one town key through the production executor."""
        game = harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = harness.command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the next board after the posted key.
        following = copy.deepcopy(raw)
        following["turn"] += 10
        prompts = ([harness.prompt_screen("Rest (0-9999, '*' for HP/SP, '&' as needed): ")]
                   if key.startswith("R") else [])
        game.screens = prompts + [harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in prompts] + [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
            posting_contract=PostingContract())
        self.assertTrue(sent, getattr(port.last_result, "stop_line", None))
        self.assertEqual(port.last_result.outcome, "completed")
        policy.confirm_key_posted(key)

    # Rule 1 ---------------------------------------------------------------
    def test_escape_descent_cooldown_ends_back_in_town(self):
        case = self.cases["cooldown"]
        rows = case["rows"]
        recorded = case["recorded"]
        self.assertEqual(recorded["83"][0]["reason"], "status-threat:stairs")
        self.assertEqual((recorded["84"][0]["reason"], recorded["84"][0]["descent_refusal"]),
                         ("stuck:wander", "descent-cooldown"))
        policy = self.policy(case)
        self.answer(policy, rows["home"])
        policy.prime(parse_snapshot(copy.deepcopy(rows["town"]), policy._monrace_knowledge))
        self.decide(policy, rows["town"])
        _, key = self.decide(policy, rows["dungeon"])
        # The recorded escape arms the cooldown on the fled floor.
        self.assertEqual((key, policy.last_reason), ("<", "status-threat:stairs"))
        self.assertTrue(policy._descent_blocked)
        policy.confirm_key_posted(key)
        arrival, key = self.decide(policy, rows["arrival"])
        self.assertFalse(policy._descent_blocked)
        self.assertEqual(policy._descent_block_countdown, 0)
        self.assertFalse(policy._descent_is_blocked(arrival)
                         and policy._descent_refusal_reason == "descent-cooldown")
        self.assertNotEqual(policy.last_reason, "stuck:wander")
        self.post(policy, rows["arrival"], key)


if __name__ == "__main__":
    import unittest
    unittest.main()
