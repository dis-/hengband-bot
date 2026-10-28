"""Issue #47 R3: actual accepted-Q1 stops with calibrated Warrior state.

Only game replies (entry confirmation/floor and later movement/combat) are
constructed; entrance terrain, resources, skill and calibration are recorded.
"""
import tests  # noqa: F401
import copy
import gzip
import io
import json
import pickle
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from hengbot.model import parse_snapshot, _GRID_TERRAIN_NAMES
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy_constants import QUEST_STATUS_TAKEN
from hengbot.warrior_optimization import load_character_calibration
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen, prompt_screen
from tests import test_opening_route_r2_recorded as round2


class OpeningRouteR3RecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(round2.OpeningRouteR2RecordedTest.shelf_screen)
    @classmethod
    def setUpClass(cls):
        round2.OpeningRouteR2RecordedTest.setUpClass()
        with gzip.open(Path(__file__).with_name("fixtures") / "opening-route-r3-stops.json.gz",
                       "rt", encoding="utf-8") as stream:
            cls.stops = json.load(stream)

    def case(self, tag, stage="snapshot"):
        policy, _ = round2.OpeningRouteR2RecordedTest().case(tag)
        facts = copy.deepcopy(self.stops["monrace2"])
        for name in ("flags", "abilities"):
            facts[name] = frozenset(facts[name])
        facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
        policy._monrace_knowledge[2] = MonraceKnowledge(**facts)
        raw = copy.deepcopy(self.stops[tag][stage])
        board = parse_snapshot(raw, policy._monrace_knowledge)
        policy.prime(board)
        policy.consume_skill_knowledge(self.stops[tag]["skill"])
        directory = tempfile.TemporaryDirectory(prefix="opening-r3-calibration-")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "calibration.json"
        path.write_text(json.dumps(self.stops[tag]["calibration"]), encoding="utf-8")
        # Same loader as CLI; bind the recorded inverse to this replay process.
        policy._character_calibration = load_character_calibration(path)
        policy._character_calibration_loaded = True
        self.assertIsNotNone(policy._validated_character_calibration(board))
        return policy, raw

    @staticmethod
    def inside_reply(policy, raw):
        # DECLARED CONSTRUCTED: engine confirms entry and shows Q1's real start
        # room. Static terrain comes from the reviewed quest definition.
        inside = copy.deepcopy(raw)
        inside["floor"].update(in_town=False, quest_id=1, level=5)
        inside["turn"] += 1
        battlefield = policy._quest_knowledge[1].battlefield
        inside["player"]["y"], inside["player"]["x"] = battlefield.player_start
        inside["visible_monsters"] = []
        inside["detected_monsters"] = []
        palette, runs, cells = [], [], []
        for (y, x), kind in battlefield.terrain.items():
            flags = {"floor", "move", "los"}
            if kind in {"wall", "permanent", "door", "secret"}:
                flags = {"wall"} if kind != "door" else {"door"}
            if (y, x) == battlefield.exit:
                flags |= {"up_stairs", "stairs", "quest_exit"}
                cells.append(dict(y=y, x=x, q=1))
            bits = sum(1 << _GRID_TERRAIN_NAMES.index(f) for f in flags)
            palette.append([1, 0, bits, True])
            runs.append([y, x, 1, len(palette)-1])
        inside["grid_map"] = dict(h=10, w=15, palette=palette, runs=runs,
                                  cells=cells, found_items=[], unsafe_rows=None)
        return inside

    def post_entry(self, policy, raw, key, inside):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = command_screen(raw["turn"])
        game.screens = [prompt_screen("Do you enter? [y/n]"), command_screen(inside["turn"])]
        game.states = [copy.deepcopy(raw), copy.deepcopy(inside)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic()+10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "opening-r3-entry", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic()+10,
            poll_interval=0, prompt_japanese=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, [key, "y"])
        self.assertFalse(game.term_fifo)
        policy.confirm_key_posted(key)

    def test_actual_calibrated_stops_enter_by_step_and_use_approved_floor_strategy(self):
        for tag in ("1", "2"):
            with self.subTest(seed=tag):
                policy, raw = self.case(tag)
                before = self.stops[tag]["before"]
                self.assertEqual(before["fixedquest_readiness"]["opening_route_failure"],
                                 "quest-request-unavailable")
                self.assertIn("equipment_departure_ready", before["departure_block"]["failed"])
                board = parse_snapshot(raw, policy._monrace_knowledge)
                self.assertEqual(board.quests[1].status, QUEST_STATUS_TAKEN)
                self.assertEqual((board.player.position.y, board.player.position.x), (34, 176))
                key = str(policy.choose_key(board))
                self.assertEqual((key, policy.last_reason), ("3", "quest:enter:approach"),
                                 getattr(policy, "_opening_q1_failure", None))
                self.assertTrue(policy.fixed_quest_readiness_state()["verdict"])
                inside = self.inside_reply(policy, raw)
                self.post_entry(policy, raw, key, inside)
                key = str(policy.choose_key(parse_snapshot(inside, policy._monrace_knowledge)))
                self.assertTrue(policy.last_reason.startswith("quest-strategy:"), (key, policy.last_reason))
                following = copy.deepcopy(inside)
                following["player"]["x"] += 1  # constructed first room step
                following["turn"] += 1
                round2.OpeningRouteR2RecordedTest.post(self, policy, inside, key, following)
                self.assertEqual(policy._quest_navigators[1].floor_key, (0, 5, 1))

    def test_restart_on_entrance_posts_downstairs_and_confirmation(self):
        policy, raw = self.case("1")
        # DECLARED CONSTRUCTED: restart on the emitted entrance itself.
        raw["player"].update(y=35, x=177)
        policy = pickle.loads(pickle.dumps(policy))
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), (">", "quest:enter"))
        self.post_entry(policy, raw, key, self.inside_reply(policy, raw))

    def test_entry_rechecks_missing_torches_and_temporary_status(self):
        for change in ("torches", "status"):
            policy, raw = self.case("1")
            if change == "torches":
                raw["inventory"] = [it for it in raw["inventory"] if it.get("tval") != 39]
            else:
                raw["player"].setdefault("status", {})["confused"] = True
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            self.assertNotEqual(policy.last_reason, "quest:enter:approach", (change, key))
            self.assertNotEqual(key, ">")

    def test_completed_shopping_is_not_reopened_before_request_after_restart(self):
        policy, raw = self.case("1")
        # DECLARED CONSTRUCTED: completed shopping, still beside the request
        # building before acceptance; ample remaining gold is not a new survey.
        raw["progress"]["quests"] = [dict(q, status=0) if q["id"] == 1 else q
                                      for q in raw["progress"]["quests"]]
        raw["player"].update(y=27, x=98, gold=10000)
        policy._opening_q1_kit_bought = True
        policy = pickle.loads(pickle.dumps(policy))
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), ("8q\x1b", "fixedquest:request"))

    def test_taken_quest_does_not_reopen_shops_or_rebuild_readiness_while_walking(self):
        policy, raw = self.case("1", "approach")
        # A richer purse must not restart kit work after acceptance, including
        # a checkpoint whose in-memory shopping latch was not retained.
        raw["player"]["gold"] = 10000
        with patch.object(policy, "_evaluate_fixed_quest_readiness", wraps=policy._evaluate_fixed_quest_readiness) as ready:
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual(policy.last_reason, "quest:enter:approach", key)
        self.assertEqual(ready.call_count, 0)

    def test_detection_stop_settles_combat_instead_of_reversing_shop_step(self):
        policy, _ = self.case("1")
        raw = copy.deepcopy(self.stops["1"]["detection"]["snapshot"])
        # Recorded purse 218 can afford a detection shelf survey. This was a
        # combat/shop oscillation, not R2's no-money shelf loop.
        self.assertEqual(raw["player"]["gold"], 218)
        before = self.stops["1"]["detection"]["before"]
        self.assertEqual(before["fixedquest_readiness"]["opening_route_failure"],
                         "no-progress:observe:fundraising-detection")
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), ("3", "melee"))
        following = copy.deepcopy(raw)
        # DECLARED CONSTRUCTED: attack kills the adjacent recorded town monster;
        # the character does not move away to undo a later shopping step.
        following["visible_monsters"] = []
        following["detected_monsters"] = []
        following["turn"] += 1
        round2.OpeningRouteR2RecordedTest.post(self, policy, raw, key, following)
        next_key = str(policy.choose_key(parse_snapshot(following, policy._monrace_knowledge)))
        self.assertIn(policy.last_reason, {"shop:approach", "shop:travel"}, next_key)
