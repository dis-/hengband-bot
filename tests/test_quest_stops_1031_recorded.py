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

Q34 opening wait (n1-a life-426, Lv1 in the Outpost, three stall captures):
for all 124 decisions of the first capture the opening owner answered
opening-q34:wait.  _fixed_quest_key declines while a monster stands beside the
player, so no entry verdict was evaluated, and the town kill-mob rung below the
opening owner never ran while Merry and a beggar touched the player.

Q2 wall breach (n1-a life-422): the Telmora entry gate counted the
utility_tools.wall_breach carry as one item, so a Stone to Mud wand with one
charge passed for the five-wall corridor [7..11,47].  After the first cast the
bot waited at [7,47] on quest:blocked:q2-breach-tool until loop-detected.
Owner 2026-10-31 「Q2の岩石溶解 - 回数を数える」: charges count one wall each;
a qualifying digger still breaches the whole corridor.  The blocked reason is
now a named final stop.

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

from hengbot.cli import _policy_final_stop_required
from hengbot.model import SV_WAND_STONE_TO_MUD, TVAL_WAND, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import (
    Q2_BREACH_CORRIDOR, Q2_BREACH_WALL_COUNT, Q34_SEQUENCE_DOOR_ATTEMPT_LIMIT, WAIT_KEY,
)
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_navigator import QuestFloorNavigator
from hengbot.quest_strategies import load_quest_strategies
from tests import test_opening_route_r2_recorded as round2
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


class Q34OpeningAdjacentMonsterRecordedTest(ProductionHarness):
    post = bee.Q34BeeSweepRecordedTest.post

    @classmethod
    def setUpClass(cls):
        cls.data = load_fixture()["opening"]
        round2.OpeningRouteR2RecordedTest.setUpClass()
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def policy(self):
        # The Outpost map and Q34 facts of the recorded opening-route policy.
        policy, _ = round2.OpeningRouteR2RecordedTest().case("1")
        for race_id in {monster["race_id"] for monster in self.data["board"]["visible_monsters"]}:
            policy._monrace_knowledge[race_id] = self.monraces[race_id]
        policy.prime(parse_snapshot(self.data["board"], policy._monrace_knowledge))
        # DECLARED RECONSTRUCTED: the capture has no checkpoint.  The recorded
        # rows show no live town route claim (claim owner quest-request; the
        # bot ran with enforce_town_claims=False) and a scanned Home.
        policy.consume_home_knowledge([])
        policy._town_claims_active = lambda snapshot: False
        return policy

    def test_recorded_adjacent_town_monster_is_answered_not_waited_on(self):
        raw = self.data["board"]
        self.assertEqual({row["reason"] for row in self.data["decisions"]},
                         {"opening-q34:wait"})
        self.assertEqual(len(self.data["decisions"]), 124)
        policy = self.policy()
        board = parse_snapshot(raw, policy._monrace_knowledge)
        adjacent = policy._physical_adjacent_hostiles(board)
        self.assertTrue(adjacent)
        key = self.post(policy, raw, self.data["following"])
        # The town melee rung attacks a monster beside the player.
        self.assertEqual(policy.last_reason, "melee")
        self.assertIn(key, {policy._direction_key(board.player.position, monster.position)
                            for monster in adjacent})


class Q2BreachChargesRecordedTest(ProductionHarness):
    post = bee.Q34BeeSweepRecordedTest.post

    @classmethod
    def setUpClass(cls):
        cls.data = load_fixture()["q2"]
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.quests = load_quest_knowledge(EDIT / "quests")
        cls.profiles = load_quest_strategies(ROOT / "strategy/quests")

    def policy(self, raw, quests):
        policy = HengbotPolicy(quest_knowledge=quests,
                               quest_strategies=self.profiles,
                               monrace_knowledge=self.monraces)
        policy.prime(parse_snapshot(raw, self.monraces))
        # DECLARED RECONSTRUCTED: the capture keeps no Home page; an empty
        # scan lets the town owners decide instead of requesting one.
        policy.consume_home_knowledge([])
        return policy

    def test_corridor_is_five_walls_of_the_quest_map(self):
        terrain = self.quests[2].battlefield.terrain
        self.assertEqual([terrain[(cell.y, cell.x)] for cell in Q2_BREACH_CORRIDOR],
                         ["wall"] * Q2_BREACH_WALL_COUNT)
        self.assertEqual(Q2_BREACH_WALL_COUNT, 5)

    def test_recorded_one_charge_wand_does_not_admit_the_q2_request(self):
        raw = self.data["board"]
        self.assertEqual(self.data["decisions"][0]["reason"], "fixedquest:request:approach")
        policy = self.policy(raw, self.quests)
        board = parse_snapshot(raw, self.monraces)
        (wand,) = [item for item in board.inventory if item.tval == TVAL_WAND
                   and item.sval == SV_WAND_STONE_TO_MUD]
        self.assertEqual(wand.charges, 1)
        status = policy._quest_carry_status(
            board, self.profiles[2].required_force)["utility_tools.wall_breach"]
        self.assertEqual((status["measured"], status["ready"]), (0, False))
        policy.consume_skill_knowledge({
            "player": {"level": board.player.level},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        self.post(policy, raw, self.data["following"])
        # The existing owner of an unready Q2 head in Telmora returns to the
        # Outpost to procure (this policy has no remembered Telmora inn route,
        # hence its route-unavailable variant); the recorded run requested Q2.
        self.assertTrue(policy.last_reason.startswith("fixedquest:prepare-return"),
                        policy.last_reason)
        # DECLARED CONSTRUCTED: the same wand with one charge per wall.
        charged = replace(board, inventory=[
            replace(item, charges=Q2_BREACH_WALL_COUNT) if item is wand else item
            for item in board.inventory])
        status = policy._quest_carry_status(
            charged, self.profiles[2].required_force)["utility_tools.wall_breach"]
        self.assertEqual((status["measured"], status["ready"]), (1, True))

    def test_recorded_empty_wand_breach_is_a_named_final_stop(self):
        # The recorded stop board, through the breach owner itself: the Q2
        # phase latches that select it live only in the stopped process.
        raw = self.data["stop_board"]
        self.assertEqual(self.data["decisions"][1]["reason"], "loop-detected")
        policy = self.policy(raw, {2: self.quests[2]})
        board = parse_snapshot(raw, self.monraces)
        navigator = QuestFloorNavigator(2, self.quests[2].battlefield)
        self.assertEqual(policy._q2_breach_key(board, navigator), WAIT_KEY)
        self.assertEqual(policy.last_reason, "quest:blocked:q2-breach-tool")
        self.assertTrue(_policy_final_stop_required(policy))


if __name__ == "__main__":
    unittest.main()
