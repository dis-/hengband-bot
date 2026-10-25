"""Issue #47: recorded observations plus explicitly constructed game replies.

The fixture contains the 287 incident rows, the 99 recorded old decisions, and
source-derived quest terrain. Counterfactual movement, trap questions and drops
are a deterministic test world, not a capture of an unperformed game run.
"""
import tests  # noqa: F401

import copy
import gzip
import io
import json
from pathlib import Path
import time
import unittest
from dataclasses import replace

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.model import Position, parse_snapshot, TVAL_CHEST
from hengbot.policy import HengbotPolicy
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.quest_knowledge import QuestBattlefield, QuestInfo
from hengbot.quest_strategies import load_quest_strategies
from tests.test_input_executor import ProductionHarness, FaithfulHookGame, command_screen, prompt_screen

FIXTURE = Path(__file__).with_name("fixtures") / "q34-collect-20261025.json.gz"


def captured():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def make_policy(data):
    facts = copy.deepcopy(data["quest"])
    terrain = facts.pop("battlefield")
    terrain["terrain"] = {(y, x): value for y, x, value in terrain["terrain"]}
    for name in ("entrance", "exit", "player_start", "reward_tile"):
        if terrain.get(name) is not None:
            terrain[name] = tuple(terrain[name])
    facts["battlefield"] = QuestBattlefield(**terrain)
    races = {}
    for race_id, values in data["monraces"].items():
        values = dict(values)
        for key in ("flags", "abilities"):
            values[key] = frozenset(values[key])
        values["blows"] = tuple(MonsterBlow(**blow) for blow in values["blows"])
        races[int(race_id)] = MonraceKnowledge(**values)
    policy = HengbotPolicy(quest_knowledge={34: QuestInfo(**facts)}, monrace_knowledge=races,
                          quest_strategies=load_quest_strategies(Path("strategy/quests")))
    return policy


def observe_until(policy, rows, boundary):
    for raw in rows[:boundary]:
        if raw["type"] == "knowledge":
            policy.consume_skill_knowledge(raw)
        else:
            policy._observe(policy._with_grid_memory(parse_snapshot(raw, policy._monrace_knowledge)))


class Q34CollectRecordedTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.data = captured()

    def post(self, policy, raw, key, following, *, auto_direction=False):
        """Real follow executor, fake transport, source-derived prompt frames."""
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        screens = []
        expected = [key]
        if key.startswith(("D", "o")) and len(key) == 2 and policy.last_reason.startswith("chest:"):
            expected = [key[0]] if auto_direction else [key[0], key[1]]
            if not auto_direction:
                screens.append(prompt_screen("Direction (Escape to cancel)?"))
        elif key.startswith("g") and len(key) > 1:
            expected = list(key)
            screens.extend(prompt_screen("(Floor: a-b, ESC) Get which item?") for _ in key[1:])
        # cmd-move.cpp does not ask the leave question on completed Q34.
        game.screens = screens + [command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in screens] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "q34-recorded-collect", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, {}), posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, expected)
        self.assertFalse(game.term_fifo)
        return game

    def test_recorded_invisible_swords_enter_shared_loot_candidates(self):
        policy = make_policy(self.data)
        observe_until(policy, self.data["rows"], 286)
        raw = self.data["rows"][286]
        board = parse_snapshot(raw, {})
        for pos in (Position(9, 9), Position(9, 11)):
            self.assertIn(pos, policy._known_loot)
            self.assertEqual(policy._with_grid_memory(board).grid_at(pos).object_count, 0)
        # DECLARED CONSTRUCTED: the chest is already processed; isolate the
        # remaining ordinary equipment from the independent chest procedure.
        policy._processed_chest_positions.add(Position(10, 9))
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "loot:seek-quest-sweep")
        self.assertIn(policy._loot_target, {Position(9, 9), Position(9, 11)})
        self.assertEqual(policy.decision_claim["owner"], "floor-loot")
        self.assertEqual(policy.decision_claim["goal"]["kind"], "Reach")
        self.assertEqual(policy.decision_claim["goal"]["cell"], [policy._loot_target.y, policy._loot_target.x])
        self.assertTrue(policy.decision_claim["rung"].startswith("_normal_loot_key"))
        self.assertIsNone(policy.decision_claim["violation"])
        self.post(policy, raw, key, dict(raw, turn=raw["turn"] + 10))

    def test_found_items_work_after_restart_without_loot_observation_history(self):
        policy = make_policy(self.data)
        # DECLARED CONSTRUCTED: terrain remembered by a restarted process,
        # but no previous object observations. found_items remains unchanged.
        board = parse_snapshot(self.data["rows"][286], {})
        terrain = self.data["quest"]["battlefield"]["terrain"]
        from policy_fixtures import grid
        grids = dict(board.grids)
        for y, x, kind in terrain:
            if kind != "wall":
                grids.setdefault(Position(y, x), grid(y, x))
        board = replace(board, grids=grids, player=replace(board.player, two_weapon_skill=0, shield_skill=0))
        policy._observe(policy._with_grid_memory(board))
        policy._processed_chest_positions.add(Position(10, 9))
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "loot:seek-quest-sweep")
        self.assertIn(policy._loot_target, {Position(9, 9), Position(9, 11)})

    def test_first_completed_record_prioritizes_reserved_chest_over_ruins(self):
        policy = make_policy(self.data)
        observe_until(policy, self.data["rows"], 188)
        raw = self.data["rows"][188]
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual(policy.last_reason, "chest:approach")
        self.assertEqual(policy._chest_position, Position(10, 9))
        self.assertEqual(policy.decision_claim["owner"], "floor-loot")
        self.assertEqual(policy.decision_claim["goal"]["kind"], "Reach")
        goal = Position(*policy.decision_claim["goal"]["cell"])
        self.assertEqual(goal.distance_to(policy._chest_position), 1)
        self.assertFalse(policy.decision_claim["goal_missing"])
        self.assertIsNone(policy.decision_claim["violation"])
        self.post(policy, raw, key, dict(raw, turn=raw["turn"] + 10))

    def test_quest_chest_away_from_reservation_is_still_processed(self):
        policy = make_policy(self.data)
        observe_until(policy, self.data["rows"], 286)
        raw = copy.deepcopy(self.data["rows"][286])
        # DECLARED CONSTRUCTED: another chest elsewhere on the same quest
        # floor. The preferred source coordinate is not an exclusion rule.
        raw["grid_map"]["found_items"] = [[9, 11, 1, 7]]
        key = str(policy.choose_key(parse_snapshot(raw, {})))
        self.assertEqual(policy._chest_position, Position(9, 11))
        self.assertEqual(policy.last_reason, "chest:approach")
        self.post(policy, raw, key, dict(raw, turn=raw["turn"] + 10))

    def test_reservation_matches_source_terrain_and_recorded_chest(self):
        policy = make_policy(self.data)
        pos = Position(*policy.approved_quest_strategy(34).engagement_plan["chest_position"])
        self.assertEqual(pos, Position(10, 9))
        terrain = policy._quest_knowledge[34].battlefield.terrain
        self.assertEqual(terrain[(10, 8)], "wall")
        self.assertEqual(terrain[(pos.y, pos.x)], "floor")
        self.assertIn([10, 9, 1, TVAL_CHEST], self.data["rows"][286]["grid_map"]["found_items"])

    def test_collect_swords_open_chest_collect_contents_then_exit(self):
        self.collect_from_recorded_row(286)

    def test_first_completed_board_collects_every_nonjunk_item_then_exits(self):
        self.collect_from_recorded_row(188)

    def collect_from_recorded_row(self, row_index):
        policy = make_policy(self.data)
        observe_until(policy, self.data["rows"], row_index)
        raw = copy.deepcopy(self.data["rows"][row_index])
        # DECLARED CONSTRUCTED: respond to the changed route on the recorded
        # final board. Only position, turn, floor objects and pickup inventory
        # evolve. The two chest drops are invented; contents were not recorded.
        objects = {(y, x): list(ts) for y, x, count, *ts in raw["grid_map"]["found_items"]}
        picked = []
        opened = False
        reasons = []
        steps = {"8": (-1, 0), "2": (1, 0), "4": (0, -1), "6": (0, 1),
                 "7": (-1, -1), "9": (-1, 1), "1": (1, -1), "3": (1, 1)}
        terrain = policy._quest_knowledge[34].battlefield.terrain
        blocked = {tuple(p) for p in policy.approved_quest_strategy(34).engagement_plan["avoid_door_positions"]}
        blocked.discard((4, 14))

        def render():
            raw["grid_map"]["found_items"] = [[y, x, len(ts), *ts] for (y, x), ts in objects.items()]
            raw["grid_map"]["cells"] = [dict(c, o=0, t=[]) for c in raw["grid_map"]["cells"] if "o" not in c]
            here = Position(raw["player"]["y"], raw["player"]["x"])
            for (y, x), ts in objects.items():
                if here.distance_to(Position(y, x)) <= 2:
                    raw["grid_map"]["cells"].append({"y": y, "x": x, "o": len(ts), "t": ts[:]})
            raw["messages"] = []

        render()
        for _ in range(600):
            before = copy.deepcopy(raw)
            key = str(policy.choose_key(parse_snapshot(before, {})))
            reason = policy.last_reason
            reasons.append(reason)
            y, x = raw["player"]["y"], raw["player"]["x"]
            if key in steps:
                dy, dx = steps[key]
                dest = (y + dy, x + dx)
                self.assertNotEqual(terrain.get(dest), "wall", (key, reason, dest))
                self.assertNotIn(dest, blocked, (key, reason, dest))
                raw["player"]["y"], raw["player"]["x"] = dest
            elif key.startswith("g"):
                pile = objects.get((y, x), [])
                self.assertNotIn(7, pile, "the chest itself must stay on the floor")
                for tval in pile:
                    picked.append(((y, x), tval))
                    raw["inventory"].append({"slot": chr(ord("a") + len(raw["inventory"])),
                                             "name": "constructed pickup", "count": 1,
                                             "tval": tval, "known": False, "aware": False})
                objects.pop((y, x), None)
            elif reason == "chest:open" and not opened:
                self.assertGreaterEqual(reasons.count("chest:search"), 6)
                self.assertGreaterEqual(reasons.count("chest:disarm"), 2)
                objects.setdefault((9, 9), []).append(75)
                objects[(11, 9)] = [23]
                opened = True
            elif key == "<":
                self.assertTrue(opened)
                self.assertIn(((9, 9), 23), picked)
                self.assertIn(((9, 11), 23), picked)
                self.assertIn(((9, 9), 75), picked)
                self.assertIn(((11, 9), 23), picked)
                self.assertTrue(all(t in {1, 3, 7, 10} for ts in objects.values() for t in ts), objects)
                self.assertEqual(objects.get((10, 9)), [7])
                raw["floor"]["quest_id"] = 0
                raw["floor"]["level"] = 0
            raw["turn"] += 10
            render()
            self.post(policy, before, key, raw)
            policy.confirm_key_posted(key)
            if key == "<":
                break
        else:
            self.fail(f"did not finish: {reasons[-10:]}")

    def test_chest_contents_on_same_cell_leave_chest_in_place(self):
        policy = make_policy(self.data)
        observe_until(policy, self.data["rows"], 286)
        raw = copy.deepcopy(self.data["rows"][286])
        # DECLARED CONSTRUCTED: Chest::open can drop contents on its own
        # square. Its leading chest must survive repeated floor chooser picks.
        raw["player"]["y"], raw["player"]["x"] = 10, 9
        raw["grid_map"]["cells"].append({"y": 10, "x": 9, "o": 3, "t": [7, 75, 23]})
        raw["grid_map"]["found_items"] = [[10, 9, 3, 7, 75, 23]]
        policy._chest_position = Position(10, 9)
        policy._chest_phase_counts = {"search": 6, "disarm": 2, "open": 1}
        policy._chest_preopen_objects = {Position(10, 9): (1, 0)}
        key = str(policy.choose_key(parse_snapshot(raw, {})))
        self.assertEqual((key, policy.last_reason), ("gbb\x1b", "chest:collect-contents"))
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["grid_map"]["found_items"] = [[10, 9, 1, 7]]
        following["grid_map"]["cells"][-1] = {"y": 10, "x": 9, "o": 1, "t": [7]}
        self.post(policy, raw, key, following)

    def test_opened_chest_does_not_collect_deferred_or_junk_contents(self):
        policy = make_policy(self.data)
        observe_until(policy, self.data["rows"], 286)
        raw = copy.deepcopy(self.data["rows"][286])
        # DECLARED CONSTRUCTED: generated junk and an explicitly deferred
        # content pile are subject to the same rules as ordinary quest loot.
        raw["player"]["y"], raw["player"]["x"] = 9, 9
        raw["grid_map"]["found_items"] = [[9, 9, 1, 1], [11, 9, 1, 75], [10, 9, 1, 7]]
        raw["grid_map"]["cells"] += [
            {"y": 9, "x": 9, "o": 1, "t": [1]},
            {"y": 11, "x": 9, "o": 1, "t": [75]},
            {"y": 10, "x": 9, "o": 1, "t": [7]},
        ]
        policy._chest_position = Position(10, 9)
        policy._chest_phase_counts = {"search": 6, "disarm": 2, "open": 1}
        policy._chest_preopen_objects = {Position(10, 9): (1, 0)}
        policy._deferred_loot.add(Position(11, 9))
        key = str(policy.choose_key(parse_snapshot(raw, {})))
        self.assertEqual((key, policy.last_reason), ("o2", "chest:open"))
        self.post(policy, raw, key, dict(raw, turn=raw["turn"] + 10))

    def test_visible_underfoot_junk_does_not_bypass_shared_judgment(self):
        policy = make_policy(self.data)
        observe_until(policy, self.data["rows"], 286)
        raw = copy.deepcopy(self.data["rows"][286])
        # DECLARED CONSTRUCTED: the observed pile underfoot consists only
        # of remains; the immediate pickup branch must apply floor judgment.
        raw["player"]["y"], raw["player"]["x"] = 9, 9
        raw["grid_map"]["found_items"] = [[9, 9, 1, 1]]
        raw["grid_map"]["cells"].append({"y": 9, "x": 9, "o": 1, "t": [1]})
        policy._processed_chest_positions.add(Position(10, 9))
        key = str(policy.choose_key(parse_snapshot(raw, {})))
        self.assertFalse(key.startswith("g"))
        self.assertNotEqual(policy.last_reason, "quest:sweep:pickup")
        self.post(policy, raw, key, dict(raw, turn=raw["turn"] + 10))

    def test_shared_junk_and_deferral_rules_filter_quest_sweep(self):
        policy = make_policy(self.data)
        observe_until(policy, self.data["rows"], 286)
        raw = copy.deepcopy(self.data["rows"][286])
        # DECLARED CONSTRUCTED: one remembered remains pile, one explicitly
        # deferred sword; neither is a sweep goal despite being found_items.
        raw["grid_map"]["found_items"] = [[9, 9, 1, 1], [9, 11, 1, 23]]
        policy._processed_chest_positions.add(Position(10, 9))
        policy._deferred_loot.add(Position(9, 11))
        policy.choose_key(parse_snapshot(raw, {}))
        self.assertEqual(policy.last_reason, "quest:exit")

    def test_chest_direction_answer_is_dropped_when_game_auto_selects(self):
        policy = make_policy(self.data)
        observe_until(policy, self.data["rows"], 286)
        raw = copy.deepcopy(self.data["rows"][286])
        # DECLARED CONSTRUCTED: stand next to the captured chest, after the
        # existing search/disarm budgets, and model easy_open's inferred dir.
        raw["player"]["y"], raw["player"]["x"] = 9, 9
        policy._chest_position = Position(10, 9)
        policy._chest_phase_counts = {"search": 6, "disarm": 2}
        key = str(policy.choose_key(parse_snapshot(raw, {})))
        self.assertEqual(policy.last_reason, "chest:open")
        self.assertEqual(key, "o2")
        self.post(policy, raw, key, dict(raw, turn=raw["turn"] + 10), auto_direction=True)


if __name__ == "__main__":
    unittest.main()
