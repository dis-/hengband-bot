"""n1-b life-294 (2026-11-02 13:14, Yeek cave 1F): a blind mining run.

A gas trap blinded the mining warrior at turn 144615 (trap.cpp
TrapType::BLIND) with no Cure Critical Wounds carried.  A blind player's
map is not updated, so the run kept acting on the board from before:
dig-to-treasure 'T7' into the vein it had just dug (cmd-tunnel.cpp
「そこは掘れない。」, no turn spent: the stalled-command stop of 13:14:36),
then after the restart it stepped back onto the trap (blinded again) and
waited '5' with fundraise:upstairs-not-found at one cell until the cell
guard stopped it twice (13:14:44, 13:14:52) and the character was replaced.

Now the blind run rests (``R&``, until ``is_fully_healthy`` which includes
sight, player-processor.cpp) before any floor work: both recorded boards
answer ``fundraise:wait-sight`` and the rest is posted through the
production executor.
Fixture: tests/extract_n1b_blind_mining_1102_fixture.py (boards, remembered
terrain and fundraising modes of each capture).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
import time
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import REST_MACRO
from hengbot.policy_fundraising import FUNDRAISING_WAIT_SIGHT_REASON
from tests.support import recorded as executor_harness
from tests.test_n1c_loops_0336_1102_recorded import REST_PROMPT


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-blind-mining-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
DUG_OUT = "そこは掘れない。"


class BlindMiningRecordedTest(executor_harness.ProductionHarness):

    def policy(self, case):
        raw = case["board"]
        policy = HengbotPolicy(monrace_knowledge={})
        policy.prime(parse_snapshot(copy.deepcopy(raw), {}))
        terrain = case["terrain"]
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in terrain[f"{name}_t"])
        for name, value in case["modes"].items():
            setattr(policy, name, value)
        if case["skill"] is not None:
            policy.consume_skill_knowledge(
                {**case["skill"], "player": {"level": raw["player"]["level"]}})
        return policy

    def post(self, policy, raw, key):
        following = dict(copy.deepcopy(raw), messages=[])
        following["turn"] += 750  # DECLARED CONSTRUCTED: the rest until sight returns
        following["player"]["status"]["blind"] = False
        game = executor_harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = executor_harness.command_screen(raw["turn"])
        game.screens = [executor_harness.prompt_screen(REST_PROMPT),
                        executor_harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw), copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "n1b-blind-mining", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, (getattr(port.last_result, "reason", None), game.accepted))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, ["R", key[1:]])

    def test_recorded_rows_acted_on_the_map_while_blind(self):
        dig = CASE["dig"]
        self.assertTrue(dig["board"]["player"]["status"]["blind"])
        self.assertTrue(any(DUG_OUT in message for message in dig["board"]["messages"]))
        # The tail also holds an older visit's row at the same game turn.
        here = dig["board"]["player"]
        self.assertEqual({(row["reason"], row["key"]) for row in dig["decisions"]
                          if row["reason"] != "loop-detected"
                          and row["position"] == {"y": here["y"], "x": here["x"]}},
                         {("fundraise:dig-to-treasure", "T7")})
        wait = CASE["wait"]
        self.assertTrue(wait["board"]["player"]["status"]["blind"])
        self.assertEqual([(row["reason"], row["key"]) for row in wait["decisions"]],
                         [("fundraise:upstairs-not-found", "5"), ("loop-detected", "")])
        for name in ("dig", "wait"):
            self.assertEqual(CASE[name]["modes"]["_fundraising_mode"], "mine")
            board = parse_snapshot(copy.deepcopy(CASE[name]["board"]), {})
            self.assertEqual((board.floor_key, board.visible_monsters), ((2, 1, 0), []))
            self.assertFalse(any(item.tval == 75 for item in board.inventory))  # no potion

    def test_blind_mining_run_rests_until_it_sees(self):
        for name in ("dig", "wait"):
            with self.subTest(name):
                case = CASE[name]
                policy = self.policy(case)
                raw = copy.deepcopy(case["board"])
                key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), {}))
                self.assertEqual((key, policy.last_reason),
                                 (REST_MACRO, FUNDRAISING_WAIT_SIGHT_REASON))
                self.post(policy, raw, key)


if __name__ == "__main__":
    import unittest
    unittest.main()
