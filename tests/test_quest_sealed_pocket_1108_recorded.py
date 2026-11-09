"""n1-a life-496, Angband 6F, RANDOM quest 49 (トラのホッブス, race 200), 2026-11-08 01:36-03:35.

The bot circled ``quest-search:loop`` for two hours (restarts on
stall:floor-dwell:quest-search:loop at 02:06, 02:38 and 03:09).  The known floor covers x 78-131 of
a 132-wide board and no frontier is left (map_memory open_frontiers 0 at 02:06); the door search
rounds searched the two dead ends only, (3,113) and (10,87), and the way on was not there.  A
tunnel through a room's outer wall is a secret door one time in five (floor/cave-generator.cpp
make_walls; grid/door.cpp place_random_door), which from inside reads as the outer wall.

Owner 2026-11-08: 「感知手段があるならそれを用いる。感知手段のないキャラクタの場合、扉になりうる
場所の探索を追加する。」 (quest_target_search ``door_means_key``, ``door_walls``).

Recorded (tests/extract_quest_sealed_pocket_1108_fixture.py): the stop board of 02:06:57 and the
decision rows of the three captures.  The warrior holds no door detection (j: Rod of Trap Location).
DECLARED CONSTRUCTED: the corridors the bot remembered.  The board draws a dark corridor's floor
blank and the walls beside it; the corridors are the blank grids reached from the recorded walk
and from the drawn floors and doors without crossing a drawn grid.  Also the player's walk on the
board (the player moved as the key says, the board otherwise the same; a closed door stays
closed), the lap count that makes the door search round due, the dead ends' spent rounds, the
carried means, and the board after its use.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import hengbot.policy  # noqa: F401 -- loads the modules in their cycle-safe order
from hengbot import quest_target_search as search
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SEARCH_KEY, SEARCH_LIMIT
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "quest-sealed-pocket-1108.json.xz"
FLOOR_ROW = [1, 2, 416, 1]
OPEN_TERRAIN = {1, 4, 5, 6, 13}  # floor, open and closed door, up and down stairs
DEAD_ENDS = {(3, 113), (10, 87)}
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1),
         "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
# The carried means (DECLARED): (tval, sval, name, command).
ROD_DOOR = (66, 1, "ドア/階段感知のロッド", "z")
STAFF_DOOR = (55, 13, "ドア/階段感知の杖", "u")
SCROLL_DOOR = (70, 29, "ドア/階段感知の巻物", "r")


def _pin():
    return json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))


def _cells(raw) -> dict:
    cells = {}
    for y, x, length, value in raw["grid_map"]["runs"]:
        for offset in range(length):
            cells[(y, x + offset)] = value
    return cells


def _with_corridors(raw, walked) -> dict:
    """The board with the remembered corridors laid as floor (the module docstring)."""
    grid_map = raw["grid_map"]
    cells, palette = _cells(raw), grid_map["palette"]
    height, width = grid_map["h"], grid_map["w"]
    seeds = {cell for cell in walked if cell not in cells}
    for (y, x), value in cells.items():
        if palette[value][0] in OPEN_TERRAIN:
            seeds |= {cell for cell in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)) if cell not in cells}
    corridors, stack = set(seeds), list(seeds)
    while stack:
        y, x = stack.pop()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cell = (y + dy, x + dx)
                if (cell not in cells and cell not in corridors
                        and 0 < cell[0] < height - 1 and 0 < cell[1] < width - 1):
                    corridors.add(cell)
                    stack.append(cell)
    floor = palette.index(FLOOR_ROW)
    cells.update((cell, floor) for cell in corridors)
    grid_map["runs"] = [[y, x, 1, value] for (y, x), value in sorted(cells.items())]
    return raw


def _next_board(raw, key=None):
    board = copy.deepcopy(raw)
    board["turn"] += 10
    board["messages"] = []
    if key in MOVES:
        board["player"]["y"] += MOVES[key][0]
        board["player"]["x"] += MOVES[key][1]
    return board


class QuestSealedPocketRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin = _pin()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.walked = {(row["position"]["y"], row["position"]["x"])
                      for session in cls.pin["sessions"] for row in session["decisions"]}

    def policy(self, *means):
        raw = _with_corridors(copy.deepcopy(self.pin["board"]), self.walked)
        for tval, sval, name, _ in means:
            raw["inventory"].append(dict(
                copy.deepcopy(raw["inventory"][0]), slot="t", tval=tval, sval=sval, count=1,
                known=True, aware=True, fully_known=True, charging=False, charging_count=0,
                charges=5, pval=5,
                name=name, weight=15))
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.prime(board)
        # DECLARED: the player has seen this floor (owner 2026-10-23: seen floor is explored).
        policy._remembered_marked_t.update(_cells(raw))
        return policy, raw

    def choose(self, policy, raw):
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))

    def to_the_search(self, policy, raw, limit=200):
        """Walk until the quest search answers: (key, board it answered on)."""
        for _ in range(limit):
            key = self.choose(policy, raw)
            if policy.last_reason.startswith("quest-search"):
                return key, raw
            raw = _next_board(raw, key)
        self.fail("the quest search never answered")

    def snapshot(self, policy, raw):
        return parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)

    # -- the recording -------------------------------------------------------

    def test_recorded_sealed_pocket(self):
        raw = self.pin["board"]
        self.assertEqual((raw["floor"]["quest_id"], raw["floor"]["level"], raw["floor"]["width"]), (49, 6, 132))
        self.assertEqual(raw["player"]["class_id"], 0)  # a warrior: no class spell
        columns = {x for _, x in _cells(raw)}
        self.assertEqual((min(columns), max(columns)), (78, 129))
        first = self.pin["sessions"][0]
        self.assertEqual(first["map_memory"]["open_frontiers"], 0)
        reasons = {row["reason"] for row in first["decisions"]}
        self.assertTrue({search.LOOP_REASON, search.DOOR_REASON, search.SEARCH_REASON} <= reasons)
        searched = {(row["position"]["y"], row["position"]["x"])
                    for row in first["decisions"] if row["reason"] == search.SEARCH_REASON}
        self.assertEqual(searched, DEAD_ENDS)
        # No door detection in the pack: the trap rod (sval 0) only detects traps (cmd-zaprod.cpp).
        held = {(item["tval"], item.get("sval")) for item in raw["inventory"]}
        self.assertFalse(held & set(search.CARRIED_DOOR_MEANS))
        self.assertIn((66, 0), held)
        # The two later sessions only circled.
        for session in self.pin["sessions"][1:]:
            self.assertEqual({row["reason"] for row in session["decisions"]}, {search.LOOP_REASON})

    def test_the_board_reaches_the_loop_with_walls_a_door_can_be_in(self):
        policy, raw = self.policy()
        key, raw = self.to_the_search(policy, raw)
        self.assertEqual(policy.last_reason, search.LOOP_REASON)
        board = self.snapshot(policy, raw)
        routes = search._routes(policy, board)
        walls = search.door_walls(policy, board, routes)
        self.assertTrue({(cell.y, cell.x) for cell in search._dead_ends(policy, board, routes)} >= DEAD_ENDS)
        # The rooms' west walls, facing the floor never seen (x < 78).
        self.assertTrue(any(wall.x <= 81 for wall in walls), sorted(walls))
        self.assertFalse(search.door_means_held(policy, board))

    # -- without a means: the walls a door can be in are searched ---------------

    def test_without_a_means_the_round_searches_beside_the_walls_after_the_dead_ends(self):
        policy, raw = self.policy()
        key, raw = self.to_the_search(policy, raw)
        memory = getattr(policy, search.MEMORY)
        memory.laps = search.DOOR_SEARCH_LAPS  # DECLARED: three laps circled
        raw = _next_board(raw, key)
        self.choose(policy, raw)
        self.assertTrue(memory.door_search)
        # DECLARED: the dead ends had their rounds, as recorded (02:06, nothing found).
        board = self.snapshot(policy, raw)
        for dead_end in search._dead_ends(policy, board, search._routes(policy, board)):
            for _ in range(SEARCH_LIMIT):
                policy._record_wall_search(dead_end)
        rows = []
        for _ in range(120):
            key = self.choose(policy, raw)
            rows.append((key, policy.last_reason, (raw["player"]["y"], raw["player"]["x"])))
            if key == SEARCH_KEY:
                break
            raw = _next_board(raw, key)
        self.assertEqual(rows[0][1], search.DOOR_REASON, rows[:3])
        self.assertEqual(rows[-1][:2], (SEARCH_KEY, search.SEARCH_REASON), rows[-3:])
        here = Position(*rows[-1][2])
        self.assertNotIn(rows[-1][2], DEAD_ENDS)
        board = self.snapshot(policy, raw)
        walls = search.door_walls(policy, board, search._routes(policy, board))
        self.assertTrue(search._beside(here, walls), here)
        self.assertTrue(memory.door_search)
        self.assertEqual({reason for _, reason, _ in rows}, {search.DOOR_REASON, search.SEARCH_REASON})

    # -- with a means: it is used, once where it reaches -------------------------

    def test_with_a_means_it_is_used_when_the_search_starts(self):
        for means in (ROD_DOOR, STAFF_DOOR, SCROLL_DOOR):
            with self.subTest(means[2]):
                policy, raw = self.policy(means)
                key, raw = self.to_the_search(policy, raw)
                self.assertEqual(policy.last_reason, search.DOOR_MEANS_REASON)
                self.assertEqual(key[0], means[3])
                self.assertEqual(key[1], "t")
                board = self.snapshot(policy, raw)
                self.assertTrue(search.door_means_held(policy, board))
                # The board after the use (DECLARED): the turn passed, nothing failed.
                after = _next_board(raw)
                if means is SCROLL_DOOR:
                    after["inventory"] = [item for item in after["inventory"] if item["slot"] != "t"]
                self.choose(policy, after)
                memory = getattr(policy, search.MEMORY)
                here = Position(raw["player"]["y"], raw["player"]["x"])
                self.assertEqual([centre for centre, _ in memory.door_casts], [here])
                self.assertNotEqual(policy.last_reason, search.DOOR_MEANS_REASON)

    def test_with_a_rod_the_round_does_not_search_the_walls(self):
        policy, raw = self.policy(ROD_DOOR)
        key, raw = self.to_the_search(policy, raw)
        board = self.snapshot(policy, raw)
        memory = getattr(policy, search.MEMORY)
        # DECLARED: the rod is charging after its use (a charging rod is still held).
        raw = _next_board(raw, key)
        raw["inventory"][-1].update(charging=True, charging_count=1)
        memory.laps = search.DOOR_SEARCH_LAPS
        self.choose(policy, raw)
        board = self.snapshot(policy, raw)
        for dead_end in search._dead_ends(policy, board, search._routes(policy, board)):
            for _ in range(SEARCH_LIMIT):
                policy._record_wall_search(dead_end)
        self.choose(policy, _next_board(raw))
        self.assertEqual(policy.last_reason, search.LOOP_REASON)
        self.assertFalse(memory.door_search)


if __name__ == "__main__":
    unittest.main()
