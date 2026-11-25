"""Quest 25 on n1-b life-419 (2026-11-26 05:00-05:01): the patrol detected the last quylthulg in a room never entered and walked its rounds elsewhere, recorded.

n1-b life-419 (Magic-Eater Lv40, Zombie, build bot-12d92ad85) on Quest 25 『幽霊屋敷』, every phase of
the plan over (battle phase 11, ``q25-battle.json``), the quest still TAKEN (type 6 KILL_ALL:
quest-completion-checker.cpp complete_kill_all wins it only on the death of the last hostile).  The
one hostile left was a Nexus quylthulg (480, monster index 8: NEVER_MOVE, INVISIBLE, EMPTY_MIND,
BLINK) at [13,10], in the shadow demons' room of the map (``S``, [11..13,10..12]), whose one door is
[10,11].  No board had shown that room: its cells and the door's far side were not on the remembered
map, the door closed.

 * Turn 3661154 the patrol cast the Rod of Detection through Powerful Activation (radius 45, the
   whole map); the board of turn 3661158 listed the quylthulg at [13,10].  No remembered walk reaches
   a cell beside it (the room unmapped), so ``_hunt`` answered None and the patrol walked its round
   ('9', ``quest-patrol:walk``); the next board no longer listed it, and ``_hunt_remembered``
   forgot the cell no remembered walk reached.
 * Each later round's detection (3661473, 3661929, 3662386, 3662857) listed it at [13,10] again; the
   fifth round ended in ``quest:blocked:quest-patrol-rounds`` at turn 3663324.

The rule (owner 2026-11-13 「全滅クエストで作戦を完了しても終了しない場合、周回して敵を探す。感知を
持っていれば感知して敵を探す」, found to be killed; 2026-11-09 the last cell of an enemy is
walked to): the walk to a found hostile passes the cells the map does not know inside the floor's
known walls (``kill_all_patrol._toward_unmapped``): a door no board has seen past is opened and the
room walked into.

Recorded: tests/fixtures/n1b-419-q25-patrol-1126.json.gz
(tests/extract_n1b_419_q25_patrol_1126_fixture.py): the boards and decisions of turns
3661151-3661211, 3661456-3661473 and the stop, and the battle record at the stop.  A fresh policy
restores the record through the real path and decides the recorded boards in order through the
public ``choose_key``.

DECLARED RECONSTRUCTED: the remembered magic-eater lists (the boards do not carry them), the rows
of test_n1c_208_q25_patrol_1115_recorded.lists; the battle record's turn set to the first replayed
board's.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import kill_all_patrol, quest25_battle as battle
from hengbot.model import Position, parse_snapshot
from tests.support import q25_house as q25
from tests.support import recorded as harness
from tests.test_n1c_208_q25_patrol_1115_recorded import lists

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-419-q25-patrol-1126.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

CAST = 3661154          # the patrol's powered cast of the absorbed Rod of Detection
FOUND = 3661158         # the board listing the quylthulg at [13,10]
NEXT = 3661165          # the next board: nothing listed
FOUND_AGAIN = 3661473   # the second round's detection board, the player at [9,15]
STOP = 3663324
QUYL, QUYL_INDEX, QUYL_CELL = 480, 8, (13, 10)
DOOR = (10, 11)         # the shadow demons' room's door, closed and never passed
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def boards():
    seen, unique = set(), []
    for raw in CASE["window"]["boards"]:
        if raw["turn"] not in seen:
            seen.add(raw["turn"])
            unique.append(raw)
    return unique


def board(turn):
    return copy.deepcopy(next(raw for raw in boards() if raw["turn"] == turn))


def recorded(turn):
    return [(row["reason"], row["key"]) for row in CASE["window"]["decisions"] if row["turn"] == turn]


def decide(policy, raw):
    return policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))


class _Replay(harness.ProductionHarness):
    def setUp(self):
        super().setUp()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def replay(self, last):
        """(policy, [(turn, reason, key)]) of the recorded boards ``CAST``..``last``."""
        first = board(CAST)
        record = dict(CASE["battle_record"], turn=first["turn"])   # DECLARED (module note)
        (self.directory / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies=q25.STRATEGIES)
        policy._q25_battle_record_path = self.directory / "q25-battle.json"
        policy._warning_cell_record_path = self.directory / "warning-cells.json"
        snapshot = parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge)
        policy.prime(snapshot)
        policy._skill_exp_cache = (0, 0, snapshot.player.level, policy._town_visit_epoch)
        policy._me_device_lists = lists()
        decided = []
        for raw in boards():
            if CAST <= raw["turn"] <= last:
                key = decide(policy, raw)
                decided.append((raw["turn"], policy.last_reason, key))
        return policy, decided


def unmapped_walk(policy, raw, key, target):
    """The cells of the walk the patrol takes from the board's player (``key`` its first step) to
    a cell beside ``target``, through the floor's unmapped cells as the patrol passes them."""
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    here = snapshot.player.position
    dy, dx = STEPS[key]
    path = [here, Position(here.y + dy, here.x + dx)]
    inside = kill_all_patrol._unmapped_inside(policy, snapshot)
    seen, queue = {path[-1]}, deque([(path[-1], ())])
    while queue:
        cell, trail = queue.popleft()
        if max(abs(cell.y - target[0]), abs(cell.x - target[1])) <= 1:
            return path + list(trail)
        for neighbor in kill_all_patrol._unmapped_neighbors(policy, snapshot, cell, inside):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, (*trail, neighbor)))
    return path


class TheRecordingTest(_Replay):
    def test_the_quest_is_still_taken_and_one_quylthulg_is_left_in_an_unmapped_room(self):
        stop = board(STOP)
        quest = next(row for row in stop["progress"]["quests"] if row["id"] == 25)
        self.assertEqual((quest["status"], quest["type"]), (1, 6))   # TAKEN, KILL_ALL
        for turn in (FOUND, FOUND_AGAIN):
            found = board(turn)["detected_monsters"]
            self.assertEqual([(row["race_id"], row["index"], row["y"], row["x"]) for row in found],
                             [(QUYL, QUYL_INDEX, *QUYL_CELL)])
        self.assertEqual(board(NEXT)["detected_monsters"], [])
        fight = CASE["battle_record"]["battle"]
        self.assertEqual(fight["phase"], len(battle.PHASES))
        # The room's cells are not on the map the patrol walks, the door closed.
        policy, _decided = self.replay(FOUND)
        snapshot = parse_snapshot(board(FOUND), policy._monrace_knowledge)
        for cell in ((11, 10), (11, 11), (12, 11), (13, 11), QUYL_CELL):
            self.assertNotIn(cell, policy._remembered_known_t, cell)
        self.assertTrue(snapshot.grids[Position(*DOOR)].is_closed_door)

    def test_the_recorded_chain(self):
        self.assertEqual(recorded(CAST), [(kill_all_patrol.POWERED_DETECT_REASON, "UCg")])
        self.assertEqual(recorded(FOUND), [(kill_all_patrol.WALK_REASON, "9")])
        self.assertEqual(recorded(FOUND_AGAIN), [(kill_all_patrol.WALK_REASON, "8")])
        self.assertEqual(recorded(STOP), [(kill_all_patrol.STOP_REASON, "5")])


class TheHuntTest(_Replay):
    def test_the_detected_quylthulg_is_walked_to_through_the_unmapped_room(self):
        """Revert-proof: before the fix the board of the detection walked the round ('9', walk)."""
        policy, decided = self.replay(FOUND)
        by_turn = {turn: (reason, key) for turn, reason, key in decided}
        self.assertEqual(by_turn[CAST], (kill_all_patrol.POWERED_DETECT_REASON, "UCg"))
        reason, key = by_turn[FOUND]
        self.assertEqual(reason, kill_all_patrol.HUNT_REASON)
        self.assertEqual(policy._kill_all_patrol.targets, {QUYL_INDEX: QUYL_CELL})
        walk = unmapped_walk(policy, board(FOUND), key, QUYL_CELL)
        self.assertIn(Position(*DOOR), walk)
        self.assertLessEqual(max(abs(walk[-1].y - QUYL_CELL[0]), abs(walk[-1].x - QUYL_CELL[1])), 1)

    def test_the_remembered_cell_is_walked_to_on_the_boards_after(self):
        """The next boards list nothing; the patrol keeps the cell and walks on toward the door."""
        policy, decided = self.replay(NEXT)
        by_turn = {turn: (reason, key) for turn, reason, key in decided}
        self.assertEqual(by_turn[NEXT][0], kill_all_patrol.HUNT_REASON)
        self.assertEqual(policy._kill_all_patrol.targets, {QUYL_INDEX: QUYL_CELL})

    def test_the_second_rounds_detection_board_walks_to_the_door(self):
        """From [9,15] (the recorded '8', a round walk) the walk heads west to the door [10,11]."""
        policy, _decided = self.replay(FOUND)
        policy._kill_all_patrol.targets = {}
        key = decide(policy, board(FOUND_AGAIN))
        self.assertEqual(policy.last_reason, kill_all_patrol.HUNT_REASON)
        walk = unmapped_walk(policy, board(FOUND_AGAIN), key, QUYL_CELL)
        self.assertIn(Position(*DOOR), walk)

    def test_a_cell_walled_in_by_known_walls_is_still_forgotten(self):
        """A hostile no walk reaches even through the unmapped cells (outside the map's known
        permanent walls) is passed for the round, as before."""
        policy, _decided = self.replay(FOUND)
        raw = board(FOUND)
        sealed = (18, 40)   # DECLARED CONSTRUCTED: beyond the map's walls (the floor is 22 x 66)
        raw["detected_monsters"][0]["y"], raw["detected_monsters"][0]["x"] = sealed
        policy._kill_all_patrol.targets = {}
        decide(policy, raw)
        self.assertNotEqual(policy.last_reason, kill_all_patrol.HUNT_REASON)


if __name__ == "__main__":
    import unittest

    unittest.main()
