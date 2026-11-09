"""Quest 25 on n1-c life-174 (2026-11-09 03:16:34-03:17:01): the corridor trap search, recorded.

n1-c life-174 (Magic-Eater Lv36) took the haunted house at 03:16:34 and, teleported to [2,19] in
the ambush, walked back west along the north corridor, whose ten cells [1,8]-[1,17] the map
always traps.  On [1,18] it aimed the absorbed Rod of Disarming west ('mCo4'); the cast failed
once and then went off: 「まばゆい閃光が走った！ <x10>」 -- KILL_TRAP flashed on each of the ten
traps of the row (spells-beam.cpp disarm_trap is a PROJECT_BEAM; effect-feature.cpp KILL_TRAP
prints the flash and DISARMs every trap grid of the path, hidden ones included).  The plan counted
only [1,17] answered, aimed the rod again before each of the next five steps and the wand once,
and on [1,11], with nothing left to aim, searched [1,10] for a trap that was gone.  The owner's
phase-5 rule searches an always-trapped cell until the trap is found (2026-11-06 「見つかるまで
探す」), so it searched until the loop guard stopped the bot (03:16:55), and again after the
restart (03:17:01): the restarted process carried the battle (quest25_battle_record) without
[1,10] answered.

Recorded: tests/fixtures/n1c-174-q25-loops-1109.json.gz (tests/extract_n1c_174_q25_loops_1109_fixture.py),
one board per recorded decision of three processes on the quest floor, with the recorded reason
and key: the first from the floor's entry (decision 783) through its own loop stop (1099, the
counted recharge rest on [2,24], left to the owner), the second (decisions 0-69) and the third
(0-39) through theirs.  One policy decides the first process's boards in order through the public
``choose_key``; a fresh policy decides the second's, restoring the battle the first one wrote
through the real record (quest25_battle_record, the path cli.py gives it); a third the third's.

DECLARED CONSTRUCTED: the first policy holds the magic-eater lists its own process held at its
town arrival (03:16:03, the town-arrival checkpoint of the same process): the ring's boards do not
carry the lists the executor read off the screen after each ``b``.  A restarted process holds no
lists (``_me_device_lists`` is not carried across a restart), as live.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle
from hengbot.model import Position, _parse_items, parse_snapshot
from tests import test_q25_haunted_house as q25


with gzip.open(Path(__file__).with_name("fixtures") / "n1c-174-q25-loops-1109.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

PARTS = ("first", "second", "third")
FLASH = "まばゆい閃光が走った！ <x10>"
BEAM_OFF = 879          # the first process's board after the beam that went off from [1,18]
CORRIDOR_STEPS = range(880, 893)   # [1,17] .. [1,12]: the recorded aims and steps
SEARCHED = 893          # the first process's first search of [1,10] from [1,11]
SECOND_SEARCH = 14      # the second process's first search of [1,10]
ITEMS_ON_CELL = 30      # from here on the second process's boards show items on [1,10]


def board(part, sequence):
    for raw, row in zip(CASE[part]["boards"], CASE[part]["recorded"]):
        if row["sequence"] == sequence:
            return raw, row
    raise KeyError((part, sequence))


def new_policy(first, *, lists, record):
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    first = copy.deepcopy(first)
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(CASE["skill"]), turn=first["turn"],
        player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
    policy.consume_home_knowledge(tuple(_parse_items(CASE["home"]["knowledge"]["items"], protocol=3)))
    if lists:
        policy._me_device_lists = {kind: (turn, tuple(rows)) for kind, (turn, rows) in CASE["lists"].items()}
    policy._q25_battle_record_path = record
    return policy


def replay():
    """(part, sequence) -> (key, reason): each process decided by its own policy, in order."""
    answers = {}
    with TemporaryDirectory() as directory:
        record = Path(directory) / "q25-battle.json"
        for part in PARTS:
            boards = CASE[part]["boards"]
            policy = new_policy(boards[0], lists=part == "first", record=record)
            for raw, row in zip(boards, CASE[part]["recorded"]):
                snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
                key = str(policy.choose_key(snapshot))
                answers[part, row["sequence"]] = (key, policy.last_reason)
                policy.confirm_key_posted(key)
    return answers


ANSWERS = {}


def replay_answers():
    if not ANSWERS:
        ANSWERS.update(replay())
    return ANSWERS


def answer(part, sequence):
    return replay_answers()[part, sequence]


class Q25CorridorTrapSearchTest(unittest.TestCase):

    def test_the_recording(self):
        raw, row = board("first", BEAM_OFF)
        self.assertEqual((raw["floor"]["quest_id"], raw["floor"]["level"]), (25, 48))
        self.assertIn(FLASH, raw["messages"])
        self.assertEqual(board("first", BEAM_OFF - 1)[1]["key"], "mCo4")
        snapshot = parse_snapshot(copy.deepcopy(raw), q25.RACES)
        self.assertEqual((snapshot.player.position.y, snapshot.player.position.x), (1, 18))
        # The traps of the row the board knew before the beam are gone on this board.
        before = parse_snapshot(copy.deepcopy(board("first", BEAM_OFF - 1)[0]), q25.RACES)
        self.assertTrue(before.grid_at(Position(1, 17)).trap)
        self.assertFalse(any(snapshot.grid_at(Position(1, x)).trap for x in range(8, 18)
                             if snapshot.grid_at(Position(1, x)) is not None))
        # The recorded aims before each step, and the searches of [1,10] from [1,11].
        self.assertEqual([board("first", s)[1]["key"] for s in range(880, 889, 2)], ["mCo4"] * 5)
        for part, sequences in (("first", (SEARCHED,)), ("second", range(SECOND_SEARCH, 18)),
                                ("second", range(ITEMS_ON_CELL, 70)), ("third", range(1, 40))):
            for sequence in sequences:
                raw, row = board(part, sequence)
                self.assertEqual((row["key"], row["reason"]), ("s", battle.SEARCH_REASON), (part, sequence))
                self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (1, 11))

    def test_the_beam_that_went_off_answers_the_whole_row(self):
        # After the flash the plan walks on: no second aim along the row it already cleared.
        for sequence in CORRIDOR_STEPS:
            raw, row = board("first", sequence)
            if row["reason"] != battle.WALK_REASON and not row["reason"].startswith("me-power:trap"):
                continue
            with self.subTest(sequence=sequence):
                key, reason = answer("first", sequence)
                self.assertEqual(reason, battle.WALK_REASON, (key, row))
                self.assertEqual(key, "4")

    def test_no_search_of_the_cleared_cell_in_any_process(self):
        self.assertEqual(answer("first", SEARCHED), ("4", battle.WALK_REASON))
        self.assertEqual(answer("second", SECOND_SEARCH), ("4", battle.WALK_REASON))
        for (part, sequence), (key, reason) in sorted(replay_answers().items()):
            raw = board(part, sequence)[0]
            if (raw["player"]["y"], raw["player"]["x"]) == (1, 11):
                with self.subTest(part=part, sequence=sequence):
                    self.assertNotEqual(reason, battle.SEARCH_REASON, key)

    def test_items_on_a_map_trap_cell_mean_no_trap_there(self):
        # Without the beam's line (the battle of a process that never saw the flash) and without
        # the board's unsafe flag, the items the fight left on [1,10] still answer it: a trap
        # terrain takes no item.
        with patch.object(battle, "_settle_beam", lambda ctx: None), \
                patch.object(battle, "_settled_on_board", lambda ctx, grid: False):
            answers = replay()
        self.assertEqual(answers["second", SECOND_SEARCH], ("s", battle.SEARCH_REASON))
        self.assertEqual(answers["second", ITEMS_ON_CELL], ("4", battle.WALK_REASON))
        self.assertEqual(answers["third", 1], ("4", battle.WALK_REASON))


# -- stop 1: the counted recharge rest on [2,24] -----------------------------------------------
#
# Teleported to [2,24] out of the Ipsissimus fight (decision 1060), the plan prepared the
# stragglers' phase: read the three lists ('bC','bA','bB') and rested 'R100\r' while an attack
# power was short.  Each rest ended 3-13 game turns later: the Dreadmaster (race 690, Lv44),
# sensed undead (the amulet's ESP), came through the walls from [11,24] to [8,25], and each of its
# moves disturbed the rest (monster-move.cpp; disturb_high / disturb_unknown).  The cycle repeated
# until the loop guard stopped the bot (decision 1099).  Owner 2026-11-09 「持ち場へ歩き静まれば休む」.
#
# DECLARED CONSTRUCTED: the boards after each recorded 'b' carry the list the executor would
# have read off the screen (``_magic_eater_power_list``): the town-arrival list of that kind with
# the Acid Bolts wand short (the recorded rests repeated because some attack power stayed short;
# the ring's boards hold no list).  Only boards from STOP1_FIRST on carry one.  The "quiet" board
# is the board after the first cut rest with the sensed movers removed (turn + 5, no message).
STOP1_FIRST = 1061      # the first board on [2,24]: 'bC'
STOP1_REST = 1064       # the first 'R100\r'
STOP1_CUT = 1065        # the board after it: 13 game turns later, the Dreadmaster sensed
SHORT_WAND = "アシッド・ボルト"
KIND_OF = {"bA": "staff", "bB": "wand", "bC": "rod"}


def listed(kind):
    turn, rows = CASE["lists"][kind]
    rows = [dict(row) for row in rows]
    if kind == "wand":
        for row in rows:
            if row["name"] == SHORT_WAND:
                row["current"] = 3
    return {"kind": kind, "rows": rows}


def stop1(through=STOP1_CUT, *, quiet=False):
    """(policy, {sequence: (key, reason)}) of the first process through ``through``; ``quiet``
    then decides the constructed quiet board after it."""
    answers = {}
    with TemporaryDirectory() as directory:
        boards = CASE["first"]["boards"]
        policy = new_policy(boards[0], lists=True, record=Path(directory) / "q25-battle.json")
        previous = None
        for raw, row in zip(boards, CASE["first"]["recorded"]):
            if row["sequence"] > through:
                break
            raw = copy.deepcopy(raw)
            if row["sequence"] >= STOP1_FIRST and previous in KIND_OF:
                raw["_magic_eater_power_list"] = listed(KIND_OF[previous])
            snapshot = parse_snapshot(raw, policy._monrace_knowledge)
            key = str(policy.choose_key(snapshot))
            answers[row["sequence"]] = (key, policy.last_reason)
            policy.confirm_key_posted(key)
            previous, last = key, raw
        if quiet:
            raw = copy.deepcopy(last)
            raw["turn"] += 5
            raw["messages"] = []
            raw.pop("_magic_eater_power_list", None)
            raw["detected_monsters"] = [m for m in raw["detected_monsters"] if m["race_id"] not in MOVERS]
            snapshot = parse_snapshot(raw, policy._monrace_knowledge)
            key = str(policy.choose_key(snapshot))
            answers["quiet"] = (key, policy.last_reason)
    return policy, answers


DREADMASTER, NIGHTMARE = 690, 622
MOVERS = (DREADMASTER, NIGHTMARE)


class Q25RechargeRestCutTest(unittest.TestCase):

    def test_the_recording(self):
        rows = {row["sequence"]: row for row in CASE["first"]["recorded"]}
        self.assertEqual([rows[s]["key"] for s in range(STOP1_FIRST, STOP1_FIRST + 4)],
                         ["bC", "bA", "bB", "R100\r"])
        self.assertEqual(rows[STOP1_REST]["reason"], battle.RECHARGE_REASON)
        # Every recorded rest was followed by the next read within 13 game turns.
        rests = [s for s, row in rows.items() if row["reason"] == battle.RECHARGE_REASON and s >= STOP1_FIRST]
        self.assertEqual(len(rests), 9)
        for sequence in rests:
            self.assertLessEqual(rows[sequence + 1]["turn"] - rows[sequence]["turn"], 13)
            self.assertEqual(rows[sequence + 1]["key"], "bC")
        raw = board("first", STOP1_CUT)[0]
        self.assertEqual(raw["visible_monsters"], [])
        sensed = {m["race_id"]: (m["y"], m["x"]) for m in raw["detected_monsters"]}
        self.assertIn(DREADMASTER, sensed)
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (2, 24))

    def test_the_first_rest_is_still_keyed(self):
        _, answers = stop1(STOP1_REST)
        self.assertEqual([answers[s][0] for s in range(STOP1_FIRST, STOP1_REST + 1)],
                         ["bC", "bA", "bB", "R100\r"])
        self.assertEqual(answers[STOP1_REST][1], battle.RECHARGE_REASON)

    def test_a_rest_the_sensed_mover_cut_walks_to_the_post(self):
        _, answers = stop1()
        key, reason = answers[STOP1_CUT]
        self.assertEqual(reason, battle.WALK_REASON, key)
        self.assertNotEqual(key[:1], "b")

    def test_the_recharge_rest_goes_on_once_no_mover_is_sensed(self):
        _, answers = stop1(quiet=True)
        self.assertEqual(answers[STOP1_CUT][1], battle.WALK_REASON)
        key, reason = answers["quiet"]
        self.assertIn(key, ("bA", "bB", "bC", "R100\r"), reason)


if __name__ == "__main__":
    unittest.main()
