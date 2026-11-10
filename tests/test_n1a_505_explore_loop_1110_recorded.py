"""Two loop stops of 2026-11-10 (build 7404002a7), from the captures.

Recorded: tests/fixtures/n1a-505-explore-loop-1110/
(tests/extract_n1a_505_explore_loop_1110_fixtures.py).  Every decision is the public
``choose_key`` of a fresh policy given the stop's remembered terrain (its policy-state;
DECLARED RECONSTRUCTION, as stops-1109 and n1c-183), fed the recorded boards in order.

n1-a life-505 (warrior Lv25, Angband 6F, random quest 49), ``louse-0234``: the 100-attack
rule had latched the floor (breeder_stalemate) and the quest's type pursues the target past
the breeders (breeder_quest PURSUE: the bite ring of every perceived breeder is a route veto).
At [46,74] the 巨大白シラミ (race 69) up the corridor were in view, their rings closed it, and
explore stepped '1' or '3' into the room; there they were out of sight, the rings were
released and explore stepped back, until the loop detector at 02:34 (and again at 02:35 after
the restart, quest-search:seek-door).  The rings now stay at the breeders' last shown cells
out of sight (breeder_quest BREEDER_SEEN, owner 2026-11-09 「起きた敵も最後の位置を覚える」).
The latch comes through the production restart path: the policy reads the floor's breeder
record (breeder_floor_record) on its first board, as the restarted process of 02:34:13 did.
DECLARED RECONSTRUCTION: the record is the stopped process's (latched, no open window: the
incident policy-state's ``_breeder_engagement_start_count`` is null).  The fresh policy walks
seek-loot where the live one explored (its loot knowledge is not the live one's); the walk
reads the same rings.

n1-c life-186 (Magic-Eater Lv29, Orc cave 23F, the final floor), ``hunt-0229``: Detect Evil
showed the guardian (race 373) at [52,153] past the explored ground, and the hunt walk went to
the nearest frontier "closer to it than the player" (hunt_target.route_key, game distance), a
bound that moves with every step: the frontier chosen from [32,131] (30) was no longer closer
from [33,132] (29), the walk turned to another, and stepped '3' and '7' between the two cells
38 times until the loop detector.  The chosen frontier is now kept until reached; once the
player is as near the target as it, the walk gives the cell up as when no frontier is closer.
DECLARED COMPONENT PIN: the live process's walk veto (its remembered monsters) is not in the
capture, and on the fresh policy the two frontiers happen to lie on one way, so the pin asserts
the walk's target on the recorded boards, read from the goal walk's own route
(goal_route.follow) without changing it.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hengbot import breeder_quest, goal_route, hunt_target
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.test_dungeon_1031_recorded import skill
from tests.test_n1b_348_stops_1108_recorded import knowledge

FIXTURES = Path(__file__).with_name("fixtures") / "n1a-505-explore-loop-1110"
TERRAIN_SETS = ("known", "marked", "floor", "wall", "door", "rubble")
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
         "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
QUEST_FLOOR = (1, 6, 49)
LOUSE = 69
GUARDIAN = 373
DETECT_BOARD = 1576275  # [32,131]: Detect Evil shows the guardian at [52,153]
STEP_BOARD = 1576287  # [33,132]: the board after the walk's '3'


def case(name):
    with gzip.open(FIXTURES / f"{name}.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


LOUSE_CASE = case("louse-0234")
HUNT_CASE = case("hunt-0229")


def here(raw):
    return Position(raw["player"]["y"], raw["player"]["x"])


def boards(data):
    return [row for row in data["rows"] if row.get("type") == "player_turn"]


def recorded(data):
    rows = {}
    for row in data["decisions"]:
        rows.setdefault(row["turn"], (row["key"], row["reason"]))
    return rows


def fresh(data, *, record=None):
    policy = HengbotPolicy(monrace_knowledge=knowledge(data))
    for key, row in data["dungeons"].items():
        policy._dungeon_knowledge[int(key)] = DungeonInfo(**dict(row, flags=frozenset(row["flags"])))
    # The CLI points the record path before the first board (cli._configure_policy_output_paths).
    policy._breeder_floor_record_path = record
    first = copy.deepcopy(boards(data)[0])
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    terrain = data["terrain"]
    for name in TERRAIN_SETS:
        getattr(policy, f"_remembered_{name}_t").update(tuple(cell) for cell in terrain[f"{name}_t"])
    policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
    policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
    skill(policy, first)
    return policy


def decide(policy, raw):
    key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
    key = "" if key is None else str(key)
    if key:
        policy.confirm_key_posted(key)
    return key


def destination(raw, key):
    if key not in MOVES:
        return None
    return Position(raw["player"]["y"] + MOVES[key][0], raw["player"]["x"] + MOVES[key][1])


class RecordedRowsTest(unittest.TestCase):
    def test_recorded_rows(self):
        rows = recorded(LOUSE_CASE)
        self.assertEqual(rows[788108], ("1", "breakout:seek-frontier"))
        self.assertEqual(rows[788118], ("9", "explore"))
        self.assertEqual(rows[788127], ("1", "explore"))
        shown = {raw["turn"]: {m["race_id"] for m in raw["visible_monsters"]}
                 for raw in boards(LOUSE_CASE)}
        self.assertEqual(shown[788108], {LOUSE})
        self.assertEqual(shown[788118], set())
        self.assertEqual(boards(LOUSE_CASE)[0]["floor"]["quest_id"], QUEST_FLOOR[2])
        rows = recorded(HUNT_CASE)
        self.assertEqual(rows[DETECT_BOARD], ("3", "hunt:detected-target"))
        self.assertEqual(rows[STEP_BOARD], ("7", "hunt:detected-target"))
        detected = [(m["race_id"], m["y"], m["x"]) for raw in boards(HUNT_CASE)
                    if raw["turn"] == DETECT_BOARD for m in raw["detected_monsters"]]
        self.assertIn((GUARDIAN, 52, 153), detected)


class BreederRingsOutOfSightTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.record = Path(directory.name) / "breeder-floor.json"
        # DECLARED RECONSTRUCTION (module docstring): the stopped process's record.
        self.record.write_text(json.dumps({
            "floor": list(QUEST_FLOOR), "turn": boards(LOUSE_CASE)[0]["turn"],
            "state": {"breakthrough": True, "engagement": None}}) + "\n", encoding="utf-8")

    def drive(self):
        """Every recorded board: (board, key, reason, the breeder rings after it)."""
        policy = fresh(LOUSE_CASE, record=self.record)
        rows = []
        for raw in boards(LOUSE_CASE):
            key = decide(policy, raw)
            rows.append((raw, key, policy.last_reason,
                         frozenset(policy._breeder_quest_avoid_cells)))
        self.assertEqual(policy._breeder_breakthrough_floor, QUEST_FLOOR)
        self.assertEqual(breeder_quest.response(policy, parse_snapshot(
            copy.deepcopy(boards(LOUSE_CASE)[-1]), policy._monrace_knowledge)),
            breeder_quest.PURSUE)
        return rows

    def test_out_of_sight_the_rings_stay(self):
        rows = self.drive()
        out_of_sight = [(raw, rings) for raw, _key, _reason, rings in rows
                        if not any(m["race_id"] == LOUSE for m in raw["visible_monsters"])
                        and here(raw) in {Position(47, 73), Position(47, 75)}]
        self.assertGreaterEqual(len(out_of_sight), 10)
        corridor = {Position(y, x) for y in range(36, 46) for x in (73, 74, 75)}
        for raw, rings in out_of_sight:
            # bot-7404002a7: empty, the corridor north open again.
            self.assertTrue(rings & corridor, raw["turn"])

    def test_the_walks_do_not_step_back_and_forth(self):
        rows = self.drive()
        flips = {}
        for (before, key, _reason, _rings), (after, back, reason, _) in zip(rows, rows[1:]):
            if destination(before, key) == here(after) and destination(after, back) == here(before):
                pair = frozenset({here(before), here(after)})
                flips.setdefault(pair, []).append((after["turn"], back, reason))
        # bot-7404002a7: [46,74] and [47,75] traded six times (seek-loot '3' and '7').
        for pair, steps in flips.items():
            self.assertLessEqual(len(steps), 1, (sorted(pair), steps))


class HuntKeepsItsFrontierTest(unittest.TestCase):
    def test_the_walk_does_not_turn_to_a_frontier_closer_than_the_new_cell(self):
        policy = fresh(HUNT_CASE)
        targets = {}
        follow = goal_route.follow

        def observed(policy_, snapshot, predicate, *args):
            route = follow(policy_, snapshot, predicate, *args)
            if "hunt_target" in goal_route.goal_kind(predicate):
                targets.setdefault(snapshot.turn, []).append(route.target)
            return route

        decided = {}
        with mock.patch.object(goal_route, "follow", observed):
            for raw in boards(HUNT_CASE):
                if raw["turn"] > STEP_BOARD:
                    break
                decided[raw["turn"]] = (here(raw), decide(policy, raw), policy.last_reason)
        self.assertEqual(decided[DETECT_BOARD],
                         (Position(32, 131), "3", hunt_target.REASON))
        chosen = targets[DETECT_BOARD][-1]
        self.assertEqual(chosen, Position(31, 134))
        # From [33,132] the frontier is as near the target as the player (game distance 29):
        # bot-7404002a7 turned to Position(33, 135), "closer than the player" from there.
        self.assertEqual(set(targets.get(STEP_BOARD, [])) - {chosen}, set())
        position, _key, reason = decided[STEP_BOARD]
        self.assertEqual(position, Position(33, 132))
        self.assertNotEqual(reason, hunt_target.REASON)
        visit = hunt_target._visit(policy, parse_snapshot(
            copy.deepcopy(next(raw for raw in boards(HUNT_CASE) if raw["turn"] == STEP_BOARD)),
            policy._monrace_knowledge))
        self.assertIn(chosen, visit.spent_frontiers)
        self.assertIsNone(visit.position)

if __name__ == "__main__":
    unittest.main()
