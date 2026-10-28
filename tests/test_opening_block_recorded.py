"""Issue #47: Q34 completion captures reach Q1 with their existing supplies.

Only responses to posted commands and the completed-shopping latch are
constructed. Character stats, inventory, town terrain and skill are captured.
"""
import tests  # noqa: F401
import copy
import gzip
import json
from dataclasses import replace
from pathlib import Path

from hengbot.model import parse_snapshot, _GRID_TERRAIN_NAMES
from hengbot.policy_constants import QUEST_STATUS_TAKEN, QUEST_STATUS_COMPLETED
from hengbot.quest_entry_requirements import allows_overweight_travel
from tests import test_opening_route_r2_recorded as round2
from tests import test_opening_route_r3_recorded as round3
import tests.test_input_executor as executor_harness


class OpeningBlockRecordedTest(executor_harness.ProductionHarness):
    post = round2.OpeningRouteR2RecordedTest.post
    shelf_screen = staticmethod(round2.OpeningRouteR2RecordedTest.shelf_screen)

    @classmethod
    def setUpClass(cls):
        round2.OpeningRouteR2RecordedTest.setUpClass()
        with gzip.open(Path(__file__).with_name("fixtures") / "opening-block-20261028.json.gz",
                       "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def case(self, tag):
        policy, _ = round2.OpeningRouteR2RecordedTest().case("1")
        raw = copy.deepcopy(self.cases[tag]["snapshot"])
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        policy.consume_skill_knowledge(self.cases[tag]["skill"])
        # DECLARED CONSTRUCTED: resume after the already purchased mining kit,
        # without repeating the optional supplier survey after a restart.
        policy._opening_q1_kit_bought = True
        return policy, raw

    def enter(self, tag, five_only=False):
        policy, raw = self.case(tag)
        if five_only:
            # DECLARED CONSTRUCTED: exactly the owner's five throwing torches;
            # keep their recorded fuel, kit, stats and purse.
            torch = next(it for it in raw["inventory"] if it.get("tval") == 39
                         and it.get("sval") == 0)
            raw["inventory"] = [it for it in raw["inventory"]
                                if not (it.get("tval") == 39 and it.get("sval") == 0)]
            raw["inventory"].append(dict(torch, count=5))
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(board.player.level, 7)
        self.assertTrue(policy._fixed_quest_ready(board, 1), policy.fixed_quest_readiness_state())
        key = str(policy.choose_key(board))
        if policy.last_reason == "opening-q1:equip-light":
            following = round2.OpeningRouteR2RecordedTest().equip_reply(raw, key)
            self.post(policy, raw, key, following)
            raw = following
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual(policy.last_reason, "fixedquest:request:approach", key)
        # DECLARED CONSTRUCTED: walking finishes beside Q1's request building.
        following = copy.deepcopy(raw)
        following["player"].update(y=27, x=98)
        following["turn"] += 1
        self.post(policy, raw, key, following)
        raw = following
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), ("8q\x1b", "fixedquest:request"))
        # DECLARED CONSTRUCTED: successful request exposes the quest entrance.
        accepted = copy.deepcopy(raw)
        accepted["progress"]["quests"].append(dict(id=1, status=QUEST_STATUS_TAKEN,
                                                    fixed=True, level=5, type=6, name="Q1"))
        accepted["player"]["y"] -= 1
        accepted["turn"] += 1
        cell = next(c for c in accepted["grid_map"]["cells"] if c.get("p") == 1)
        cell["q"] = 1
        palette = accepted["grid_map"]["palette"]
        base = next(run[3] for run in accepted["grid_map"]["runs"]
                    if run[0] == cell["y"] and run[1] <= cell["x"] < run[1] + run[2])
        terrain = list(palette[base])
        terrain[2] |= 1 << _GRID_TERRAIN_NAMES.index("quest_enter")
        palette.append(terrain)
        accepted["grid_map"]["runs"].append([cell["y"], cell["x"], 1, len(palette)-1])
        self.post(policy, raw, key, accepted)
        # DECLARED CONSTRUCTED: town walking arrives on that emitted entrance.
        accepted["player"].update(y=cell["y"], x=cell["x"])
        key = str(policy.choose_key(parse_snapshot(accepted, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), (">", "quest:enter"))
        inside = round3.OpeningRouteR3RecordedTest.inside_reply(policy, accepted)
        self.post(policy, accepted, key, inside)

    def test_each_recorded_stop_accepts_and_enters_through_follow_executor(self):
        for tag in self.cases:
            with self.subTest(capture=tag):
                self.assertEqual(self.cases[tag]["before"]["key"], "")
                self.assertEqual(self.cases[tag]["before"]["fixedquest_readiness"]["reason"],
                                 "overweight" if tag == "a382" else "light-oil")
                self.enter(tag)

    def test_five_torches_are_sufficient_without_oil_or_potions(self):
        for tag in self.cases:
            with self.subTest(capture=tag):
                self.enter(tag, five_only=True)

    def test_existing_no_healing_tier_already_waives_the_recorded_potion_shortage(self):
        for tag in self.cases:
            policy, raw = self.case(tag)
            board = parse_snapshot(raw, policy._monrace_knowledge)
            self.assertTrue(policy._approved_strategy_force_ready(board, policy.approved_quest_strategy(1)))
            force = policy.fixed_quest_readiness_state()["strategy_force"]
            self.assertEqual(force["failed"], [])
            self.assertEqual(force["speed_potions"], {"measured": 0, "required": 1})
            self.assertEqual(force["heal_potions"], {"measured": 0, "required": 2})

    def test_light_relaxation_requires_a_usable_carried_torch(self):
        policy, raw = self.case("a381")
        # DECLARED CONSTRUCTED: no usable fuel remains; lit throwing items
        # still satisfy the throwing predicate, which reads the emitted flags.
        for it in raw["inventory"]:
            if it.get("tval") == 39:
                it["light_turns"] = 99
        self.assertFalse(policy._fixed_quest_ready(parse_snapshot(raw, policy._monrace_knowledge), 1))
        self.assertEqual(policy.fixed_quest_readiness_state()["reason"], "light-oil")

    def test_completed_q1_does_not_relax_later_travel_weight(self):
        policy, raw = self.case("a382")
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertTrue(allows_overweight_travel(policy, board))
        # DECLARED CONSTRUCTED: Q1 has completed; its reward/later travel has
        # the ordinary weight gate even though its profile permits acceptance.
        quests = dict(board.quests)
        quests[1] = replace(policy._known_fixed_quests(board)[1], status=QUEST_STATUS_COMPLETED)
        self.assertFalse(allows_overweight_travel(policy, replace(board, quests=quests)))
