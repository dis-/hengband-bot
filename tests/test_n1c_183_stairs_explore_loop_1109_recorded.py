"""n1-c life-183's loop stops on Angband 49F, 2026-11-09 (Magic-Eater Lv38).

Recorded: tests/fixtures/n1c-183-stairs-explore-loop-1109/
(tests/extract_n1c_183_stairs_explore_loop_1109_fixtures.py).  Every decision is the public
``choose_key`` of a fresh policy given the stop's remembered terrain (its policy-state;
DECLARED RECONSTRUCTION, as stops-1109), and fed the recorded rows in order: a ~f
``knowledge`` response goes to ``consume_skill_knowledge`` while the request is in flight,
as cli.py does.

20:33 (build b078e0b34), ``stairs-2033``: the blow that killed an 古代レッド・ドラゴン (index 67,
race 644) at [37,108] made the character Lv38; the level-up asked ~f on that board (2948402),
which returns before any observation, and the next board showed no message.  The kill line
was never read, the dragon stayed remembered awake at [37,108] (sleeper_reach_memory) and its
area was the routes' veto: at [37,117] (9 cells, outside its area) the whole area,
``stuck:seek-stairs`` stepped '7' into it to [36,116], where (8 cells) only the cells nearer
it were, and the explore stepped '3' back, until the loop detector.  Two defects:
- the consumed board's messages (``_with_skill_request_board_messages``);
- the goal walks (goal_route) kept off the retreats' own cells only, while the explore,
  descent and loot walks kept off the veto too (``_walk_veto``, one answer for every walker).
DECLARED COMPONENT PIN (the second): the live explore found no frontier off the veto at
[37,117] and its stair walk had a route west; a fresh policy has neither (the live process
cast mapping and light powers from its absorbed list, which a fresh policy has not read, and
its remembered terrain does not join the stairs).  So a goal walk west from the recorded
board is asked directly, through the same goal_route the stair walk takes: to [37,112], the
recorded way in from the west (decisions 403-404), inside the dragon's remembered area, with the dragon remembered as the live
process read it (DECLARED COUNTERFACTUAL: the kill line unread, the 20:33 build's reading).

20:44-20:45 (build 2ea922e5b, three stops), ``chest-2045``: at [5,39] a ネクサス・クイルスルグ
(index 3, race 480) at [4,58] was in view, the chest pipeline yielded and seek-loot stepped
'7' to [4,38]; there it was out of sight and ``chest:approach`` stepped '3' back toward the
chest at [7,53].  The chest now yields to a remembered hostile out of sight, as the loot
walk's block does (owner 2026-11-09 「起きた敵も最後の位置を覚える」).  DECLARED PHYSICS: from
[4,38] the player follows the decided moves on the recorded board (the monsters as shown
there), five game turns a decision.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import sleeper_reach_memory
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.test_dungeon_1031_recorded import skill
from tests.test_n1b_348_stops_1108_recorded import knowledge

FIXTURES = Path(__file__).with_name("fixtures") / "n1c-183-stairs-explore-loop-1109"
TERRAIN_SETS = ("known", "marked", "floor", "wall", "door", "rubble")
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
         "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
DRAGON = (67, 644)
QUYLTHULG = (3, 480)
KILL_TURN = 2948402
STAIRS_BOARD = 2948824  # [37,117]: live ('7', 'stuck:seek-stairs')


def case(name):
    with gzip.open(FIXTURES / f"{name}.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


STAIRS = case("stairs-2033")
CHEST = case("chest-2045")


def here(raw):
    return Position(raw["player"]["y"], raw["player"]["x"])


def boards(data):
    return [row for row in data["rows"] if row.get("type") == "player_turn"]


def recorded(data):
    rows = {}
    for row in data["decisions"]:
        rows.setdefault(row["turn"], (row["key"], row["reason"]))
    return rows


def fresh(data):
    policy = HengbotPolicy(monrace_knowledge=knowledge(data))
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


def drive(data, *, until=None, unread_kill=False):
    """Feed the recorded rows in order up to the board of ``until``: (policy, that board)."""
    policy = fresh(data)
    for row in data["rows"]:
        if row.get("type") == "knowledge":
            if getattr(policy, "_skill_exp_request_inflight", False):
                policy.consume_skill_knowledge(copy.deepcopy(row))
            continue
        raw = copy.deepcopy(row)
        if until is not None and raw["turn"] >= until:
            return policy, raw
        if unread_kill and raw["turn"] == KILL_TURN:
            raw["messages"] = []
        decide(policy, raw)
    return policy, None


def remembered(policy):
    memory = getattr(policy, sleeper_reach_memory.MEMORY, None)
    return set() if memory is None else set(memory[1])


class RecordedRowsTest(unittest.TestCase):
    def test_recorded_rows(self):
        rows = recorded(STAIRS)
        self.assertEqual(rows[2948399], ("4", "melee"))
        self.assertEqual(rows[KILL_TURN], ("~f\x1b", "periodic:skill-exp-knowledge"))
        self.assertEqual(rows[STAIRS_BOARD], ("7", "stuck:seek-stairs"))
        self.assertEqual(rows[2948828], ("3", "breakout:seek-frontier"))
        self.assertEqual(rows[2948843], ("3", "explore"))
        kill = [raw for raw in boards(STAIRS) if raw["turn"] == KILL_TURN]
        self.assertTrue(any("古代レッド・ドラゴンを葬り去った。" in raw["messages"] for raw in kill))
        self.assertEqual(kill[-1]["messages"], [])
        rows = recorded(CHEST)
        self.assertEqual(rows[2995517], ("7", "seek-loot"))
        self.assertEqual(rows[2995522], ("3", "chest:approach"))
        shown = {raw["turn"]: [(m["index"], m["race_id"]) for m in raw["visible_monsters"]]
                 for raw in boards(CHEST)}
        self.assertEqual(shown[2995522], [])
        self.assertIn(QUYLTHULG, shown[2995517])


class KillOnSkillRequestBoardTest(unittest.TestCase):
    def test_the_kill_on_the_request_board_forgets_the_dragon(self):
        policy, _ = drive(STAIRS, until=2948408)
        # bot-b078e0b34: the dragon stays remembered at [37,108] for the routes' veto.
        self.assertNotIn(DRAGON, remembered(policy))

    def test_the_loop_boards_keep_no_veto_and_no_stairs_walk(self):
        policy, _ = drive(STAIRS, until=STAIRS_BOARD - 1)
        for raw in boards(STAIRS):
            if raw["turn"] < STAIRS_BOARD:
                continue
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            self.assertEqual(policy._engagement_route_veto(snapshot), frozenset(), raw["turn"])
            decide(policy, raw)
            self.assertNotEqual(policy.last_reason, "stuck:seek-stairs", raw["turn"])


class StairWalkKeepsTheVetoTest(unittest.TestCase):
    def test_a_goal_walk_keeps_off_the_cells_the_explore_keeps_off(self):
        policy, raw = drive(STAIRS, until=STAIRS_BOARD, unread_kill=True)
        self.assertIn(DRAGON, remembered(policy))
        self.assertEqual(here(raw), Position(37, 117))
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.choose_key(snapshot)  # the board's own decision builds its grid index
        veto = policy._walk_veto(snapshot)
        self.assertIn(Position(36, 116), veto)
        west = Position(37, 112)
        remembered_board = policy._with_grid_memory(snapshot)  # as the ladder's walks read it
        self.assertTrue(remembered_board.grids[west].passable)
        step = policy._nearest_goal_step(remembered_board, lambda grid: grid.position == west)
        # bot-b078e0b34: Position(36, 116), the recorded '7' into the veto.
        self.assertFalse(step in veto, step)


class ChestYieldsOutOfSightTest(unittest.TestCase):
    def test_out_of_sight_the_chest_does_not_walk_back(self):
        policy = fresh(CHEST)
        start = None
        for raw in boards(CHEST):
            if raw["turn"] >= 2995300 and here(raw) == Position(4, 38):
                start = copy.deepcopy(raw)
                break
            decide(policy, raw)
        self.assertIsNotNone(start)
        self.assertIn(QUYLTHULG, remembered(policy))
        raw, visited, reasons = start, [here(start)], []
        for _ in range(5):
            key = decide(policy, raw)
            reasons.append(policy.last_reason)
            if key not in MOVES:
                break
            raw = copy.deepcopy(raw)
            raw["player"]["y"] += MOVES[key][0]
            raw["player"]["x"] += MOVES[key][1]
            raw["turn"] += 5
            visited.append(here(raw))
        # bot-2ea922e5b: ('3', 'chest:approach') back to [5,39] on the first board.
        self.assertNotIn("chest:approach", reasons)
        self.assertNotIn(Position(5, 39), visited)

    def test_the_recorded_boards_out_of_sight_leave_the_chest(self):
        policy = fresh(CHEST)
        for raw in boards(CHEST):
            decide(policy, raw)
            if raw["turn"] >= 2995300 and here(raw) == Position(4, 38):
                self.assertNotEqual(policy.last_reason, "chest:approach", raw["turn"])

if __name__ == "__main__":
    unittest.main()
