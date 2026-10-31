"""D46 (#47): the recorded n1-b life-279 death (2026-10-31 12:45, Castle 22F).

The Lv30 zombie warrior (555 max HP) meleed a swarm of 巨大ゴキブリ (race
1007, MULTIPLY, max blow 2) for 703 decisions, HP 333 -> 4, carrying Healing,
Teleportation and Word of Recall; none was used.

Chain (diagnosis LUNA-DIAG-n1b-279-death.txt): the floor was latched as a
breeder breakthrough, so every weak breeder left the strategic hostile list
(_strategic_subset) and the emergency ladder weighed no hostile (no heal,
teleport or recall); a remembered immobile summoner made
_immobile_summoner_key, which runs above the breakthrough's Recall, melee the
adjacent breeders on every board (retreat was possible, so it fought them).

Fixture: tests/fixtures/n1b-279-death-20261031.json.gz
(tests/extract_n1b_279_death_fixture.py).  Each decision goes through the
public choose_key and each posted key through the production executor port.

DECLARED CONSTRUCTED: the capture holds no ~f reply, so the skill knowledge is
supplied before each decision.  The capture holds no policy checkpoint, so
the two facts the diagnosis proved are set after priming the recorded board:
the breakthrough latch on this floor and one remembered immobile summoner
(race 263 at [30,30], a cell never seen on this level).  With exactly these
two facts the unfixed policy reproduced all 703 recorded keys and reasons
from the 1500 recorded boards (the three speed quaffs included).  Executor
replies are the same board ten game turns later.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import survival_preemption
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests import test_input_executor as executor_pins
from tests.test_town_decision_speed_caches import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-279-death-20261031.json.gz"
READ_PROMPT = "どの巻物を読みますか? "
QUAFF_PROMPT = "どの薬を飲みますか? "
COCKROACH = 1007
SUMMONER = 263  # 閾に棲む者: NEVER_MOVE, summons (constructed memory)
SUMMONER_CELL = Position(30, 30)
SV_HEALING, SV_TELEPORT, SV_RECALL = 37, 9, 11
# HP 333 (60%) and 276 (under the low-HP threshold 277.5, above the 40% heal
# ratio); then 219 (< 40%), 137, 55, 21 (the first speed quaff) and 4 (death).
WALKOUT_TURNS = (1337860, 1338894)
COLLAPSE_TURNS = (1339534, 1340288, 1341107, 1342360, 1344207)


class N1b279DeathRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def raw(self, turn):
        return copy.deepcopy(next(b for b in self.case["boards"] if b["turn"] == turn))

    def recorded(self, turn):
        return next(d for d in self.case["decisions"] if d["turn"] == turn)

    def policy_on(self, raw, *, latched=True, remembered=True):
        policy = HengbotPolicy(monrace_knowledge=dict(self.monraces))
        board = parse_snapshot(raw, policy._monrace_knowledge)
        policy.prime(board)
        if latched:
            policy._breeder_breakthrough_floor = board.floor_key
        if remembered:
            policy._immobile_summoner_memory = (board.floor_key, {SUMMONER_CELL: SUMMONER})
        return policy

    @staticmethod
    def decide(policy, raw):
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))

    def post(self, policy, raw, key, prompt):
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(prompt),
                        executor_pins.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        return game.accepted

    @staticmethod
    def slot(board, sval, tval):
        return next(item.slot for item in board.inventory
                    if item.tval == tval and item.sval == sval)

    def test_recorded_rows(self):
        for turn in (*WALKOUT_TURNS, *COLLAPSE_TURNS):
            row = self.recorded(turn)
            self.assertIn(row["reason"], {"melee", "item:strong-fight-speed"}, turn)
            raw = self.raw(turn)
            self.assertEqual(raw["player"]["hp"], row["player"]["hp"])
            races = {m["race_id"] for m in raw["visible_monsters"]}
            self.assertEqual(races, {COCKROACH}, turn)
        self.assertEqual(self.recorded(1344207)["key"], "3")
        self.assertEqual(self.recorded(1344207)["player"]["hp"], 4)
        board = parse_snapshot(self.raw(1344207), self.monraces)
        carried = {(item.tval, item.sval) for item in board.inventory}
        self.assertLessEqual({(75, SV_HEALING), (70, SV_TELEPORT), (70, SV_RECALL)}, carried)
        cockroach = next(m for m in board.visible_monsters if m.race_id == COCKROACH)
        self.assertTrue(HengbotPolicy._is_weak_breeder(board, cockroach))

    def test_collapse_boards_heal_through_the_executor(self):
        for turn in COLLAPSE_TURNS:
            with self.subTest(turn=turn):
                raw = self.raw(turn)
                policy = self.policy_on(raw)
                key = self.decide(policy, raw)
                board = parse_snapshot(raw, self.monraces)
                healing = self.slot(board, SV_HEALING, 75)
                # Recorded: melee (or the speed quaff) on every one of these.
                self.assertEqual((key, policy.last_reason), ("q" + healing, "item:heal"))
                self.assertEqual(self.post(policy, raw, key, QUAFF_PROMPT), ["q", healing])

    def test_walkout_boards_read_recall_through_the_executor(self):
        for turn in WALKOUT_TURNS:
            with self.subTest(turn=turn):
                raw = self.raw(turn)
                policy = self.policy_on(raw)
                key = self.decide(policy, raw)
                recall = self.slot(parse_snapshot(raw, self.monraces), SV_RECALL, 70)
                self.assertEqual((key, policy.last_reason),
                                 ("r" + recall, "breeder-breakthrough:recall"))
                self.assertEqual(self.post(policy, raw, key, READ_PROMPT), ["r", recall])

    def test_unlatched_breeder_fight_at_safe_hp_keeps_melee(self):
        raw = self.raw(WALKOUT_TURNS[0])
        policy = self.policy_on(raw, latched=False, remembered=False)
        self.assertEqual(self.decide(policy, raw), self.recorded(WALKOUT_TURNS[0])["key"])
        self.assertEqual(policy.last_reason, "melee")

    def test_harmless_suppressed_breeders_keep_the_strategic_list(self):
        raw = self.raw(WALKOUT_TURNS[0])
        policy = self.policy_on(raw)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        strategic = policy._strategic_hostiles(board)
        physical = policy._physical_hostiles(board)
        self.assertEqual(strategic, [])
        self.assertTrue(physical)
        # HP 333 is above the low-HP threshold and the projection (35) far
        # below HP: no emergency return is re-armed by the suppressed swarm.
        self.assertIs(survival_preemption.emergency_hostiles(
            policy, board, strategic, physical), strategic)
        dying = parse_snapshot(self.raw(1344207), policy._monrace_knowledge)
        self.assertTrue(survival_preemption.endangering(
            policy, dying, [], policy._physical_hostiles(dying)))

    def test_a_new_level_with_the_same_floor_key_forgets_the_summoner(self):
        raw = self.raw(WALKOUT_TURNS[0])
        policy = self.policy_on(raw, latched=False)
        upper = copy.deepcopy(raw)
        upper["floor"]["level"] = 21
        upper["visible_monsters"] = []
        policy.prime(parse_snapshot(upper, policy._monrace_knowledge))
        # Back on 22F: a newly generated level under the same key.
        revisit = copy.deepcopy(raw)
        revisit["turn"] += 100
        revisit["visible_monsters"] = []
        board = parse_snapshot(revisit, policy._monrace_knowledge)
        policy.prime(board)
        self.assertEqual(policy._immobile_summoner_memory[1], {})
        self.assertIsNone(policy._immobile_summoner_key(board, []))
        self.assertEqual(policy._immobile_summoner_memory[1], {})


if __name__ == "__main__":
    unittest.main()
