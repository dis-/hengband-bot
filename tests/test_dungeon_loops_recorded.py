"""D31: recorded dungeon loop stops of 2026-10-30 (n1-a, n1-b).

Fixture: tests/fixtures/dungeon-loops-20261030.json.gz
(tests/extract_dungeon_loops_1031.py).  Every decision goes through the
public choose_key and every posted key through the production executor port.

- mining-door (n1-a life-446; same shape n1-c life-007/009, n1-a life-441):
  the mining closure routes to a detected vein through a locked door.  Each
  pick (exe_open: 鍵をはずせなかった。) uses a turn and holds the cell, so the
  CLI cell guard stopped the run after 40 decisions although the closure's
  own MINING_STALL_LIMIT leash bounds the picks per target.
- loot-piles (n1-b life-249, life-273): with a full pack the triage walked
  toward unknown floor items on multi-object piles; the floor identify ('-')
  acts only on a single-object grid, so it walked between two piles forever.
- confused-read (n1-a life-418): confused, the no-wait ladder chose a
  Teleport read that cmd-read.cpp refuses (cmd_limit_confused) without a turn.

DECLARED CONSTRUCTED: the mining checkpoint does not carry the detection
floor latch, so ``_mining_scroll_used_floor`` is the stop floor (the recorded
rows are mid-closure, after detection).  Replies to an open key keep the
board at the next turn (the lock holds).  The loot cases' victory-loot latch
is not checkpointed; the recorded triage reason is only reachable through the
conquest loot owner, so ``_victory_loot_dungeon`` is the stop dungeon.  The
look probe's reply is the ring's recorded look row.  A walk's reply moves the
player one cell on the recorded board.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from collections import deque
import gzip
import json
from pathlib import Path
import unittest

from hengbot.cli import (
    LOOP_WINDOW, SendResult, _ExecutorInputPort, _cell_loop_guard_applies, _is_looping,
)
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import MINING_STALL_LIMIT
from hengbot.policy_fundraising import (
    FundraisingPurpose, FundraisingPurposeRecord, FundraisingTransportChild,
)
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen

FIXTURE = Path(__file__).parent / "fixtures" / "dungeon-loops-20261030.json.gz"
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
DOOR = Position(38, 95)


class DungeonLoopsRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def policy(self, name):
        case = self.cases[name]
        races = {}
        for key, facts in case["monraces"].items():
            facts = copy.deepcopy(facts)
            for field in ("flags", "abilities"):
                facts[field] = frozenset(facts[field])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            races[int(key)] = MonraceKnowledge(**facts)
        raw = copy.deepcopy(case["board"])
        policy = HengbotPolicy(monrace_knowledge=races)
        policy.prime(parse_snapshot(raw, races))
        # The captured process already held the skill knowledge, so the
        # periodic skill-experience request does not own the decision.
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy, raw

    def mining_policy(self):
        policy, raw = self.policy("mining-door")
        case = self.cases["mining-door"]
        terrain = case["terrain"]
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in terrain[f"{name}_t"])
        policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
        for name, value in case["modes"].items():
            setattr(policy, name, value)
        recorded = case["purpose"]
        purpose = FundraisingPurpose(recorded["id"], recorded["mode"],
                                     recorded["first_run_food_waiver"])
        child = recorded["child"]
        policy._fundraising_run_purpose = purpose
        policy._fundraising_purpose_record = FundraisingPurposeRecord(
            purpose, status=recorded["status"],
            child=FundraisingTransportChild(
                purpose.identity, child["direction"], (0, 0, 0),
                child["posted_sequence"], state=child["state"]),
        )
        # DECLARED CONSTRUCTED (module docstring): detected on this floor.
        policy._mining_scroll_used_floor = parse_snapshot(raw, {}).floor_key
        return policy, raw

    def choose(self, policy, raw):
        return str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))

    def post(self, policy, raw, key, following):
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

    @staticmethod
    def walked(raw, key):
        """DECLARED CONSTRUCTED: the reply to a walk moves the player."""
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        dy, dx = DIRECTIONS[key]
        following["player"]["y"] += dy
        following["player"]["x"] += dx
        return following

    def test_recorded_rows(self):
        rows = {name: case["decision"] for name, case in self.cases.items()}
        self.assertEqual((rows["mining-door"]["reason"], rows["mining-door"]["key"]),
                         ("fundraise:seek-treasure", "o1"))
        self.assertEqual(self.cases["mining-door"]["claim_goal"],
                         {"kind": "Reach", "cell": [40, 97]})
        for name in ("loot-piles-249", "loot-piles-273"):
            self.assertEqual(rows[name]["reason"], "loot:seek-unidentified-floor-item")
        self.assertEqual((rows["confused-read"]["reason"], rows["confused-read"]["key"]),
                         ("no-wait:escape-scroll", "rd"))
        self.assertIn("confused", rows["confused-read"]["player"]["status"])

    def test_locked_door_picks_on_the_mining_route_do_not_trip_the_cell_guard(self):
        policy, raw = self.mining_policy()
        board = parse_snapshot(raw, {})
        self.assertEqual(board.player.position, Position(37, 96))
        self.assertTrue(board.grids[DOOR].is_closed_door)
        # The CLI cell guard as the driver feeds it (cli.py main loop).
        recent, previous = deque(maxlen=LOOP_WINDOW), None
        for _ in range(LOOP_WINDOW + 5):
            key = self.choose(policy, raw)
            self.assertEqual(key, "o1")
            self.assertEqual(policy.last_reason, "fundraise:seek-treasure:open-door")
            following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10)
            self.post(policy, raw, key, following)
            if _cell_loop_guard_applies(board, policy.last_reason, previous):
                recent.append((board.floor_key, board.player.position.y,
                               board.player.position.x))
            else:
                recent.clear()
            previous = board.player.position
            self.assertFalse(_is_looping(recent), policy.last_reason)
            raw = following

    def test_mining_door_picks_are_bounded_per_target(self):
        policy, raw = self.mining_policy()
        self.assertEqual(self.choose(policy, raw), "o1")
        target = policy._treasure_target
        self.assertEqual(target, Position(40, 97))
        # DECLARED CONSTRUCTED: the lock never yields; jump to the leash.
        policy._mining_stall_turns = MINING_STALL_LIMIT - 1
        self.choose(policy, dict(raw, turn=raw["turn"] + 10))
        self.assertIn(target, policy._mining_dropped_veins)
        self.assertNotEqual(policy._treasure_target, target)


if __name__ == "__main__":
    unittest.main()
