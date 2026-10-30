"""D21: recorded n1-c Magic-Eater deaths on Yeek cave 1F (2026-10-30).

Boards, decision rows, terrain and modes are recorded
(tests/fixtures/me-mining-death-20261030.json.gz, see
tests/extract_me_mining_death.py).  Lives 8, 9 and 11 meleed giant white
mice, an insect swarm and small kobolds to death while carrying an absorbed
Magic Missile, attack wands and lit torches.  Life 16 walked, explored and
picked a locked door with an awake yeek hitting it: the floor was latched as
a breeder breakthrough, whose fundraising floor exit was consulted above the
flee and melee rungs.

DECLARED CONSTRUCTED: the remembered terrain and the modes come from the
checkpoint written at each stop, not at the decided board; life 16's
``_breeder_breakthrough_floor`` is not exported and is restored from the
recorded rows (``test_life016_latch_reproduces_the_recorded_return`` pins
that the latch alone yields the recorded fundraising decisions).  Replies to
posted keys are constructed from the game's prompts (cmd-magiceat.cpp,
get_aim_dir).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest
from unittest import mock

from hengbot import survival_preemption
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.magic_eater import MISSILE_REASON
from hengbot.me_ranged_first import TORCH_REASON, WAND_REASON
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen
from tests.test_magic_eater_o3 import powers, prompt

FIXTURE = Path(__file__).parent / "fixtures" / "me-mining-death-20261030.json.gz"
WARRIOR = 1
YEEK_FLOOR = (2, 1, 0)


class MagicEaterMiningDeathRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.races = {}
        for key, facts in cls.data["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            cls.races[int(key)] = MonraceKnowledge(**facts)

    def raw(self, life, turn, *, class_id=None):
        raw = copy.deepcopy(self.data["cases"][life]["boards"][str(turn)])
        if class_id is not None:
            raw["player"]["class_id"] = class_id
        return raw

    def recorded(self, life, turn):
        return self.data["cases"][life]["decisions"][str(turn)]

    def policy(self, life, raw, *, breakthrough=False):
        case = self.data["cases"][life]
        policy = HengbotPolicy(monrace_knowledge=dict(self.races))
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        terrain = case["terrain"]
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in terrain[f"{name}_t"])
        policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
        for name, value in case["modes"].items():
            setattr(policy, name, value)
        if breakthrough:
            # DECLARED CONSTRUCTED (module docstring).
            policy._breeder_breakthrough_floor = YEEK_FLOOR
        return policy

    def choose(self, policy, raw):
        # The captured process already held the skill knowledge.
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))

    def post(self, policy, raw, key, screens):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [*screens, command_screen(raw["turn"] + 10)]
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10)
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        return game, port

    def fire_missile(self, policy, raw, key):
        direction = key[-1]
        game, _ = self.post(policy, raw, key, [
            prompt("[A] staff, [B] wand, [C] rod:"), powers(3),
            prompt("Direction?", "direction", can_choose_target=True)])
        self.assertEqual(game.accepted, ["m", "B", "p", direction])

    def adjacent_direction(self, policy, raw, life):
        board = parse_snapshot(raw, policy._monrace_knowledge)
        adjacent = [monster for monster in board.visible_monsters
                    if board.player.position.distance_to(monster.position) <= 1]
        self.assertTrue(adjacent, life)
        return {policy._direction_key(board.player.position, m.position) for m in adjacent}

    def test_recorded_rows_meleed_while_ranged_power_was_carried(self):
        expected = {
            ("life-008", 805338): "melee", ("life-008", 805349): "melee",
            ("life-009", 219660): "flee:cornered-attack",
            ("life-009", 219724): "emergency:cornered-attack",
            ("life-011", 186766): "melee", ("life-011", 187358): "emergency:cornered-attack",
            ("life-016", 94171): "fundraise:seek-upstairs-explore",
            ("life-016", 94285): "fundraise:open-upstairs-door",
        }
        for (life, turn), reason in expected.items():
            with self.subTest(life=life, turn=turn):
                row = self.recorded(life, turn)
                self.assertEqual(row["reason"], reason)
                raw = self.raw(life, turn)
                self.assertEqual(raw["player"]["class_id"], 16)
                self.assertIn(raw["player"]["level"], (7, 8))
                board = parse_snapshot(raw, self.races)
                self.assertEqual(board.floor_key, YEEK_FLOOR)
                adjacent = [m for m in board.visible_monsters
                            if board.player.position.distance_to(m.position) <= 1]
                self.assertTrue(adjacent)
        # The packs held charged attack wands and spare lit torches.
        names = {item["name"] for item in self.raw("life-011", 187358)["inventory"]}
        self.assertIn("マジック・ミサイルの魔法棒 (17回分)", names)
        self.assertEqual(self.raw("life-011", 187358)["player"]["hp"], 13)

    def test_cornered_magic_eater_fires_the_absorbed_missile(self):
        for life, turn in (("life-011", 187358), ("life-009", 219724),
                           ("life-008", 805349), ("life-011", 186766)):
            with self.subTest(life=life, turn=turn):
                raw = self.raw(life, turn)
                policy = self.policy(life, raw)
                key = self.choose(policy, raw)
                self.assertEqual(policy.last_reason, MISSILE_REASON)
                self.assertTrue(key.startswith("mBp"), key)
                self.assertIn(key[-1], self.adjacent_direction(policy, raw, life))
                self.fire_missile(policy, raw, key)

    def test_empty_missile_aims_a_carried_attack_wand(self):
        for life, turn, slot in (("life-011", 187358, "d"), ("life-009", 219724, "f"),
                                 ("life-008", 805349, "h")):
            with self.subTest(life=life, turn=turn):
                raw = self.raw(life, turn)
                # The executor's observation of an empty power list.
                raw["_magic_eater_wand_charges"] = 0
                policy = self.policy(life, raw)
                key = self.choose(policy, raw)
                self.assertEqual(policy.last_reason, WAND_REASON)
                self.assertEqual(key[:2], "a" + slot)
                self.assertIn(key[-1], self.adjacent_direction(policy, raw, life))
                game, _ = self.post(policy, raw, key, [])
                self.assertEqual("".join(game.accepted), key)

    def test_without_wands_a_spare_lit_torch_is_thrown(self):
        raw = self.raw("life-011", 187358)
        raw["_magic_eater_wand_charges"] = -1
        # DECLARED CONSTRUCTED: the carried wands are removed.
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] != 65]
        policy = self.policy("life-011", raw)
        key = self.choose(policy, raw)
        self.assertEqual(policy.last_reason, TORCH_REASON)
        torch = next(item for item in raw["inventory"] if item["tval"] == 39 and item["sval"] == 0)
        self.assertEqual(key, "v" + torch["slot"] + "3")
        game, _ = self.post(policy, raw, key, [])
        self.assertEqual("".join(game.accepted), key)

    def test_warrior_boards_keep_melee(self):
        for life, turn in (("life-011", 187358), ("life-009", 219660), ("life-011", 186766)):
            with self.subTest(life=life, turn=turn):
                raw = self.raw(life, turn, class_id=WARRIOR)
                policy = self.policy(life, raw)
                key = self.choose(policy, raw)
                row = self.recorded(life, turn)
                self.assertEqual((key, policy.last_reason), (row["key"], row["reason"]))

    def test_life016_latch_reproduces_the_recorded_return(self):
        # With the survival gate disabled the breakthrough latch alone yields
        # the recorded fundraising decisions beside the attacking yeek.
        with mock.patch.object(survival_preemption, "preempts", return_value=False):
            for turn in (94171, 94285):
                with self.subTest(turn=turn):
                    raw = self.raw("life-016", turn)
                    policy = self.policy("life-016", raw, breakthrough=True)
                    key = self.choose(policy, raw)
                    self.assertTrue(policy.last_reason.startswith("fundraise:"), policy.last_reason)
        raw = self.raw("life-016", 94285)
        policy = self.policy("life-016", raw, breakthrough=True)
        with mock.patch.object(survival_preemption, "preempts", return_value=False):
            self.assertEqual(self.choose(policy, raw), self.recorded("life-016", 94285)["key"])

    def test_life016_attacked_player_fights_before_the_return(self):
        for class_id, expected in ((16, MISSILE_REASON), (WARRIOR, "melee")):
            for turn in (94171, 94285):
                with self.subTest(class_id=class_id, turn=turn):
                    raw = self.raw("life-016", turn, class_id=class_id)
                    policy = self.policy("life-016", raw, breakthrough=True)
                    key = self.choose(policy, raw)
                    self.assertEqual(policy.last_reason, expected)
                    direction = self.adjacent_direction(policy, raw, "life-016")
                    self.assertIn(key[-1], direction)
                    preempted = policy._decision_survival_preempted
                    self.assertEqual(preempted[0], raw["turn"])
                    self.assertIn("_finish_mining_floor", preempted[1])
                    if class_id == WARRIOR:
                        game, _ = self.post(policy, raw, key, [])
                        self.assertEqual("".join(game.accepted), key)
                    else:
                        self.fire_missile(policy, raw, key)

    def test_unattacked_return_is_not_preempted(self):
        # DECLARED CONSTRUCTED: the yeek is asleep; the return keeps its board.
        raw = self.raw("life-016", 94285, class_id=WARRIOR)
        for monster in raw["visible_monsters"]:
            monster["asleep"] = True
        policy = self.policy("life-016", raw, breakthrough=True)
        self.choose(policy, raw)
        self.assertTrue(policy.last_reason.startswith("fundraise:"), policy.last_reason)


if __name__ == "__main__":
    unittest.main()
