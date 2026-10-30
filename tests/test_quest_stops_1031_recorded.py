"""D33 (2026-10-30 viewing bots): recorded fixed-quest stops.

Q34 sequence door (n1-c lives 030 and 039): a zombie Magic-Eater's lock-pick
chance is the game's 2% floor (exe_open: "if (j < 2) j = 2").  The bound of 200
picks per door ended both runs on quest:blocked:q34-sequence-door-locked,
although every one of the 200 picks was answered "鍵をはずせなかった。" and so
was progress.  The bound now counts only unanswered picks.

Q31 (n1-a lives 419 and 423, 5 loop-detected stops): an off-plan Huorn
(NEVER_MOVE, BLINK/TELE_TO) seen 19-20 cells away down the open west rows made
the threat model predict TELE_TO, so the sweep step north was undone by
retake-hold south, forever.  Beyond get_max_range() (cdis over 18) a monster
casts nothing without a counter-attack target (mspell-attack.cpp:318-321),
and a NEVER_MOVE monster cannot walk into range.

Boards, their order and the recorded decisions are from
tests/fixtures/quest-stops-20261030.json.gz (tests/extract_quest_stops_1031_fixture.py).
Restored state: the cleared fixed targets (Q34: all three, reconstructed from
the recorded kills; Q31: the checkpoint's set) and the checkpoint's surveyed
cells.  Executor replies are the next recorded board.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import Q34_SEQUENCE_DOOR_ATTEMPT_LIMIT
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from tests import test_q34_bee_sweep_recorded as bee
from tests.test_input_executor import ProductionHarness
from tests.test_q34_collect_recorded import captured, make_policy

ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
FIXTURE = Path(__file__).with_name("fixtures") / "quest-stops-20261030.json.gz"
SEQUENCE_DOORS = {"n1-c/life-030": Position(4, 16), "n1-c/life-039": Position(4, 15)}


def decide(policy, raw):
    """The public chooser, with the omitted skill-knowledge reply supplied."""
    policy.consume_skill_knowledge({
        "player": {"level": raw["player"]["level"]},
        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
    })
    return policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))


def load_fixture():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class Q34SequenceDoorRecordedTest(ProductionHarness):
    post = bee.Q34BeeSweepRecordedTest.post

    @classmethod
    def setUpClass(cls):
        cls.data = load_fixture()["doors"]
        cls.facts = captured()

    def boards(self, life):
        case = self.data[life]
        boards = []
        for board in case["boards"]:
            board = copy.deepcopy(board)
            board["grid_map"] = copy.deepcopy(case["grid_maps"][board["grid_map"]])
            boards.append(board)
        return boards

    def policy(self, raw):
        policy = make_policy(self.facts)
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15), (107, 9, 11), (107, 11, 9),
        }
        policy._quest_strategy_surveyed_placements[34] = {Position(3, 13)}
        return policy

    def test_recorded_answered_picks_keep_picking_the_sequence_door(self):
        for life, door in SEQUENCE_DOORS.items():
            with self.subTest(life=life):
                case = self.data[life]
                boards = self.boards(life)
                # The recorded run: 200 picks, every one answered as a
                # failed pick, then the named stop on the 201st board.
                self.assertEqual(len(boards), Q34_SEQUENCE_DOOR_ATTEMPT_LIMIT + 1)
                self.assertEqual(
                    [row["reason"] for row in case["decisions"]],
                    ["quest-strategy:open-sequence-door"] * Q34_SEQUENCE_DOOR_ATTEMPT_LIMIT
                    + ["quest:blocked:q34-sequence-door-locked"])
                self.assertTrue(all("鍵をはずせなかった" in board["messages"][-1]
                                    for board in boards[1:]))
                policy = self.policy(boards[0])
                approach = Position(door.y + 1, door.x)
                for raw in boards[:-1]:
                    board = parse_snapshot(raw, policy._monrace_knowledge)
                    self.assertEqual(board.player.position, approach)
                    self.assertTrue(board.grid_at(door).is_closed_door)
                    self.assertEqual(decide(policy, raw), "o8")
                    self.assertEqual(policy.last_reason, "quest-strategy:open-sequence-door")
                # Only the first, unanswered pick counts toward the bound.
                self.assertEqual(policy._q34_sequence_door_attempts[door], 1)
                last = boards[-1]
                following = dict(last, turn=last["turn"] + 10)
                self.assertEqual(self.post(policy, last, following), "o8")
                self.assertEqual(policy.last_reason, "quest-strategy:open-sequence-door")

    def test_unanswered_picks_still_end_in_the_named_stop(self):
        # DECLARED CONSTRUCTED: the recorded board with its answer removed;
        # picks the game does not answer keep the bound.
        boards = self.boards("n1-c/life-030")
        policy = self.policy(boards[0])
        door = SEQUENCE_DOORS["n1-c/life-030"]
        silent = dict(boards[-1], messages=[])
        for _ in range(Q34_SEQUENCE_DOOR_ATTEMPT_LIMIT):
            self.assertEqual(decide(policy, silent), "o8")
        self.assertEqual(policy._q34_sequence_door_attempts[door],
                         Q34_SEQUENCE_DOOR_ATTEMPT_LIMIT)
        decide(policy, silent)
        self.assertEqual(policy.last_reason, "quest:blocked:q34-sequence-door-locked")


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
