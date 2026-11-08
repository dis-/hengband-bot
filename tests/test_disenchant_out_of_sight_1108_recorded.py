"""disenchant-out-of-sight-1108: an avoided disenchanter keeps its area once out of sight.

Recorded: n1-b life-339 (Magic-Eater), 鉄獄30階, 2026-11-08 02:39
(tests/fixtures/disenchant-out-of-sight-20261108.json.gz,
tests/extract_disenchant_out_of_sight_1108_fixture.py).  A Devilfish (race 918: BR_DISE,
AQUATIC; no disenchant resistance, so owner 2026-11-05 「劣化耐性がないときに劣化属性攻撃を
するモンスターとの戦闘は可能であれば回避する」 applies, disenchant_avoid) swam at
[37,81]/[38,81].  At [37,84] the engagement retreat stepped '3' to [38,85]; there the wall
hid it, _engagement_danger_cells (perceived monsters only) was empty, and the explore
stepped '7' straight back to [37,84], 40 times, until the loop detector stopped the bot.
The retreat's veto of [37,84] was not claimed (engagement_avoid_seal: it would close the
pocket), so nothing else kept the walk out.

Now disenchant_avoid remembers a kept-away monster at its last shown cell for the
retreat veto's window (retreat_veto_life.UNSEEN_GAME_TURNS): the retreat still answers for
it, and the explore and the routes keep off its area (disenchant_avoid.remembered_cells).

Every decision is the public ``choose_key``; the asserted first key goes through the
production executor.
DECLARED RECONSTRUCTION: the replay starts at the capture's board 40 ([39,84]) with a fresh
policy; the stop's deferred loot ([39,80], policy-state.json) and the loot at [37,79] the live
run never walked to are deferred, so the replay's floor owner is the explore, as recorded.
DECLARED COUNTERFACTUAL (the walk): after the first board out of sight the player follows the
decided moves on that board with nothing in view, ten game turns a decision, for the
window; every other board fact is unchanged.  The remembered frontiers beyond the Devilfish's
reach are taken as already probed, so the frontiers left lie in its reach, where the live
explore went.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HUNT_RANGE
from hengbot.retreat_veto_life import UNSEEN_GAME_TURNS
from tests import test_input_executor as executor_pins
from tests.test_dungeon_1031_recorded import RecordedHarness, decide

FIXTURE = Path(__file__).with_name("fixtures") / "disenchant-out-of-sight-20261108.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
BOARDS = CASE["boards"]
RECORDED = {row["turn"]: (row["key"], row["reason"]) for row in CASE["decisions"]}
DEVILFISH = 918
AVOID = "threat:avoid-engagement"
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
         "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def knowledge():
    races = {}
    for race, facts in CASE["monraces"].items():
        facts = copy.deepcopy(facts)
        for name in ("flags", "abilities"):
            facts[name] = frozenset(facts[name])
        facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
        facts["names"] = tuple(facts["names"])
        races[int(race)] = MonraceKnowledge(**facts)
    return races


def replayed():
    """The policy after boards 0..-2 (DECLARED RECONSTRUCTION, module docstring)."""
    policy = HengbotPolicy(monrace_knowledge=knowledge())
    policy.prime(parse_snapshot(copy.deepcopy(BOARDS[0]), policy._monrace_knowledge))
    loot = {Position(*cell) for cell in CASE["deferred_loot"]}
    policy._deferred_loot |= loot | {Position(37, 79)}
    policy._nav_ledger_deferred_loot |= loot
    for raw in BOARDS[:-1]:
        key = decide(policy, copy.deepcopy(raw))
        if key:
            policy.confirm_key_posted(key)
    return policy


class DisenchanterOutOfSightRecordedTest(RecordedHarness):
    def test_recorded_retreat_then_walk_back(self):
        seen, hidden = BOARDS[-2], BOARDS[-1]
        self.assertEqual((seen["player"]["y"], seen["player"]["x"]), (37, 84))
        self.assertEqual([(m["race_id"], m["y"], m["x"]) for m in seen["visible_monsters"]],
                         [(DEVILFISH, 37, 81)])
        self.assertEqual(RECORDED[seen["turn"]], ("3", AVOID))
        self.assertEqual((hidden["player"]["y"], hidden["player"]["x"]), (38, 85))
        self.assertEqual(hidden["visible_monsters"], [])
        self.assertEqual(RECORDED[hidden["turn"]], ("7", "explore"))

    def test_out_of_sight_the_retreat_still_steps_away(self):
        policy = replayed()
        raw = BOARDS[-1]
        key = decide(policy, copy.deepcopy(raw))
        self.assertEqual(policy.last_reason, AVOID)
        here = Position(raw["player"]["y"], raw["player"]["x"])
        step = Position(here.y + MOVES[key][0], here.x + MOVES[key][1])
        last_seen = Position(37, 81)
        self.assertGreater(step.distance_to(last_seen), here.distance_to(last_seen))
        self.post(policy, raw, key, [], self.later(raw))

    def test_no_walk_goes_back_into_its_reach_for_the_window(self):
        policy = replayed()
        raw = copy.deepcopy(BOARDS[-1])
        # DECLARED COUNTERFACTUAL (module docstring): only the frontiers in its reach left.
        snapshot = policy._with_grid_memory(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        last_seen = Position(37, 81)
        beyond = {
            Position(y, x) for y, x in policy._remembered_floor_t
            if policy._is_remembered_frontier(snapshot, Position(y, x))
            and Position(y, x).distance_to(last_seen) > HUNT_RANGE
        }
        policy._probed_frontiers |= beyond
        policy._exploration_ledger.probed_frontiers |= beyond
        start_turn = raw["turn"]
        here = Position(raw["player"]["y"], raw["player"]["x"])
        distance = here.distance_to(last_seen)
        left = False
        while raw["turn"] - start_turn <= UNSEEN_GAME_TURNS:
            key = decide(policy, copy.deepcopy(raw))
            if key:
                policy.confirm_key_posted(key)
            raw["turn"] += 10
            raw["messages"] = []
            if key not in MOVES:
                continue
            here = Position(raw["player"]["y"] + MOVES[key][0], raw["player"]["x"] + MOVES[key][1])
            raw["player"]["y"], raw["player"]["x"] = here.y, here.x
            now = here.distance_to(last_seen)
            if left:
                self.assertGreater(now, HUNT_RANGE, (raw["turn"], key, policy.last_reason))
            else:
                self.assertGreaterEqual(now, distance, (raw["turn"], key, policy.last_reason))
            if not left and now > HUNT_RANGE:
                # Outside: its whole area is the descent's and the committed
                # explore route's veto too (_engagement_danger_cells).
                board = policy._with_grid_memory(
                    parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
                self.assertIn(Position(38, 85), policy._engagement_danger_cells(board))
            left = left or now > HUNT_RANGE
            distance = now
        self.assertTrue(left)


if __name__ == "__main__":
    import unittest
    unittest.main()
