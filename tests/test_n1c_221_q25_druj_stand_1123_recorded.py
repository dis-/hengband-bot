"""Quest 25 on n1-c life-221 (2026-11-23 04:59-05:03): the stairway and the druj fought off the plan's stands, recorded.

n1-c life-221 (Magic-Eater Lv39) on Quest 25 『幽霊屋敷』.  Owner plan (strategy/quests/QUEST_25.jsonc
``revised_plan_draft``): the stairway to hell [13,29] from [13,27] (「[13,27] から階段までは距離2」),
the druj [11,18] from [13,20] (「ドアを開けずに13,20に移動して、11,19を岩石溶解して11,19に範囲攻撃」);
owner 2026-11-23 「立ち位置を守れば一切の反撃を受けずに倒せた」.

 * 05:00:39 (turn 3191513): the stairway phase on its stand [13,27] keyed ``o6``.  With easy_open
   and the one closed door [13,28] around, do_cmd_open took the direction itself and the ``6``
   walked onto the opened door, beside the stairway.  Its touch stole (「泥棒は笑って逃げた！」: the
   thief teleports away) and the phase shot the empty grid [13,29] until 05:03:14 (turn 3201816).
 * 05:03:15 (turn 3202245): the walk to a cell that sees it keyed ``o4`` from [11,20], opening the
   druj's door [11,19] and stepping into the doorway beside the druj.
 * 05:03:24-34 (turns 3207204-3207646): the druj's phase, the door open, walked to its line
   ([11,25], [12,24]), was cursed (HP 672 -> 389) and shot it from [12,24] (``UB0@11,18``).

The fix: observed_input posts the ``o`` alone and releases the direction only at the observed
direction question, for every producer (tests/test_easy_open_direction_1123_recorded.py); ``_druj_shut`` keeps every walk of the plan off [11,19] while the
druj lives; ``_druj`` goes to [13,20] and aims the ball at [11,19] with the door already open too
([13,20] is out of the druj's line either way).

Recorded: tests/fixtures/n1c-221-q25-druj-stand-1123.json.gz
(tests/extract_n1c_221_q25_druj_stand_1123_fixture.py).  A fresh policy decides through the public
``choose_key``.

DECLARED CONSTRUCTED: the battle record (the run kept none of those turns): the phase the decision
names (「stairway」 or 「druj」) with the roster before it counted killed; the player moved to [13,20]
or [12,27] where a test says so.
DECLARED RECONSTRUCTED: the remembered magic-eater lists (the boards do not carry them): the rows of
tests/test_n1c_208_q25_patrol_1115_recorded.lists with the wands ロケット (the run cast it powerfully,
``UB0@11,18``) and 岩石溶解.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_battle_record
from hengbot.model import parse_snapshot
from tests.support import q25_house as q25
from tests import test_n1c_208_q25_patrol_1115_recorded as life208

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-221-q25-druj-stand-1123.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

geo = battle.geo
STAIR_OPEN = 3191513     # 'o6' on the stand [13,27]
STAIR_SHOT = 3191524     # the first shot, on [13,28]
TO_DRUJ_DOOR = 3202245   # 'o4' from [11,20], the walk to a sight
DRUJ_LINE = 3207208      # [12,24], the door open: 'UB0@11,18'
DRUJ_WALK = 3207204      # [11,25], the walk to its line
STAIRWAY_CELL = (13, 29)


def board(turn):
    return copy.deepcopy(next(raw for raw in CASE["boards"] if raw["turn"] == turn))


def decisions(turn):
    return [row for row in CASE["decisions"] if row["turn"] == turn]


def at(raw, cell):
    """DECLARED CONSTRUCTED: the player on ``cell``."""
    moved = copy.deepcopy(raw)
    moved["player"] = dict(moved["player"], y=cell[0], x=cell[1])
    return moved


def lists():
    """DECLARED RECONSTRUCTED (module note)."""
    found = life208.lists()
    found["wand"] = (0, (life208._row("ロケット", current=10, max=10),
                         life208._row("岩石溶解", current=5, max=5)))
    return found


def record(phase, turn, *, druj_killed=False):
    """DECLARED CONSTRUCTED (module note)."""
    kills = {race: count for race, count in geo.ROSTER.items()
             if race not in (geo.DRUJ, geo.STAIRWAY, geo.MASS)}
    if phase == "druj":
        kills[geo.STAIRWAY] = 1
    if druj_killed:
        kills[geo.DRUJ] = 1
    fought = battle.Battle(phase=battle.PHASE_NAMES.index(phase), kills=kills)
    carried = {name: quest25_battle_record._encode(getattr(fought, name))
               for name in fought.__dataclass_fields__ if name not in quest25_battle_record._NOT_CARRIED}
    return {"version": quest25_battle_record.VERSION, "floor": [0, 48, 25], "turn": turn,
            "battle": carried, "board": None}


def new_policy(directory, raw, phase, **changes):
    directory = Path(directory)
    (directory / "q25-battle.json").write_text(json.dumps(record(phase, raw["turn"], **changes)),
                                               encoding="utf-8")
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    policy._q25_battle_record_path = directory / "q25-battle.json"
    policy._warning_cell_record_path = directory / "warning-cells.json"
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    policy.prime(snapshot)
    policy._skill_exp_cache = (0, 0, snapshot.player.level, policy._town_visit_epoch)
    policy._me_device_lists = lists()
    return policy


def decide(policy, raw):
    """The first key on ``raw`` that is not the policy's own periodic list read (posted each)."""
    key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
    for _read in range(4):
        if not policy.last_reason.startswith("periodic:"):
            break
        policy.confirm_key_posted(key)
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
    return key


def ctx_of(policy, raw):
    policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
    return battle._ctx(policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))


def stairway_shown(raw):
    return [(row["y"], row["x"]) for row in raw["detected_monsters"] if row["race_id"] == geo.STAIRWAY]


class TheRecordingTest(unittest.TestCase):

    def test_the_open_on_the_stand_walked_onto_the_door_and_the_stairway_left(self):
        [opened] = decisions(STAIR_OPEN)[-1:]
        self.assertEqual((opened["reason"], opened["key"], opened["y"], opened["x"]),
                         (battle.OPEN_REASON, "o6", *geo.STAIRWAY_STAND))
        [shot] = decisions(STAIR_SHOT)[:1]
        self.assertEqual((shot["y"], shot["x"], shot["key"]), (*geo.STAIRWAY_DOOR, "UB3@13,29"))
        stolen = [row for row in CASE["decisions"] if STAIR_SHOT <= row["turn"] < STAIR_SHOT + 20]
        self.assertTrue(any("泥棒は笑って逃げた！" in text for row in stolen for text in row["messages"]))
        self.assertEqual(stairway_shown(board(STAIR_OPEN)), [STAIRWAY_CELL])
        self.assertEqual(stairway_shown(board(STAIR_SHOT)), [])
        self.assertEqual(stairway_shown(board(TO_DRUJ_DOOR)), [(2, 5)])

    def test_the_walk_to_a_sight_opened_the_druj_door_and_the_druj_was_fought_from_its_line(self):
        [walk] = decisions(TO_DRUJ_DOOR)
        self.assertEqual((walk["reason"], walk["key"], walk["y"], walk["x"]),
                         (battle.SIGHT_REASON, "o4", 11, 20))
        [shot] = decisions(DRUJ_LINE)
        self.assertEqual((shot["reason"], shot["key"], shot["y"], shot["x"]),
                         ("ranged:magic-eater-powerful", "UB0@11,18", 12, 24))
        kill = [row for row in CASE["decisions"] if "手のドルジを倒した。" in row["messages"]]
        self.assertEqual([(row["y"], row["x"]) for row in kill], [(12, 24)])


class TheStairwayStandTest(unittest.TestCase):

    def test_the_stand_opens_the_door_without_a_step(self):
        raw = board(STAIR_OPEN)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw, "stairway")
            key = decide(policy, raw)
            # ``o`` + direction; observed_input posts the ``o`` alone (easy_open, one door around).
            self.assertEqual((key, policy.last_reason), ("o6", battle.OPEN_REASON))

    def test_control_two_closed_doors_around_keep_the_direction(self):
        """DECLARED CONSTRUCTED: the player on [12,27], beside both [11,28] and [13,28]."""
        raw = at(board(STAIR_OPEN), (12, 27))
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw, "stairway")
            ctx = ctx_of(policy, raw)
            # The door's key through the plans' one door entry (quest_plan_base.plan_door, 2026-11-23 (a)-4).
            self.assertEqual(battle._open_key(ctx, geo.STAIRWAY_DOOR), "o3")
            self.assertEqual(policy.last_reason, battle.OPEN_REASON)


class TheDrujDoorTest(unittest.TestCase):

    def test_no_walk_of_the_plan_opens_the_druj_door_while_it_lives(self):
        raw = board(TO_DRUJ_DOOR)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw, "stairway")
            ctx = ctx_of(policy, raw)
            self.assertTrue(ctx.door_closed(geo.DRUJ_DOOR))
            self.assertIsNone(battle._walk_to_sight(ctx, STAIRWAY_CELL, {geo.DRUJ_DOOR}))

    def test_control_with_the_druj_dead_the_door_is_walked_through(self):
        raw = board(TO_DRUJ_DOOR)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw, "stairway", druj_killed=True)
            ctx = ctx_of(policy, raw)
            self.assertEqual(battle._walk_to_sight(ctx, STAIRWAY_CELL, {geo.DRUJ_DOOR}), "o4")


class TheDrujStandTest(unittest.TestCase):

    def test_the_door_open_the_phase_walks_to_its_stand_not_its_line(self):
        for turn in (DRUJ_WALK, DRUJ_LINE):
            raw = board(turn)
            with TemporaryDirectory() as directory:
                policy = new_policy(directory, raw, "druj")
                ctx = ctx_of(policy, raw)
                self.assertFalse(ctx.door_closed(geo.DRUJ_DOOR))
                key = decide(policy, raw)
                self.assertEqual(policy.last_reason, battle.WALK_REASON, (turn, key))
                path = battle._path(ctx, {geo.DRUJ_AREA_STAND})
                self.assertEqual(path[-1], geo.DRUJ_AREA_STAND)
                self.assertEqual(key, battle._direction(ctx.here, path[1]), turn)

    def test_on_the_stand_the_ball_is_aimed_at_the_open_door(self):
        raw = at(board(DRUJ_LINE), geo.DRUJ_AREA_STAND)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw, "druj")
            ctx = ctx_of(policy, raw)
            self.assertNotIn(geo.DRUJ_AREA_STAND, geo.line_cells(ctx.open_terrain(), (11, 18)))
            key = decide(policy, raw)
            self.assertTrue(key.endswith("@11,19"), (key, policy.last_reason))

    def test_control_the_door_closed_the_stand_melts_it(self):
        raw = at(board(STAIR_OPEN), geo.DRUJ_AREA_STAND)
        with TemporaryDirectory() as directory:
            policy = new_policy(directory, raw, "druj")
            key = decide(policy, raw)
            self.assertEqual(policy.last_reason, battle.MELT_REASON, key)
            self.assertTrue(key.endswith("@11,19"), key)


if __name__ == "__main__":
    unittest.main()
