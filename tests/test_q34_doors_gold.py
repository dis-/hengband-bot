"""Q34 owner request (2026-10-30): open [4,15] and [4,16] after the final door,
fight the bee on contact, and collect the bottom-right gold after clearing.

Boards are recorded (tests/fixtures/q34-final-room-1029.json.gz board 78509 and
tests/fixtures/q34-collect-20261025.json.gz row 188).  DECLARED CONSTRUCTED:
the opened-door terrain (the recorded open glass door feature 200 of row 188
placed on [4,14..16]), the bee moved next to the player, the player's movement
and the loot sweep's used route budget.  They are not a claim of a new
live-game run.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot.cli import STATIONARY_EXEMPT_REASONS, _ExecutorInputPort, SendResult
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import (
    POLICY_FINAL_STOP_REASONS,
    Q34_SEQUENCE_DOOR_ATTEMPT_LIMIT,
    WAIT_KEY,
)
from hengbot.quest_final_room import avoided_doors, door_gates, next_sequence_door
from hengbot.quest_navigator import SWEEP_BUDGET
from tests.test_input_executor import FaithfulHookGame, ProductionHarness, command_screen
from tests.test_q34_collect_recorded import (
    Q34CollectRecordedTest,
    captured,
    make_policy,
    observe_until,
)

FINAL_ROOM = Path(__file__).parent / "fixtures" / "q34-final-room-1029.json.gz"
# Row 188's palette entry for the picked (open) glass door [4,14].
OPEN_GLASS_DOOR = [200, 0, 388, 1]
CLOSED_GLASS_PALETTE = 2  # board 78509: [202, 0, 32900, 1]
STEPS = {"8": (-1, 0), "2": (1, 0), "4": (0, -1), "6": (0, 1),
         "7": (-1, -1), "9": (-1, 1), "1": (1, -1), "3": (1, 1)}
GOLD = Position(11, 20)


def with_open_doors(raw, opened):
    """Board 78509 with the given row-4 glass doors among [4,14..16] open."""
    grid = raw["grid_map"]
    if OPEN_GLASS_DOOR not in grid["palette"]:
        grid["palette"].append(list(OPEN_GLASS_DOOR))
    open_index = grid["palette"].index(OPEN_GLASS_DOOR)
    grid["runs"] = [run for run in grid["runs"]
                    if not (run[0] == 4 and 14 <= run[1] <= 16)]
    for x in (14, 15, 16):
        grid["runs"].append([4, x, 1, open_index if x in opened else CLOSED_GLASS_PALETTE])
    return raw


class Q34DoorsGoldTest(ProductionHarness):
    collect_post = Q34CollectRecordedTest.post

    @classmethod
    def setUpClass(cls):
        with gzip.open(FINAL_ROOM, "rt", encoding="utf-8") as stream:
            cls.final_room = json.load(stream)
        cls.facts = captured()

    def door_board(self, opened):
        raw = copy.deepcopy(self.final_room["boards"]["78509"])
        return with_open_doors(raw, opened)

    def door_policy(self, raw):
        policy = make_policy(self.facts)
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15), (107, 9, 11), (107, 11, 9),
        }
        return policy

    def post(self, policy, raw, following):
        """choose_key, then the production executor posts it to a fake game."""
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), key)
        return key

    def walk_door_sequence(self, raw, policy, limit=12):
        """Constructed replies: moves succeed and each lock pick opens its door."""
        opened = {14}
        trace = []
        for _ in range(limit):
            following = copy.deepcopy(raw)
            following["turn"] += 10
            here = (raw["player"]["y"], raw["player"]["x"])
            key = self.post(policy, raw, following)
            reason = policy.last_reason
            trace.append((key, reason, here))
            if reason == "quest-strategy:approach-final-target":
                break
            if key in STEPS:
                dy, dx = STEPS[key]
                following["player"]["y"] += dy
                following["player"]["x"] += dx
            elif key.startswith("o"):
                dy, dx = STEPS[key[1:]]
                door = (here[0] + dy, here[1] + dx)
                self.assertIn(door, ((4, 15), (4, 16)), trace)
                opened.add(door[1])
                with_open_doors(following, opened)
            raw = following
        return trace

    def test_a_opens_4_15_then_4_16_after_the_final_door(self):
        raw = self.door_board({14})
        policy = self.door_policy(raw)
        trace = self.walk_door_sequence(raw, policy)
        self.assertEqual(trace[:4], [
            ("6", "quest-strategy:approach-sequence-door", (5, 14)),
            ("o8", "quest-strategy:open-sequence-door", (5, 15)),
            ("6", "quest-strategy:approach-sequence-door", (5, 15)),
            ("o8", "quest-strategy:open-sequence-door", (5, 16)),
        ])
        # Both doors open: the existing final-target approach resumes.
        self.assertEqual(trace[4][1], "quest-strategy:approach-final-target")
        self.assertEqual(policy._q34_sequence_door_attempts, {})

    def test_a_lock_picks_are_loop_exempt_and_bounded(self):
        self.assertIn("quest-strategy:open-sequence-door", STATIONARY_EXEMPT_REASONS)
        raw = self.door_board({14})
        raw["player"]["x"] = 15
        policy = self.door_policy(raw)
        following = dict(raw, turn=raw["turn"] + 10)
        self.assertEqual(self.post(policy, raw, following), "o8")
        # The board (from the recorded final-door picks) carries the game's
        # answer "鍵をはずせなかった。": an answered pick is not counted (D33).
        self.assertIn("鍵をはずせなかった", raw["messages"][-1])
        self.assertEqual(policy._q34_sequence_door_attempts, {Position(4, 15): 0})
        # DECLARED CONSTRUCTED: the lock never yields; jump to the bound.
        policy._q34_sequence_door_attempts[Position(4, 15)] = Q34_SEQUENCE_DOOR_ATTEMPT_LIMIT
        key = policy.choose_key(parse_snapshot(following, policy._monrace_knowledge))
        self.assertEqual((key, policy.last_reason),
                         (WAIT_KEY, "quest:blocked:q34-sequence-door-locked"))
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)

    def test_b_bee_contact_during_door_work_fights_first(self):
        raw = self.door_board({14})
        raw["player"]["x"] = 15
        # DECLARED CONSTRUCTED: the bee came out through the open final door.
        raw["visible_monsters"][0].update(y=4, x=14)
        cells = raw["grid_map"]["cells"]
        for cell in cells:
            cell.pop("m", None)
        cells.append({"y": 4, "x": 14, "m": 1})
        policy = self.door_policy(raw)
        following = dict(raw, turn=raw["turn"] + 10)
        self.assertEqual(self.post(policy, raw, following), "7")
        self.assertEqual(policy.last_reason, "quest-strategy:melee")
        # The bee gone (killed), the door work resumes at [4,15].
        raw = copy.deepcopy(following)
        raw["visible_monsters"] = []
        raw["grid_map"]["cells"] = [c for c in raw["grid_map"]["cells"] if "m" not in c]
        self.assertEqual(self.post(policy, raw, dict(raw, turn=raw["turn"] + 10)), "o8")
        self.assertEqual(policy.last_reason, "quest-strategy:open-sequence-door")

    def test_c_cleared_quest_collects_the_gold_before_leaving(self):
        policy = make_policy(self.facts)
        observe_until(policy, self.facts["rows"], 188)
        raw = copy.deepcopy(self.facts["rows"][188])
        quest = next(q for q in raw["progress"]["quests"] if q["id"] == 34)
        self.assertEqual(quest["status"], 2)  # recorded: cleared (COMPLETED)
        gold_cell = next(c for c in raw["grid_map"]["cells"]
                         if (c["y"], c["x"]) == (GOLD.y, GOLD.x))
        self.assertEqual(gold_cell["t"], [127])  # recorded: remembered gold
        # Leave only the gold: the other piles are already collected.
        raw["grid_map"]["found_items"] = []
        raw["grid_map"]["cells"] = [c for c in raw["grid_map"]["cells"]
                                    if "o" not in c or (c["y"], c["x"]) == (GOLD.y, GOLD.x)]
        policy._processed_chest_positions.add(Position(10, 9))
        policy.choose_key(parse_snapshot(raw, {}))
        # DECLARED CONSTRUCTED: the loot sweep has used its route budget
        # (the gold is the farthest pile from the upper room).
        policy._quest_navigators[34].sweep_turns = SWEEP_BUDGET
        reasons = []
        gold_taken = None
        for turn in range(200):
            before = copy.deepcopy(raw)
            key = str(policy.choose_key(parse_snapshot(before, {})))
            reasons.append(policy.last_reason)
            y, x = raw["player"]["y"], raw["player"]["x"]
            if key in STEPS:
                dy, dx = STEPS[key]
                raw["player"]["y"], raw["player"]["x"] = y + dy, x + dx
                if (y + dy, x + dx) == (GOLD.y, GOLD.x):
                    # Walking onto gold collects it (no pickup command).
                    raw["grid_map"]["cells"] = [c for c in raw["grid_map"]["cells"]
                                                if (c["y"], c["x"]) != (GOLD.y, GOLD.x)]
                    raw["grid_map"]["cells"].append({"y": GOLD.y, "x": GOLD.x, "o": 0, "t": []})
                    gold_taken = turn
            elif key == "<":
                raw["floor"]["quest_id"] = 0
                raw["floor"]["level"] = 0
            raw["turn"] += 10
            self.collect_post(policy, before, key, raw)
            policy.confirm_key_posted(key)
            if key == "<":
                break
        else:
            self.fail(f"did not leave: {reasons[-10:]}")
        self.assertIn("quest:post-clear:seek-gold", reasons)
        self.assertIsNotNone(gold_taken, reasons[-10:])
        self.assertEqual(reasons[-1], "quest:exit")
        self.assertLess(gold_taken, len(reasons) - 1)

    def test_d_4_17_is_never_opened(self):
        plan = make_policy(self.facts).approved_quest_strategy(34).engagement_plan
        self.assertIn(Position(4, 17), avoided_doors(plan))
        self.assertTrue({Position(4, 15), Position(4, 16)}.isdisjoint(avoided_doors(plan)))
        raw = self.door_board({14, 15, 16})
        board = parse_snapshot(dict(raw, visible_monsters=[]), {})
        self.assertIsNone(next_sequence_door(board, plan))
        self.assertIn(Position(4, 17), door_gates(board, plan))
        # Walk the whole sequence: no key ever opens or enters [4,17].
        policy = self.door_policy(self.door_board({14}))
        trace = self.walk_door_sequence(self.door_board({14}), policy)
        for key, _, here in trace:
            if key in STEPS or key.startswith("o"):
                dy, dx = STEPS[key[-1]]
                self.assertNotEqual((here[0] + dy, here[1] + dx), (4, 17), trace)


if __name__ == "__main__":
    unittest.main()
