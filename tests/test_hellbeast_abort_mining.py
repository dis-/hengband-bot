"""A mining run that meets the Greater Hell-Beast ends (owner 2026-10-31).

Owner: 「採掘中に『グレーター・ヘル=ビースト』に出会ったら採掘を切り上げて
地上に戻る。序盤の攻撃力では倒せないし非効率。」

Recorded: n1-c life-045 (zombie Magic-Eater Lv7, build 475bc157b) mining on
Yeek cave 1F (mode "mine", 12 of 16 veins collected).  The unique race 39
came into view asleep at turn 136152 and the bot kept mining
(fundraise:seek-treasure); from 136186 it threw torches at it
(ranged:throw-torch), then fired devices and meleed it for thousands of game
turns.  Both boards, the knowledge rows and the race row are frozen in
tests/fixtures/me-hellbeast-mining-20261030.json.gz (see
tests/extract_hellbeast_mining_fixture.py); every decision goes through the
public ``choose_key`` and the abort key through the production executor.

DECLARED RECONSTRUCTED: the mining-run state the departure sets (mode
"mine", one planned run, the detection marked read on this floor).  DECLARED
CONSTRUCTED: the warrior variant (the recorded board with class_id 1), the
not-mining variant (the fundraising mode cleared), the executor's reply (the
board unchanged, ten game turns later), and the town arrival (the same
life's recorded Outpost board of turn 209432 and its knowledge rows from
tests/fixtures/me-stockout-run-20261031.json.gz, following the abort board).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot.cli import _ExecutorInputPort, SendResult, _transport_key
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import ConservativePolicy
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen


FIXTURE = Path(__file__).with_name("fixtures") / "me-hellbeast-mining-20261030.json.gz"
TOWN_FIXTURE = Path(__file__).with_name("fixtures") / "me-stockout-run-20261031.json.gz"
HELL_BEAST = 39
WARRIOR = 1
ABORT = "fundraise:abort-unbeatable-unique:"
ATTACK_PREFIXES = ("v", "f", "m", "a", "u", "z", "E", "t", "+")


class HellbeastAbortMiningTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        with gzip.open(TOWN_FIXTURE, "rt", encoding="utf-8") as stream:
            town = json.load(stream)
        cls.town, cls.town_knowledge = town["town"], town["town_knowledge"]
        cls.races = {}
        for key, facts in cls.case["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            cls.races[int(key)] = MonraceKnowledge(**facts)

    def raw(self, name, class_id=None):
        raw = copy.deepcopy(self.case[name])
        if class_id is not None:
            raw["player"]["class_id"] = class_id
        return raw

    def policy(self, raw, *, mining=True):
        policy = ConservativePolicy(monrace_knowledge=dict(self.races))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.prime(board)
        skill, home = self.case["knowledge"]
        policy.consume_skill_knowledge(skill)
        policy.consume_home_knowledge(_parse_items(home["knowledge"]["items"], protocol=3))
        # DECLARED RECONSTRUCTED / CONSTRUCTED (module docstring).
        policy._fundraising_mode = "mine" if mining else None
        policy._planned_mining_runs, policy._mining_runs_completed = 1, 0
        policy._mining_scroll_used_floor = board.floor_key
        return policy

    @staticmethod
    def decide(policy, raw):
        return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))

    def post(self, policy, raw, key):
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), _transport_key(key, True))

    def assert_not_engaged(self, raw, key):
        """The key is a movement step that does not enter the unique's cell."""
        self.assertFalse(key.startswith(ATTACK_PREFIXES), key)
        self.assertEqual(len(key), 1, key)
        self.assertIn(key, "12346789", key)
        dx = {"1": -1, "4": -1, "7": -1, "3": 1, "6": 1, "9": 1}.get(key, 0)
        dy = {"7": -1, "8": -1, "9": -1, "1": 1, "2": 1, "3": 1}.get(key, 0)
        player, beast = raw["player"], raw["visible_monsters"][0]
        self.assertNotEqual((player["x"] + dx, player["y"] + dy), (beast["x"], beast["y"]))

    def test_capture_pins_the_recorded_scene(self):
        decisions = self.case["decisions"]
        self.assertEqual((decisions["136152"]["reason"], decisions["136152"]["fundraising"]["mode"]),
                         ("fundraise:seek-treasure", "mine"))
        self.assertEqual((decisions["136186"]["reason"], decisions["136186"]["key"]),
                         ("ranged:throw-torch", "vg9"))
        for name in ("sighted", "attack"):
            raw = self.case[name]
            self.assertEqual([m["race_id"] for m in raw["visible_monsters"]], [HELL_BEAST])
            self.assertEqual((raw["floor"]["dungeon_id"], raw["floor"]["level"]), (2, 1))
        race = self.races[HELL_BEAST]
        self.assertIn("UNIQUE", race.flags)
        self.assertEqual((race.max_hp, race.max_melee_damage), (1500, 0))

    def test_mining_run_meeting_it_takes_the_fundraising_exit(self):
        for name in ("sighted", "attack"):
            for class_id in (None, WARRIOR):
                with self.subTest(board=name, class_id=class_id):
                    raw = self.raw(name, class_id)
                    policy = self.policy(raw)
                    key = self.decide(policy, raw)
                    self.assertTrue(policy.last_reason.startswith(ABORT), policy.last_reason)
                    self.assertTrue(policy._returning_to_town)
                    self.assertEqual(policy._mining_abort_floor, (2, 1, 0))
                    self.assert_not_engaged(raw, key)
                    self.post(policy, raw, key)

    def test_not_mining_is_unchanged(self):
        for name in ("sighted", "attack"):
            with self.subTest(board=name):
                raw = self.raw(name)
                policy = self.policy(raw, mining=False)
                self.decide(policy, raw)
                self.assertFalse(policy.last_reason.startswith(ABORT), policy.last_reason)
                self.assertTrue(policy.last_reason.startswith("combat:avoid-unprofitable-unique-"),
                                policy.last_reason)
                self.assertIsNone(getattr(policy, "_mining_abort_floor", None))

    def test_aborted_run_is_not_counted(self):
        for aborted in (True, False):
            with self.subTest(aborted=aborted):
                raw = self.raw("attack")
                policy = self.policy(raw)
                policy._supply_stockout_gold_target = 1000
                cycles = policy._supply_stockout_cycles
                if aborted:
                    policy.confirm_key_posted(self.decide(policy, raw))
                    self.assertEqual(policy._mining_abort_floor, (2, 1, 0))
                else:
                    without = copy.deepcopy(raw)
                    without["visible_monsters"] = []
                    policy.confirm_key_posted(self.decide(policy, without))
                    self.assertIsNone(getattr(policy, "_mining_abort_floor", None))
                skill, home = self.town_knowledge
                policy.consume_skill_knowledge(skill)
                policy.consume_home_knowledge(_parse_items(home["knowledge"]["items"], protocol=3))
                self.decide(policy, copy.deepcopy(self.town))
                self.assertEqual(policy._mining_runs_completed, 0 if aborted else 1)
                self.assertEqual(policy._supply_stockout_cycles, cycles + (0 if aborted else 1))
                self.assertIsNone(getattr(policy, "_mining_abort_floor", None))


if __name__ == "__main__":
    unittest.main()
