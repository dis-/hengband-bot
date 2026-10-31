"""D45: an interrupted digger swap is rolled back before any fight.

Owner 2026-10-31: 「n1-cが素手で戦闘している。どういう退行？」 -- the character
must fight with its weapon.

Recorded: n1-c life-065 (zombie Magic-Eater Lv9, build aa56fccb0) mining on
Yeek cave 1F.  The mining loadout swap is two posts: 'ta' (take off the
Short Sword, fundraise:wield-digging-tool) at turn 778659, then the digger.
A breeding white worm mass (race 31) came into view at 778665;
fundraise:eliminate-multiplier, the Magic-Eater's ranged fire and melee took
every later turn with the main hand empty (still at 791632, 12:41).  The
boards, the skill row, the decision rows and the race row are frozen in
tests/fixtures/me-barehand-mining-20261031.json.gz
(tests/extract_barehand_mining_fixture.py).  Every decision goes through the
public ``choose_key`` and every posted key through the production executor.

DECLARED RECONSTRUCTED: the mining-run state the departure sets (mode
"mine", one planned run, the detection marked read on this floor) and the
quiet streak that admitted the recorded strip (MINING_THREAT_FREE_LIMIT).
DECLARED CONSTRUCTED: the executor's replies (the posted wield or takeoff
applied to the board, the pack relettered, ten game turns later); the
off-hand shield of the two-hand variant (the recorded 778659 and 778665
boards plus a Small Leather Shield, worn or in the pack); the strip-wait
board (the recorded 778665 board with the sword worn); the digger-in-hand
control (the recorded Shovel moved into the main hand); the quiet control
(the recorded 778665 board without its monsters); the restart choice (the
last recorded board with a Dagger carried ahead of the sword, and a cached
optimizer winner naming the sword).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import string
import unittest

from hengbot.cli import _ExecutorInputPort, SendResult, _transport_key
from hengbot.equipment_optimizer import (
    EvaluatedLoadout, Loadout, LoadoutMetrics, OptimizationResult, OwnedEquipment,
    equipment_identity,
)
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import MINING_THREAT_FREE_LIMIT
from hengbot.warrior_optimization import WarriorOptimizationPreparation
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen, prompt_screen


FIXTURE = Path(__file__).with_name("fixtures") / "me-barehand-mining-20261031.json.gz"
SWORD, SHOVEL, LEATHER_SHIELD, DAGGER = "ショート・ソード", "シャベル", "Small Leather Shield", "ダガー"
WORM_MASS = 31
STRIP = "fundraise:wield-digging-tool"
# hengbot.mining_loadout.REARM_REASON / STRIP_DEFERRED_REPORT, spelled out so
# the revert check (the module absent) runs every test instead of an import error.
REARM_REASON = "melee:rearm-empty-hand"
STRIP_DEFERRED_REPORT = "mining-loadout:strip-deferred-hostile-in-view"
ITEM_PROMPTS = {"w": "(Inven: a-n, ESC) どれを装備しますか?",
                "t": "(Equip: a-l, ESC) どれを装備からはずしますか?"}
SHIELD = {  # shaped like the recorded body armour row (no weapon proficiency)
    "ac": 2, "aware": True, "charges": 0, "charging": False, "count": 1,
    "damage_dice": {"num": 0, "sides": 0}, "fully_known": False,
    "inscription": "", "is_artifact": False, "is_bounty": False,
    "is_broken": False, "is_cursed": False, "is_ego": False,
    "is_equipment": True, "known": True, "known_flags": [],
    "name": "Small Leather Shield [2,+0]", "pval": 0, "slot": "sub_hand",
    "sval": 2, "to_a": 0, "to_d": 0, "to_h": 0, "tval": 34, "weight": 50,
}


def letter_of(raw, prefix):
    return next(item["slot"] for item in raw["inventory"] if item["name"].startswith(prefix))


def reletter(raw):
    for letter, item in zip(string.ascii_lowercase, raw["inventory"]):
        item["slot"] = letter
    return raw


def wielded(raw, prefix, slot):
    """The board after the pack item named ``prefix`` went into ``slot``."""
    after = copy.deepcopy(raw)
    item = next(i for i in after["inventory"] if i["name"].startswith(prefix))
    after["inventory"].remove(item)
    after["equipment"] = [i for i in after["equipment"] if i["slot"] != slot]
    after["equipment"].append(dict(item, slot=slot))
    after["turn"] += 10
    after["messages"] = []
    return reletter(after)


def taken_off(raw, slot):
    after = copy.deepcopy(raw)
    item = next(i for i in after["equipment"] if i["slot"] == slot)
    after["equipment"].remove(item)
    after["inventory"].append(dict(item, slot="?"))
    after["turn"] += 10
    after["messages"] = []
    return reletter(after)


def carrying(raw, item):
    board = copy.deepcopy(raw)
    board["inventory"].append(dict(copy.deepcopy(item), slot="?"))
    return reletter(board)


class BarehandMiningRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.races = {}
        for key, facts in cls.case["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            cls.races[int(key)] = MonraceKnowledge(**facts)

    def board(self, name):
        return copy.deepcopy(self.case["boards"][name])

    def policy(self, raw, *, mining=True):
        policy = ConservativePolicy(monrace_knowledge=dict(self.races))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.prime(board)
        policy.consume_skill_knowledge(copy.deepcopy(self.case["knowledge"]))
        if mining:
            # DECLARED RECONSTRUCTED (module docstring).
            policy._fundraising_mode = "mine"
            policy._planned_mining_runs, policy._mining_runs_completed = 1, 0
            policy._mining_scroll_used_floor = board.floor_key
            policy._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT
        return policy

    @staticmethod
    def decide(policy, raw):
        return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))

    def post(self, policy, raw, key, following):
        # cmd-equipment.cpp do_cmd_wield / do_cmd_takeoff open the item
        # source prompt; the hand chain needs no follow-up on these boards.
        prompts = [prompt_screen(ITEM_PROMPTS[key[0]])] if key[0] in ITEM_PROMPTS else []
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = prompts + [command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in prompts] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), _transport_key(key, True))
        self.assertTrue(policy.confirm_key_posted(key))

    def assert_fights(self, policy, raw):
        """The next decision on the re-armed board is no equipment command."""
        key = self.decide(policy, raw)
        self.assertNotEqual(policy.last_reason, REARM_REASON)
        self.assertFalse(key.startswith(("w", "t")), (key, policy.last_reason))
        return key

    def test_capture_pins_the_recorded_scene(self):
        decisions = self.case["decisions"]
        self.assertEqual([(row["reason"], row["key"]) for row in decisions["778659"]],
                         [(STRIP, "ta")])
        self.assertEqual([(row["reason"], row["key"]) for row in decisions["778665"]],
                         [("fundraise:eliminate-multiplier", "2")])
        self.assertEqual([row["reason"] for row in decisions["778697"]],
                         ["quest-strategy:ranged-fire:magic-eater", "melee"])
        self.assertEqual(decisions["778659"][0]["fundraising"]["mode"], "mine")
        worn = self.board("worn")
        self.assertEqual([item["name"][:len(SWORD)] for item in worn["equipment"]
                          if item["slot"] == "main_hand"], [SWORD])
        self.assertEqual(worn["visible_monsters"], [])
        for name in ("sighted", "adjacent", "latest"):
            raw = self.board(name)
            self.assertEqual([item for item in raw["equipment"]
                              if item["slot"] in ("main_hand", "sub_hand")], [])
            self.assertEqual({m["race_id"] for m in raw["visible_monsters"]}, {WORM_MASS})
            self.assertTrue(letter_of(raw, SWORD) and letter_of(raw, SHOVEL))
        self.assertIn("MULTIPLY", self.races[WORM_MASS].flags)

    def test_strip_interrupted_by_the_breeder_rearms_before_fighting(self):
        # The recorded chain: the strip, then the worm mass in view.
        worn, sighted = self.board("worn"), self.board("sighted")
        policy = self.policy(worn)
        key = self.decide(policy, worn)
        self.assertEqual((key, policy.last_reason), ("ta", STRIP))
        self.post(policy, worn, key, taken_off(worn, "main_hand"))
        key = self.decide(policy, sighted)
        self.assertEqual((key, policy.last_reason),
                         ("w" + letter_of(sighted, SWORD), REARM_REASON))
        armed = wielded(sighted, SWORD, "main_hand")
        self.post(policy, sighted, key, armed)
        self.assert_fights(policy, armed)

    def test_empty_hand_with_the_breeder_adjacent_rearms_first(self):
        # A fresh process (restart): the displaced weapon is not remembered.
        for name in ("adjacent", "latest"):
            raw = self.board(name)
            self.assertTrue(any(max(abs(m["x"] - raw["player"]["x"]),
                                    abs(m["y"] - raw["player"]["y"])) == 1
                                for m in raw["visible_monsters"]))
            for mining in (True, False):
                with self.subTest(board=name, mining=mining):
                    policy = self.policy(raw, mining=mining)
                    key = self.decide(policy, raw)
                    self.assertEqual((key, policy.last_reason),
                                     ("w" + letter_of(raw, SWORD), REARM_REASON))
                    self.post(policy, raw, key, wielded(raw, SWORD, "main_hand"))

    def test_restart_rearm_takes_the_remembered_then_the_optimizer_weapon(self):
        # DECLARED CONSTRUCTED: the last recorded board with a Dagger carried
        # ahead of the Short Sword.
        raw = self.board("latest")
        sword = next(i for i in raw["inventory"] if i["name"].startswith(SWORD))
        raw["inventory"].insert(0, dict(copy.deepcopy(sword), name=DAGGER + " (1d4) (+0,+0)",
                                        sval=4, damage_dice={"num": 1, "sides": 4}, weight=12))
        raw = reletter(raw)
        parsed = parse_snapshot(copy.deepcopy(raw), dict(self.races))
        carried_sword = next(i for i in parsed.inventory if i.name.startswith(SWORD))
        cases = {
            "nothing-known": (None, DAGGER),       # the established first-weapon fallback
            "optimizer": ("optimizer", SWORD),     # the cached optimizer winner (DECLARED CONSTRUCTED)
            "remembered-not-carried": ("gone", DAGGER),
            "remembered": ("remembered", SWORD),
        }
        for case, (setup, expected) in cases.items():
            with self.subTest(case=case):
                policy = self.policy(raw)
                if setup == "optimizer":
                    optimal = Loadout(
                        (("main_hand", OwnedEquipment("optimal-sword", carried_sword, "pack")),),
                        "one_handed")
                    policy._equipment_optimization_preparation = WarriorOptimizationPreparation(
                        current=optimal, transaction=None, blockers=(),
                        result=OptimizationResult(
                            best=EvaluatedLoadout(optimal, LoadoutMetrics(1.0, 1.0, 1.0)),
                            alternatives=(), pareto_frontier=(), dominated_item_ids=frozenset(),
                            combinations_considered=1, combinations_evaluated=1,
                            invalid_combinations=0, elapsed_seconds=0.0, timed_out=False,
                            incomplete_item_ids=frozenset()))
                elif setup == "gone":
                    policy._normal_weapon_identity = "equipped:not-carried:0"
                elif setup == "remembered":
                    policy._normal_weapon_identity = equipment_identity(carried_sword)
                key = self.decide(policy, raw)
                self.assertEqual((key, policy.last_reason),
                                 ("w" + letter_of(raw, expected), REARM_REASON))

    def test_two_hand_strip_interrupted_rearms_both_hands_then_fights(self):
        # DECLARED CONSTRUCTED: the recorded boards with a shield; the worm
        # mass comes into view on the recorded 778665 board.
        worn = self.board("worn")
        worn["equipment"].append(copy.deepcopy(SHIELD))
        sighted = self.board("sighted")
        for interrupted in ("after-ta", "after-tb"):
            with self.subTest(interrupted=interrupted):
                policy = self.policy(worn)
                key = self.decide(policy, worn)
                self.assertEqual((key, policy.last_reason), ("ta", STRIP))
                bare_main = taken_off(worn, "main_hand")
                self.post(policy, worn, key, bare_main)
                board = copy.deepcopy(sighted)
                board["equipment"].append(copy.deepcopy(SHIELD))
                if interrupted == "after-tb":
                    key = self.decide(policy, bare_main)
                    self.assertEqual((key, policy.last_reason), ("tb", STRIP))
                    self.post(policy, bare_main, key, taken_off(bare_main, "sub_hand"))
                    board = carrying(sighted, SHIELD)
                key = self.decide(policy, board)
                self.assertEqual((key, policy.last_reason),
                                 ("w" + letter_of(board, SWORD), REARM_REASON))
                armed = wielded(board, SWORD, "main_hand")
                self.post(policy, board, key, armed)
                if interrupted == "after-tb":
                    key = self.decide(policy, armed)
                    self.assertEqual((key, policy.last_reason),
                                     ("w" + letter_of(armed, LEATHER_SHIELD), REARM_REASON))
                    shielded = wielded(armed, LEATHER_SHIELD, "sub_hand")
                    self.post(policy, armed, key, shielded)
                    armed = shielded
                self.assert_fights(policy, armed)

    def test_strip_waits_while_a_hostile_is_in_view(self):
        # The breakout reaches the same strip without the mining quiet streak.
        # DECLARED CONSTRUCTED: the recorded 778665 board with the sword worn.
        board = wielded(self.board("sighted"), SWORD, "main_hand")
        policy = self.policy(board, mining=False)
        snapshot = parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge)
        self.assertTrue(snapshot.visible_monsters)
        self.assertIsNone(policy._wield_digging_tool_key(snapshot, "breakout:wield-digging-tool"))
        self.assertEqual(policy._equipment_mutation_result.report, STRIP_DEFERRED_REPORT)
        quiet = parse_snapshot(self.board("worn"), policy._monrace_knowledge)
        self.assertEqual(policy._wield_digging_tool_key(quiet, "breakout:wield-digging-tool"), "ta")

    def test_control_digger_in_hand_keeps_the_approved_mining_combat_order(self):
        # Approved spec (2026-07-29): the diggers stay on while a missile
        # answers; the re-arm waits MINING_COMBAT_CONTACT_LIMIT contact decisions.
        raw = wielded(self.board("adjacent"), SHOVEL, "main_hand")
        raw["turn"] -= 10
        policy = self.policy(raw)
        key = self.decide(policy, raw)
        self.assertNotEqual(policy.last_reason, REARM_REASON)
        self.assertFalse(key.startswith("w"), (key, policy.last_reason))

    def test_control_quiet_empty_hand_continues_the_swap(self):
        raw = self.board("sighted")
        raw["visible_monsters"] = []
        policy = self.policy(raw)
        key = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("w" + letter_of(raw, SHOVEL), STRIP))


if __name__ == "__main__":
    unittest.main()
