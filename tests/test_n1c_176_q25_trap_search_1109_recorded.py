"""Quest 25 on n1-c life-176 (life-174 resumed, 2026-11-09 04:18:17-04:18:34): the trap search, recorded.

The game was resumed from turn 4088202; the bot's Q25 battle record (written at a later turn by
life-174's last process) was not restored, so the battle started afresh.  The beam of 03:16 had
destroyed the traps of the north corridor's row 1, but nothing this process knew said so: walking
west on row 1 it stood on [1,16] and searched [1,15] (an always-trapped map cell) from decision 67
on, under the owner's phase-5 rule 「見つかるまで探す」 (2026-11-06), until the loop guard stopped
it, and the two restarts after did the same (04:18:25, 04:18:32).  Search finds only a trap that
is there (player-move.cpp search: each adjacent grid with skill_srh percent).

Owner 2026-11-09 (it replaces 「見つかるまで探す」): 「罠探知があるなら使用することで確定。そうでなければ
10回で打ち切る。」  Three paths, each through the public ``choose_key`` from the recorded boards:
 * the board's own record: [1,15] is known, shows no trap, and is no longer CAVE_UNSAFE on the
   board (grid_map.unsafe_rows; the beam of 03:16 cleared it, effect-feature.cpp KILL_TRAP): it
   holds no trap, so the walk goes on (the live boards, as recorded);
 * with a trap detection held (DECLARED CONSTRUCTED: the boards without unsafe_rows, as with the
   view_unsafe_grids option off, and the life's town-arrival magic-eater lists with the
   disarming rod charging and the disarming wands empty): the absorbed Detect Traps is used for
   the first unsettled cell; the recorded board after it stands in for the detection's result,
   exact for row 1 (its traps were gone), and row 1 is walked without a search;
 * without one (the boards without unsafe_rows, no lists, as live): ten searches, then on; the
   count is part of the battle record, so a restart after six searches searches four more.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_plan
from hengbot.model import _parse_items, parse_snapshot
from tests import test_q25_haunted_house as q25

VALUES = quest25_plan.values_of(q25.STRATEGIES[25])   # the plan's numbers (revised_plan_values)


with gzip.open(Path(__file__).with_name("fixtures") / "n1c-176-q25-trap-search-1109.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

STAND = (1, 16)
FIRST_SEARCH = 67          # the first process's first search of [1,15] from [1,16]
LAST_SEARCH = 102
RESTART_AFTER = 72         # six searches, then the restart
DETECT_FIRST = 3           # the first unsettled cell the detection path meets: [1,8] from [1,9]
DISARMING = {"rod": ("トラップ解除",), "wand": ("トラップ解除", "トラップ/ドア破壊")}


def lists_without_disarming():
    lists = {}
    for kind, (turn, rows) in CASE["lists"].items():
        rows = [dict(row) for row in rows]
        for row in rows:
            if row["name"] in DISARMING.get(kind, ()):
                if kind == "rod":
                    row["charging"] = row["max"]
                else:
                    row["current"] = 0
        lists[kind] = (turn, tuple(rows))
    return lists


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
        policy._me_device_lists = lists_without_disarming()
    policy._q25_battle_record_path = record
    return policy


def replay(parts, *, unsafe=True, lists=False, through=None):
    """{(part, sequence): (key, reason)}: each process by its own policy, the battle carried by the
    real record; ``through`` = {part: last sequence decided}."""
    answers = {}
    through = through or {}
    with TemporaryDirectory() as directory:
        record = Path(directory) / "q25-battle.json"
        for part in parts:
            boards = CASE[part]["boards"]
            policy = new_policy(boards[0], lists=lists and part == "first", record=record)
            for raw, row in zip(boards, CASE[part]["recorded"]):
                if row["sequence"] > through.get(part, 10 ** 6):
                    break
                raw = copy.deepcopy(raw)
                if not unsafe:
                    raw["grid_map"].pop("unsafe_rows", None)
                snapshot = parse_snapshot(raw, policy._monrace_knowledge)
                key = str(policy.choose_key(snapshot))
                answers[part, row["sequence"]] = (key, policy.last_reason)
                policy.confirm_key_posted(key)
    return answers


def recorded(part, sequence):
    for raw, row in zip(CASE[part]["boards"], CASE[part]["recorded"]):
        if row["sequence"] == sequence:
            return raw, row
    raise KeyError((part, sequence))


class Q25TrapSearchSettledTest(unittest.TestCase):

    def test_the_recording(self):
        for sequence in range(FIRST_SEARCH, LAST_SEARCH + 1):
            raw, row = recorded("first", sequence)
            self.assertEqual((row["key"], row["reason"]), ("s", battle.SEARCH_REASON))
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), STAND)
        for part in ("second", "third"):
            self.assertEqual({row["key"] for row in CASE[part]["recorded"][1:]}, {"s"})
        raw = recorded("first", FIRST_SEARCH)[0]
        snapshot = parse_snapshot(copy.deepcopy(raw), q25.RACES)
        grid = snapshot.grid_at(snapshot.player.position.__class__(1, 15))
        self.assertTrue(grid.known)
        self.assertFalse(grid.trap)
        self.assertEqual(grid.object_count, 0)
        self.assertFalse(snapshot.unsafe_rows[1][15])

    def test_the_board_says_the_cell_is_safe_so_the_walk_goes_on(self):
        answers = replay(("first", "second", "third"))
        self.assertEqual(answers["first", FIRST_SEARCH], ("4", battle.WALK_REASON))
        searches = [where for where, (_, reason) in answers.items() if reason == battle.SEARCH_REASON]
        self.assertEqual(searches, [])

    def test_with_a_detection_held_it_is_used_and_no_search_follows(self):
        answers = replay(("first",), unsafe=False, lists=True)
        key, reason = answers["first", DETECT_FIRST]
        self.assertEqual(reason, "me-power:trap-cell-unsettled:detect-traps", key)
        self.assertTrue(key.startswith("mA"), key)
        self.assertEqual(answers["first", DETECT_FIRST + 1], ("4", battle.WALK_REASON))
        self.assertEqual(answers["first", FIRST_SEARCH], ("4", battle.WALK_REASON))
        self.assertEqual([where for where, (_, reason) in answers.items()
                          if reason == battle.SEARCH_REASON], [])

    def test_without_one_ten_searches_then_on(self):
        answers = replay(("first",), unsafe=False)
        for sequence in range(FIRST_SEARCH, FIRST_SEARCH + VALUES.trap_searches):
            self.assertEqual(answers["first", sequence], ("s", battle.SEARCH_REASON), sequence)
        self.assertEqual(answers["first", FIRST_SEARCH + VALUES.trap_searches], ("4", battle.WALK_REASON))

    def test_the_count_survives_a_restart(self):
        answers = replay(("first", "second"), unsafe=False, through={"first": RESTART_AFTER})
        done = RESTART_AFTER - FIRST_SEARCH + 1
        self.assertEqual([answers["first", s][0] for s in range(FIRST_SEARCH, RESTART_AFTER + 1)], ["s"] * done)
        # The restarted process searches from its first board (the live one read the skill
        # list first, '~f', which this policy holds already): the four left, then on.
        left = VALUES.trap_searches - done
        self.assertEqual([answers["second", s] for s in range(0, left)],
                         [("s", battle.SEARCH_REASON)] * left)
        self.assertEqual(answers["second", left], ("4", battle.WALK_REASON))


if __name__ == "__main__":
    unittest.main()
