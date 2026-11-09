"""n1c-181-q2-breeder-1109: Q2 abandoned over the corpse masses at full HP.

Recorded: n1-c life-181 (Magic-Eater Lv20-21, 285 max HP) in Q2 下水道, 2026-11-09 12:52:52-
12:53:30 (tests/fixtures/n1c-181-q2-breeder-20261109.json.gz,
tests/extract_n1c_181_q2_breeder_1109_fixture.py).  It shot the corpse masses (死体の塊, race
202, 8d8 HP, NEVER_MOVE, MULTIPLY, IM_POIS) with plain bolts (27/shot) from the west end of their
room, two shots a kill.  The firing cell it walked to was the nearest one for the nearest mass,
at the far edge of the shot's reach (RANGED_MAX_DISTANCE), so after each kill the next mass was
out of reach and it walked again: 48 shots and 36 walks in the fight.  A mass with few neighbours
multiplies at 1/8 to 1/24 a turn (monster-processor.cpp decide_monster_multiplication), so the
masses its kills thinned bred back: the 20-attack window from turn 766740 to 767137 had 20 shots,
12 walks, 9 kills and 9 births and ended at 10 masses as it began, the floor latched
(breeder_stalemate) and turn 767148 read Recall (``breeder-breakthrough:recall``), which fails
the KILL_ALL quest (breeder_quest ABANDON).  Its one absorbed ball (悪臭雲, POIS) had no charge
left from turn 764190 and the masses are IM_POIS, so no area attack could catch them
(breeder_area_attack).

Now (owner 2026-11-08 「20行動で減らせないのであれば倒すアルゴリズム側に問題がある。」) the residual
breeder's firing cells are narrowed to those whose shot reaches the most breeders
(quest_firing_cells ``widest``), and (owner 2026-11-09 「加えて判断の窓を長く取る。20回は短いよう
だ。」→「100回」) the window is 100 attacks.

Every decision is the public ``choose_key`` over the recorded boards from the quest entry; the
asserted keys go through the production executor port.  Boards do not follow from any key the
replay decides differently from the record (the capture keeps no power list, so the recorded
absorbed-power casts are shots or steps in the replay).
DECLARED CONSTRUCTED (the walk and the clearing): after the recorded board of turn 766340 the
boards are that board with the player moved by the replay's own step keys, the turn advanced 10
per action and a mass removed after its second hit (the record: two shots a kill); no mass is
born.  DECLARED CONSTRUCTED (the window): after the last recorded board, that board repeats with
the turn advanced 10 per action and the replay shooting it unchanged.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import re
import unittest
from pathlib import Path

from hengbot import breeder_quest, breeder_stalemate, quest_firing_cells
from hengbot.model import Position, parse_snapshot
from hengbot.projection_path import projection_path
from hengbot.quest_knowledge import load_quest_knowledge
from tests import test_breeder_swarm_1102_recorded as swarm
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-181-q2-breeder-20261109.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
BOARDS = CASE["boards"]
QUEST_DEFINITIONS = Path("C:/hengband/lib/edit/quests")
MASS = 202
RECALL_TURN = 767148
RECALL_REASON = "breeder-breakthrough:recall"
APPROACH = "quest-strategy:q2-approach-residual-multiplier"
FIRE = "quest-strategy:q2-fire"
AFTER_KILL = 766340            # [8,24]: the mass at [8,34] died on this board
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
         "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def new_policy():
    policy = loops.new_policy({"boards": [BOARDS[0]], "home": None}, CASE["skill"],
                              monraces=CASE["monraces"])
    policy._quest_knowledge = load_quest_knowledge(QUEST_DEFINITIONS)
    # Entered from town (the boards begin at the entry), not a reconnect.
    policy._q2_reconnect_recovery_floor = None
    return policy


def decide(policy, raw):
    key = nokey.decide(policy, copy.deepcopy(raw), CASE["skill"])
    if key:
        policy.confirm_key_posted(key)
    return key


def replay(policy, boards):
    for raw in boards:
        decide(policy, raw)


def index_of(turn):
    return next(index for index, raw in enumerate(BOARDS) if raw["turn"] == turn)


def masses(raw):
    return [row for row in raw["visible_monsters"] if row["race_id"] == MASS]


def victim(raw, key):
    """The first monster on the shot's path (a direction or the target cursor)."""
    here = Position(raw["player"]["y"], raw["player"]["x"])
    if (direction := re.fullmatch(r"f.(\d)", key)) is not None:
        dy, dx = STEPS[direction.group(1)]
        aim = Position(here.y + 99 * dy, here.x + 99 * dx)
    else:
        y, x = here.y, here.x
        for step in re.fullmatch(r"f.\*p(\d*)t5\x1b", key).group(1):
            y, x = y + STEPS[step][0], x + STEPS[step][1]
        aim = Position(y, x)
    occupied = {(row["y"], row["x"]): row for row in raw["visible_monsters"]}
    return next((occupied[(pos.y, pos.x)] for pos in projection_path(here, aim, 99, lambda pos: False)
                 if (pos.y, pos.x) in occupied), None)


class Q2CorpseMassRecordedTest(swarm.PostedSwarmKey):
    def test_recorded_recall_on_a_window_that_did_not_reduce(self):
        rows = [row for row in CASE["decisions"] if row["reason"] == RECALL_REASON]
        self.assertEqual([(row["turn"], row["key"]) for row in rows], [(RECALL_TURN, "rf")])
        raw = BOARDS[index_of(RECALL_TURN)]
        self.assertEqual(raw["player"]["hp"], raw["player"]["max_hp"])
        self.assertEqual(len(masses(raw)), 10)
        window = [row["reason"] for row in CASE["decisions"] if 766740 < row["turn"] <= 767137]
        self.assertEqual((window.count(FIRE), window.count(APPROACH)), (20, 12))

    def test_after_a_kill_the_step_heads_where_the_shot_reaches_every_mass(self):
        policy = new_policy()
        start = index_of(AFTER_KILL)
        replay(policy, BOARDS[:start])
        raw = copy.deepcopy(BOARDS[start])
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        here = board.player.position
        self.assertEqual(here, Position(8, 24))
        breeders = [monster for monster in board.visible_monsters if monster.race_id == MASS]
        self.assertEqual(quest_firing_cells.reach(board, here, breeders), 0)
        key = decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("6", APPROACH))   # the record: "2", south
        self.post(policy, raw, key)
        # DECLARED CONSTRUCTED (module docstring): the next board, one step east.
        raw = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        raw["player"]["x"] += 1
        key = decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("fj6", FIRE))
        self.post(policy, raw, key)

    def test_the_masses_are_cleared_with_fewer_walks_than_kills(self):
        # DECLARED CONSTRUCTED (module docstring).
        policy = new_policy()
        start = index_of(AFTER_KILL)
        replay(policy, BOARDS[:start])
        raw = copy.deepcopy(BOARDS[start])
        total = len(masses(raw))
        walks = kills = 0
        hits = {}
        for _ in range(4 * total):
            key = decide(policy, raw)
            raw = dict(raw, turn=raw["turn"] + 10, messages=[])
            if key in STEPS:
                self.assertEqual(policy.last_reason, APPROACH)
                walks += 1
                raw["player"] = dict(raw["player"], y=raw["player"]["y"] + STEPS[key][0],
                                     x=raw["player"]["x"] + STEPS[key][1])
                continue
            self.assertTrue(key.startswith("fj"), (key, policy.last_reason))
            hit = victim(raw, key)
            self.assertIsNotNone(hit)
            hits[hit["index"]] = hits.get(hit["index"], 0) + 1
            if hits[hit["index"]] == 2:
                raw["visible_monsters"] = [row for row in raw["visible_monsters"] if row is not hit]
                raw["messages"] = [hit["name"] + "を倒した。"]
                kills += 1
            if not masses(raw):
                break
        self.assertEqual(kills, total)
        # The record walked 12 times for 9 kills in its last window (36 for the fight).
        self.assertLess(walks, kills // 2, (walks, kills))

    def test_the_window_is_one_hundred_attacks(self):
        policy = new_policy()
        replay(policy, BOARDS)
        floor = parse_snapshot(copy.deepcopy(BOARDS[-1]), policy._monrace_knowledge).floor_key
        self.assertNotEqual(policy._breeder_breakthrough_floor, floor)
        self.assertEqual(policy._breeder_engagement_race, MASS)
        start_count = policy._breeder_engagement_start_count
        attacks = policy._breeder_engagement_actions
        self.assertLess(attacks, breeder_stalemate.FLEE_AFTER_PLAYER_ACTIONS)
        # DECLARED CONSTRUCTED (module docstring): the last board again, shot unchanged.
        raw = copy.deepcopy(BOARDS[-1])
        count = len(masses(raw))
        latched_after = None
        for action in range(1, 3 * 100):
            raw = dict(raw, turn=raw["turn"] + 10, messages=[])
            key = decide(policy, raw)
            self.assertEqual((key, policy.last_reason), ("fj6", FIRE), action)
            if policy._breeder_breakthrough_floor == floor:
                latched_after = action
                break
        # The open window ends with fewer masses than it began (kept); the next one, opened at
        # the same count, ends unchanged after its hundredth attack and latches the floor,
        # which abandons the KILL_ALL quest.
        self.assertLess(count, start_count)
        self.assertEqual(latched_after, (100 - attacks) + 100, (attacks, start_count, count))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertTrue(breeder_quest.abandons_floor(policy, board))

if __name__ == "__main__":
    unittest.main()
