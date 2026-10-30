"""D33 (2026-10-30 viewing bots): recorded fixed-quest stops.

Q31 (n1-a lives 419 and 423, 5 loop-detected stops): an off-plan Huorn
(NEVER_MOVE, BLINK/TELE_TO) seen 19-20 cells away down the open west rows made
the threat model predict TELE_TO, so the sweep step north was undone by
retake-hold south, forever.  Beyond get_max_range() (cdis over 18) a monster
casts nothing without a counter-attack target (mspell-attack.cpp:318-321),
and a NEVER_MOVE monster cannot walk into range.

Boards, their order and the recorded decisions are from
tests/fixtures/quest-stops-20261030.json.gz (tests/extract_quest_stops_1031_fixture.py).
Restored state: the checkpoint's cleared fixed targets and surveyed cells.
Executor replies are the next recorded board.
"""
import tests  # noqa: F401 -- isolate live runtime files

from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from tests import test_q34_bee_sweep_recorded as bee
from tests.test_input_executor import ProductionHarness

ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
FIXTURE = Path(__file__).with_name("fixtures") / "quest-stops-20261030.json.gz"


def load_fixture():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class Q31DistantHuornRecordedTest(ProductionHarness):
    post = bee.Q34BeeSweepRecordedTest.post

    @classmethod
    def setUpClass(cls):
        cls.data = load_fixture()["sweeps"]
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.quest = load_quest_knowledge(EDIT / "quests")[31]
        cls.profile = load_quest_strategies(ROOT / "strategy/quests")[31]

    def policy(self, case):
        board = parse_snapshot(case["board"], self.monraces)
        policy = HengbotPolicy(quest_knowledge={31: self.quest},
                               quest_strategies={31: self.profile},
                               monrace_knowledge=self.monraces)
        policy.prime(board)
        policy._quest_strategy_initial_hold_turns[31] = (
            self.profile.engagement_plan["initial_hold_turns"])
        policy._quest_strategy_post_wave_light_attempted.add(31)
        policy._quest_strategy_cleared_targets[31] = {
            tuple(target) for target in case["cleared_targets"]}
        policy._quest_strategy_surveyed_placements[31] = {
            Position(*cell) for cell in case["surveyed"]}
        return policy

    def test_recorded_out_of_range_huorn_does_not_reverse_the_sweep(self):
        for name, case in self.data.items():
            with self.subTest(case=name):
                board = parse_snapshot(case["board"], self.monraces)
                (huorn,) = board.visible_monsters
                self.assertEqual(huorn.race_id, 329)
                self.assertGreater(HengbotPolicy._monster_cast_distance(
                    huorn.position, board.player.position), 18)
                # The recorded alternation: retake-hold south, then sweep north.
                self.assertEqual(
                    [(row["reason"], row["key"]) for row in case["decisions"]],
                    [("quest-strategy:retake-hold", "2"),
                     ("quest-strategy:placement-sweep", "8")])
                policy = self.policy(case)
                self.assertEqual(policy.threat_prediction(
                    board, board.visible_monsters, turns=3)["operational_total"], 0)
                self.assertEqual(self.post(policy, case["board"], case["following"]), "8")
                self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep")

    def test_huorn_within_spell_range_still_retakes_the_hold(self):
        # DECLARED CONSTRUCTED: the recorded Huorn moved down the same open
        # row to 18 cells, inside get_max_range().
        case = self.data["n1-a/life-423/072744"]
        board = parse_snapshot(case["board"], self.monraces)
        (huorn,) = board.visible_monsters
        near = Position(huorn.position.y, board.player.position.x + 18)
        board = replace(board, visible_monsters=[replace(huorn, position=near, distance=18)])
        policy = self.policy(case)
        self.assertGreater(policy.threat_prediction(
            board, board.visible_monsters, turns=3)["operational_total"], 0)
        policy.consume_skill_knowledge({
            "player": {"level": board.player.level},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        self.assertEqual(policy.choose_key(board), "2")
        self.assertEqual(policy.last_reason, "quest-strategy:retake-hold")


if __name__ == "__main__":
    unittest.main()
