"""D47: the recorded n1-c life-065 Q2 fare wait on Yeek cave 1F (2026-10-31).

The Magic-Eater (Lv28, stage 2 complete, Q2 The Sewer TAKEN) descended to
Yeek cave 1F on a mining run with 272 gold.  On the floor the absence-gated
Telmora Q2 errand (_telmora_q2_travel_key) read the exported ``town_id`` 0
(the game exports the last town on a dungeon floor too) as standing in the
Outpost, found the fare short and answered ``5`` (fixedquest:q2-travel-needs-
funds), rewriting the fundraising mode to "prepare".  Each wait also reset
the mining re-arm streak, so no floor owner ever acted; loop-detected three
times retired the character.

Pinned through the public choose_key and the production executor port: on
the recorded board the floor's owners act (explore while the mining re-arm
streak builds, then the mining run wields its digger); the Q2 errand never
answers off a town board and the mining mode stays.
Fixture: tests/fixtures/q2-funds-floor-20261031.json.gz
(tests/extract_q2_funds_floor_fixture.py).

DECLARED CONSTRUCTED: the captured process already held the skill knowledge
(the periodic skill-experience request does not own the decision).  A walk's
reply moves the player one cell on the recorded board; a held key's reply
advances the turn.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.policy_fundraising import (
    FundraisingPurpose, FundraisingPurposeRecord, FundraisingTransportChild,
)
from hengbot.quest_strategies import load_quest_strategies
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen

FIXTURE = Path(__file__).parent / "fixtures" / "q2-funds-floor-20261031.json.gz"
STRATEGIES = Path(__file__).resolve().parents[1] / "strategy" / "quests"
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
Q2_REASON = "fixedquest:q2-"


class Q2FundsFloorRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def policy(self):
        case = self.case
        races = {}
        for key, facts in case["monraces"].items():
            facts = copy.deepcopy(facts)
            for field in ("flags", "abilities"):
                facts[field] = frozenset(facts[field])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            races[int(key)] = MonraceKnowledge(**facts)
        raw = copy.deepcopy(case["board"])
        policy = HengbotPolicy(monrace_knowledge=races,
                               quest_strategies=load_quest_strategies(STRATEGIES))
        policy.prime(parse_snapshot(raw, races))
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        terrain = case["terrain"]
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in terrain[f"{name}_t"])
        policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
        for name, value in case["modes"].items():
            setattr(policy, name, value)
        policy._fundraising_mode = case["mode_before"]
        recorded = case["purpose"]
        purpose = FundraisingPurpose(recorded["id"], recorded["mode"],
                                     recorded["first_run_food_waiver"])
        child = recorded["child"]
        policy._fundraising_run_purpose = purpose
        policy._fundraising_purpose_record = FundraisingPurposeRecord(
            purpose, status=recorded["status"],
            child=FundraisingTransportChild(
                purpose.identity, child["direction"], (0, 0, 0),
                child["posted_sequence"], state=child["state"]),
        )
        return policy, raw

    def post(self, policy, raw, key, following):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), key)

    @staticmethod
    def reply(raw, key):
        """DECLARED CONSTRUCTED (module docstring)."""
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        if key in DIRECTIONS:
            dy, dx = DIRECTIONS[key]
            following["player"]["y"] += dy
            following["player"]["x"] += dx
        return following

    def test_recorded_row(self):
        decision = self.case["decision"]
        self.assertEqual(
            (decision["decision_sequence"], decision["turn"], decision["reason"],
             decision["key"]),
            (16311, 5135804, "fixedquest:q2-travel-needs-funds", "5"))
        self.assertEqual((self.case["mode_before"], decision["fundraising"]["mode"]),
                         ("mine", "prepare"))
        self.assertEqual(decision["mining"]["remaining_known"], 19)
        board = parse_snapshot(copy.deepcopy(self.case["board"]), {})
        self.assertFalse(board.in_town)
        self.assertEqual((board.floor_key[:2], board.town_id), ((2, 1), 0))
        self.assertEqual(board.player.gold, 272)
        self.assertEqual(board.quests[2].status, 1)

    def test_floor_owners_act_and_the_mining_run_wields_its_digger(self):
        policy, raw = self.policy()
        reasons = []
        for _ in range(16):
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            reasons.append(policy.last_reason)
            self.assertFalse(policy.last_reason.startswith(Q2_REASON), reasons)
            self.assertNotIn(key, ("", "5"), reasons)
            self.assertEqual(policy._fundraising_mode, "mine", reasons)
            if policy.last_reason.startswith("fundraise:"):
                break
            following = self.reply(raw, key)
            self.post(policy, raw, key, following)
            raw = following
        self.assertEqual(reasons[-1], "fundraise:wield-digging-tool", reasons)


if __name__ == "__main__":
    unittest.main()
