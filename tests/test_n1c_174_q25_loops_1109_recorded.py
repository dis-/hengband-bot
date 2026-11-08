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
        # Without the beam's line (the battle of a process that never saw the flash), the items
        # the fight left on [1,10] still answer it: a trap terrain takes no item.
        with patch.object(battle, "_settle_beam", lambda ctx: None):
            answers = replay()
        self.assertEqual(answers["second", SECOND_SEARCH], ("s", battle.SEARCH_REASON))
        self.assertEqual(answers["second", ITEMS_ON_CELL], ("4", battle.WALK_REASON))
        self.assertEqual(answers["third", 1], ("4", battle.WALK_REASON))


if __name__ == "__main__":
    unittest.main()
