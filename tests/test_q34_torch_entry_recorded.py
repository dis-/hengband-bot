"""Issue #47: recorded warrior board, public chooser and production posting.

Only replies to newly posted travel, acceptance and entry are constructed.
The recorded combat stats, inventory and gold remain unchanged.
"""
import tests  # noqa: F401
import copy
import gzip
import json
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.model import parse_snapshot, _GRID_TERRAIN_NAMES
from hengbot.policy_constants import QUEST_STATUS_TAKEN
from hengbot.quest_entry_requirements import carried_torch_entry_ready
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_input_executor as executor_harness


class Q34TorchEntryRecordedTest(executor_harness.ProductionHarness):
    post = lv7.Lv7TownStopRecordedTest.post
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        with gzip.open(Path(__file__).with_name("fixtures") /
                       "q34-torch-entry-20261029.json.gz", "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def boundary(self):
        return lv7.Lv7TownStopRecordedTest().boundary(self.case)

    def test_recorded_warrior_accepts_and_enters_without_lantern_or_oil(self):
        policy, raw = self.boundary()
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual((board.player.class_id, board.player.level, board.player.gold), (0, 1, 55))
        self.assertEqual(self.case["recorded_readiness"]["reason"], "light-torch-only")
        self.assertFalse(any(it.is_lantern or it.is_oil for it in board.inventory + board.equipment))
        self.assertTrue(policy._fixed_quest_ready(board, 34), policy.fixed_quest_readiness_state())
        accepted = False
        for _ in range(8):
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            reason = policy.last_reason
            following = copy.deepcopy(raw)
            following["turn"] += 1
            if reason == "fixedquest:request:approach":
                goal = min(policy._fixed_quest_building_positions(
                    parse_snapshot(raw, policy._monrace_knowledge), 34))
                following["player"].update(y=goal.y + 1, x=goal.x)
            elif reason == "fixedquest:request":
                self.assertEqual(key, "8q\x1b")
                accepted = True
                following["progress"]["quests"].append(
                    dict(id=34, status=QUEST_STATUS_TAKEN, fixed=True, level=5, type=6, name="Q34"))
                following["player"]["y"] -= 1
                goal = min(policy._fixed_quest_building_positions(
                    parse_snapshot(raw, policy._monrace_knowledge), 34))
                palette = following["grid_map"]["palette"]
                base = next(run[3] for run in following["grid_map"]["runs"]
                            if run[0] == goal.y and run[1] <= goal.x < run[1] + run[2])
                terrain = list(palette[base])
                terrain[2] |= 1 << _GRID_TERRAIN_NAMES.index("quest_enter")
                palette.append(terrain)
                following["grid_map"]["runs"].append([goal.y, goal.x, 1, len(palette) - 1])
                following["grid_map"]["cells"].append(dict(y=goal.y, x=goal.x, q=34))
            elif reason == "quest:enter:approach":
                goal = min(policy._fixed_quest_entrance_positions(
                    parse_snapshot(raw, policy._monrace_knowledge), 34))
                following["player"].update(y=goal.y, x=goal.x)
            elif reason == "quest:enter":
                self.assertTrue(accepted)
                self.assertEqual(key, ">")
                following["floor"].update(in_town=False, quest_id=34, level=5)
                self.post(policy, raw, key, following)
                return
            else:
                self.fail((key, reason, policy.fixed_quest_readiness_state()))
            self.post(policy, raw, key, following)
            raw = following
        self.fail("Q34 entry exceeded eight decisions")

    def test_once_quest_without_opening_light_contract_refuses_torch_entry(self):
        policy, raw = self.boundary()
        # DECLARED CONSTRUCTED: a Q2-like once quest has no opening lantern
        # contract. Keep the real force calculation and captured warrior kit.
        profile = policy._quest_strategies[34]
        force = dict(profile.required_force)
        force.pop("entry_requirements")
        plan = dict(profile.engagement_plan)
        plan.pop("opening_light")
        policy._quest_strategies[34] = replace(profile, required_force=force, engagement_plan=plan)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertFalse(policy._fixed_quest_ready(board, 34))
        self.assertEqual(policy.fixed_quest_readiness_state()["reason"], "light-torch-only")
        key = str(policy.choose_key(board))
        self.assertNotIn(policy.last_reason, ("fixedquest:request", "quest:enter", "opening-q34:wait"))
        self.assertNotEqual(key, ">")
        following = copy.deepcopy(raw)
        following["turn"] += 1
        self.post(policy, raw, key, following)

    def test_injured_warrior_recovers_instead_of_waiting_for_readiness(self):
        policy, raw = self.boundary()
        board = parse_snapshot(raw, policy._monrace_knowledge)
        # DECLARED CONSTRUCTED: one HP lost on the otherwise ready boundary.
        board = replace(board, player=replace(board.player, hp=board.player.max_hp - 1))
        from hengbot.policy_constants import REST_MACRO
        self.assertEqual(policy._opening_q34_town_key(board, []), REST_MACRO)
        self.assertEqual(policy.last_reason, "town:recover")
        self.assertEqual(policy.fixed_quest_readiness_state()["reason"], "not-full-hp")

    def test_light_rejection_shops_or_stops_after_supplier_routes_are_exhausted(self):
        for exhausted in (False, True):
            with self.subTest(exhausted=exhausted):
                policy, raw = self.boundary()
                board = parse_snapshot(raw, policy._monrace_knowledge)
                # DECLARED CONSTRUCTED: all torches are below the entry floor;
                # the same twenty throwing items still meet the force gate.
                board = replace(board, inventory=[
                    replace(it, fuel=99) if it.is_torch else it for it in board.inventory
                ], equipment=[
                    replace(it, fuel=99) if it.is_torch else it for it in board.equipment
                ])
                if exhausted:
                    # DECLARED CONSTRUCTED: each supplier was observed without
                    # an effect at this same boundary, exhausting existing routes.
                    for store in range(10):
                        policy._town_store_attempted[store] = board.turn
                        policy._town_visit_ledger.nonhome_attempted_without_effect[store] = (
                            policy._town_observable_effect_state(board))
                key = policy._opening_q34_town_key(board, [])
                details = policy.fixed_quest_readiness_state()
                self.assertFalse(details["verdict"])
                self.assertEqual(details["reason"], "light-torch-only")
                self.assertEqual(details["strategy_force"]["failed"], [])
                if exhausted:
                    self.assertEqual((key, policy.last_reason), ("5", "livelock:exhausted"))
                else:
                    self.assertNotEqual(key, "5")
                    self.assertIn(policy.last_reason, ("shop:travel", "shop:approach"))

    def test_torch_contract_is_quest_specific_and_checks_each_safety_field(self):
        policy, raw = self.boundary()
        board = parse_snapshot(raw, policy._monrace_knowledge)
        profile = policy.approved_quest_strategy(34)
        self.assertTrue(carried_torch_entry_ready(board, profile))
        self.assertFalse(carried_torch_entry_ready(board, policy.approved_quest_strategy(2)))
        torch = next(it for it in board.inventory if it.is_torch)
        for changes in ({"known": False}, {"fuel": 99}, {"is_cursed": True},
                        {"is_broken": True}, {"count": 0}):
            with self.subTest(changes=changes):
                altered = replace(board, inventory=[replace(torch, **changes)])
                self.assertFalse(carried_torch_entry_ready(altered, profile))
        self.assertTrue(carried_torch_entry_ready(
            replace(board, inventory=[replace(torch, fuel=100)]), profile))


if __name__ == "__main__":
    unittest.main()
