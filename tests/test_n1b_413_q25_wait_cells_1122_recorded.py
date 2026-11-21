"""Quest 25 on n1-b life-413 (2026-11-22 01:21-01:47): the waits nothing came to, recorded.

Owner 2026-11-22 (verbatim): 「敵の行動アルゴリズムを確認して待つ場所を精査する必要がある。立ち位置が悪いと
幾ら待っても来ない」, and the answers: phase 1's ranged wait is [10,1] with the door [9,1] open (it
replaces 2026-11-06 「[13,1] から」); phase 5 waits for the dreadmaster in the east big room, on a cell
its deterministic movement brings it to, chosen by the existing rules (it replaces [1,17] / [1,9]).

n1-b life-413 (Magic-Eater Lv37, Zombie) on Quest 25 『幽霊屋敷』:

 * Phase 1, ranged: the hound, the vampire lord and the skeletal tyrannosaur killed by turn 2507807,
   the ambush held [13,1] (``quest-strategy:hold`` '5') with the door [9,1] open until the 5000
   quiet actions ran out (turn 2557532, about 49,500 game turns).  The spectral tyrannosaur went
   back and forth between [9,19] and [8,19]: the game's flow (grid/grid.cpp update_flow,
   monster_flow_depth 32) does not reach it from [13,1] (35 steps), it does from [10,1] (32).
 * Phase 5, the melee style: the walk reached [1,17] at turn 2563375 and held there until a
   random move (RAND_25) brought the dreadmaster (killed at turn 2573130, about 9,750 game turns).
   From [12,24] its own movement (PASS_WALL through the doors, not the permanent inner walls) goes
   back and forth for a player on [1,17]; it comes to [1,19].

Recorded: tests/fixtures/n1b-413-q25-wait-cells-1122.json.gz
(tests/extract_n1b_413_q25_wait_cells_1122_fixture.py): the boards and decisions of turns
2507807-2507818 and 2563370-2563386, and the battle record at the floor's last stop.  A fresh
policy restores a record through the real path and decides the recorded boards through the public
``choose_key``.

DECLARED RECONSTRUCTED: each phase's battle record from the stop's (the kills read before the
board, by their recorded turns; the phase; ``ready``; the style the recorded wait shows -- ranged
on [13,1], melee on [1,17]; the north corridor's cleared traps the walk had crossed); the remembered
magic-eater lists (the rows of test_n1c_208_q25_patrol_1115_recorded.lists).  DECLARED CONSTRUCTED:
the player moved to [10,1] on a recorded phase-1 board and to [1,19] on a recorded phase-5 board (the
recorded run never held there).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_geometry as geo, quest_room_sweep, quest_wait_placement
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import WAIT_KEY
from tests.support import q25_house as q25
from tests.support import recorded as harness
from tests.test_n1c_208_q25_patrol_1115_recorded import lists

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-413-q25-wait-cells-1122.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

KILLED_THIRD = 2507807        # the skeletal tyrannosaur's kill line; the holds on [13,1] follow
AMBUSH_HOLDS = (2507812, 2507818)
AT_DOOR = 2563370             # on the door [1,18]: the recorded walk west to [1,17]
DREAD_HOLDS = (2563375, 2563380, 2563386)
HOLD = "quest-strategy:hold"


def board(turn):
    return copy.deepcopy(next(raw for raw in CASE["window"]["boards"] if raw["turn"] == turn))


def recorded(turn):
    return [(row["reason"], row["key"]) for row in CASE["window"]["decisions"] if row["turn"] == turn]


def reconstructed(turn, phase, style, cleared=()):
    """DECLARED RECONSTRUCTED (module note): the battle record as it stood before ``turn``."""
    stop = CASE["battle_record"]["battle"]
    kill_turns = [item["tuple"] for item in stop["kill_turns"]["tuple"] if item["tuple"][1] < turn]
    kills = {}
    for race, _at in kill_turns:
        kills[race] = kills.get(race, 0) + 1
    fight = {"phase": battle.PHASE_NAMES.index(phase), "ready": True, "style": style, "enlightened": True,
             "kills": {"dict": [[race, count] for race, count in kills.items()]},
             "kill_turns": {"tuple": [{"tuple": list(item)} for item in kill_turns]},
             "cleared": {"set": [{"tuple": list(cell)} for cell in cleared]}}
    return {"version": 1, "floor": CASE["battle_record"]["floor"], "turn": turn, "battle": fight, "board": None}


class _Replay(harness.ProductionHarness):
    def setUp(self):
        super().setUp()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def policy(self, raw, record):
        (self.directory / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies=q25.STRATEGIES)
        policy._q25_battle_record_path = self.directory / "q25-battle.json"
        policy._warning_cell_record_path = self.directory / "warning-cells.json"
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.prime(snapshot)
        policy._skill_exp_cache = (0, 0, snapshot.player.level, policy._town_visit_epoch)
        policy._me_device_lists = lists()
        return policy

    def decide(self, policy, raw):
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        return str(key), policy.last_reason

    def ambush_policy(self, raw):
        return self.policy(raw, reconstructed(raw["turn"], "ambush", "ranged"))

    def dread_policy(self, raw):
        return self.policy(raw, reconstructed(raw["turn"], "dreadmaster", "melee", geo.NORTH_CORRIDOR))


def _closed(raw, cell) -> bool:
    snapshot = parse_snapshot(copy.deepcopy(raw), q25.RACES)
    return snapshot.grid_at(Position(*cell)).is_closed_door


class TheRecordingTest(_Replay):
    def test_the_ambush_held_13_1_with_the_door_open_and_the_tyrannosaur_went_back_and_forth(self):
        for turn in AMBUSH_HOLDS:
            raw = board(turn)
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), geo.START)
            self.assertFalse(_closed(raw, geo.WEST_DOOR))
            self.assertEqual(recorded(turn), [(HOLD, WAIT_KEY)])
        cells = {(row["y"], row["x"]) for turn in (KILLED_THIRD, *AMBUSH_HOLDS)
                 for row in board(turn)["detected_monsters"] if row["race_id"] == geo.SPECTRAL_T}
        self.assertLessEqual(cells, {(9, 19), (8, 19)})

    def test_phase_5_walked_to_1_17_and_held_there(self):
        self.assertEqual(recorded(AT_DOOR), [(battle.WALK_REASON, "4")])
        for turn in DREAD_HOLDS:
            raw = board(turn)
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (1, 17))
            self.assertEqual(recorded(turn), [(HOLD, WAIT_KEY)])
            dread = [(row["y"], row["x"]) for row in raw["detected_monsters"] if row["race_id"] == geo.DREADMASTER]
            self.assertEqual(dread, [(12, 24)])


class TheMovementTest(_Replay):
    """quest_wait_placement's reading of the game's movement on the recorded boards."""

    def test_the_spectral_tyrannosaur_comes_to_10_1_not_13_1(self):
        raw = board(AMBUSH_HOLDS[0])
        policy = self.ambush_policy(raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        navigator = quest_room_sweep._navigator(policy, snapshot, geo.QUEST_ID)
        tyrannosaur = next(monster for monster in snapshot.detected_monsters if monster.race_id == geo.SPECTRAL_T)
        cell = (tyrannosaur.position.y, tyrannosaur.position.x)
        come = quest_wait_placement.come_cells(policy, snapshot, navigator, geo.SPECTRAL_T, cell,
                                               [(13, 1), (12, 1), (10, 1)], tyrannosaur)
        self.assertEqual(come, ((10, 1),))

    def test_the_dreadmaster_comes_to_the_east_room_not_1_17(self):
        raw = board(DREAD_HOLDS[0])
        policy = self.dread_policy(raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        navigator = quest_room_sweep._navigator(policy, snapshot, geo.QUEST_ID)
        dread = next(monster for monster in snapshot.detected_monsters if monster.race_id == geo.DREADMASTER)
        come = quest_wait_placement.come_cells(policy, snapshot, navigator, geo.DREADMASTER, (12, 24),
                                               [(1, 17), (1, 9), (2, 9), (1, 19), (2, 22), (8, 25)], dread)
        self.assertEqual(come, ((1, 19), (2, 22), (8, 25)))


class TheAmbushTest(_Replay):
    def test_on_13_1_the_ranged_ambush_walks_to_10_1(self):
        for turn in AMBUSH_HOLDS:
            raw = board(turn)
            policy = self.ambush_policy(raw)
            self.assertEqual(self.decide(policy, raw), ("8", battle.WALK_REASON), turn)

    def test_on_10_1_it_holds_with_the_door_open(self):
        raw = board(AMBUSH_HOLDS[0])
        raw["player"].update(y=10, x=1)   # DECLARED CONSTRUCTED (module note)
        policy = self.ambush_policy(raw)
        self.assertEqual(self.decide(policy, raw), (WAIT_KEY, HOLD))


class TheDreadmasterTest(_Replay):
    def test_on_the_door_the_walk_goes_on_into_the_east_room(self):
        raw = board(AT_DOOR)
        policy = self.dread_policy(raw)
        self.assertEqual(self.decide(policy, raw), ("6", battle.WALK_REASON))

    def test_on_1_17_it_does_not_hold_but_walks_east(self):
        for turn in DREAD_HOLDS:
            raw = board(turn)
            policy = self.dread_policy(raw)
            self.assertEqual(self.decide(policy, raw), ("6", battle.WALK_REASON), turn)

    def test_on_1_19_it_holds(self):
        raw = board(DREAD_HOLDS[0])
        raw["player"].update(y=1, x=19)   # DECLARED CONSTRUCTED: where the walk ends
        policy = self.dread_policy(raw)
        self.assertEqual(self.decide(policy, raw), (WAIT_KEY, HOLD))


if __name__ == "__main__":
    import unittest
    unittest.main()
