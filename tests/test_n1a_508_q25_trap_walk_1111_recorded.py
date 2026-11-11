"""Quest 25 on n1-a life-508 (2026-11-11 04:39:13-04:39:29): the trapped row walked, recorded.

After the tyrannosaur fell, the phase walked west along row 1 from [1,14].  Each cell of the row
is a trap cell of the map, so before stepping on it the plan's trap rule (quest25_battle._trap_key,
owner 2026-11-09 「罠探知があるなら使用することで確定。そうでなければ10回で打ち切る。」) searched, disarmed
what it found (「ガス・トラップを解除した。」 at decision 4123) and passed the cell after at most
``trap_searches`` (10) searches.  It kept moving -- [1,14], [1,13], [1,12], [1,11], [1,10], [1,9]
-- but 40 decisions on six cells is the driver's loop window (cli.LOOP_WINDOW), and the guard
stopped the bot at decision 4130 on [1,9], its seventh search there.

The search is bounded per cell like the trap warning's (``warning:trap-search``, a corridor of traps
walked one search at a time is no confined loop), so it is exempt from the cell loop guard
(cli.STATIONARY_EXEMPT_REASONS).  The disarm stays counted: nothing bounds its retries.

Recorded, through the public ``choose_key`` from the frozen boards (fixture from
tests/extract_n1a_508_q25_trap_walk_1111_fixture.py): the policy decides every recorded key and
reason again (the walk itself is unchanged, and was the same before the 2026-11-11 step 7 merge),
and the driver's guard, fed those decisions as cli.main feeds them, no longer stops the walk.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import collections
import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import cli, quest25_battle as battle, quest25_plan
from hengbot.model import _parse_items, parse_snapshot
from tests.support import q25_house as q25

VALUES = quest25_plan.values_of(q25.STRATEGIES[25])   # the plan's numbers (revised_plan_values)

with gzip.open(Path(__file__).with_name("fixtures") / "n1a-508-q25-trap-walk-1111.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

FIRST_SEARCH = 4092        # the first search of row 1, from [1,14]
STOPPED_AT = 4130          # the decision the loop guard stopped (its seventh search on [1,9])
ROW = [(1, 14), (1, 13), (1, 12), (1, 11), (1, 10), (1, 9)]

# Decided differently from the recording since owner 2026-11-11 (「ブレスが敵の今の HP で弱くなる」):
# at 4083 the 幽体ティラノサウルス (race 705, BR_POIS) beside the player is wounded (health band
# upper 59%: HP 1770 of 3000), so its breath is min(1770 / 3, 800) = 590, not 800, and the fight
# after the Potion of Resistance is winnable: the drink (resist_potion.drink_key, owner 2026-11-05
# 「危ない敵と戦う時に飲む」, 2026-11-07 Q25 「幽体ティラノサウルスとの単独戦闘から逃げない」) is
# taken where the recording, reading the breath at the race's full HP, attacked.  Every other
# recorded decision is decided again as recorded.
CHANGED = {4083: ("qf", "resist-potion:quaff")}


def replay():
    """[(sequence, position, key, reason)] for every recorded board, by one policy."""
    boards, recorded = CASE["boards"], CASE["recorded"]
    answers = []
    with TemporaryDirectory() as directory:
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies=q25.STRATEGIES)
        first = copy.deepcopy(boards[0])
        policy.prime(parse_snapshot(first, policy._monrace_knowledge))
        policy.consume_skill_knowledge(dict(
            copy.deepcopy(CASE["skill"]), turn=first["turn"],
            player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
        policy.consume_home_knowledge(tuple(_parse_items(CASE["home"]["knowledge"]["items"], protocol=3)))
        policy._q25_battle_record_path = Path(directory) / "q25-battle.json"
        for raw, row in zip(boards, recorded):
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = str(policy.choose_key(snapshot))
            answers.append((row["sequence"], snapshot, key, policy.last_reason))
            policy.confirm_key_posted(key)
    return answers


def guard_stop(answers):
    """The decision the driver's cell loop guard stops at, fed as cli.main feeds it; else None."""
    recent, last_position, last_player = [], None, None
    for sequence, snapshot, _, reason in answers:
        previous_position, last_position = last_position, snapshot.player.position
        previous_player, last_player = last_player, snapshot.player
        if not cli._cell_loop_guard_applies(snapshot, reason, previous_position, previous_player):
            recent.clear()
            continue
        position = snapshot.player.position
        recent.append((snapshot.floor_key, position.y, position.x))
        if cli._is_looping(recent):
            return sequence
    return None


class N1a508TrapWalkRecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.answers = replay()

    def test_the_recording(self):
        rows = [row for row in CASE["recorded"] if row["sequence"] >= FIRST_SEARCH]
        cells = [(board["player"]["y"], board["player"]["x"])
                 for board, row in zip(CASE["boards"], CASE["recorded"]) if row["sequence"] >= FIRST_SEARCH]
        self.assertEqual(rows[-1]["sequence"], STOPPED_AT)
        self.assertEqual(list(dict.fromkeys(cells)), ROW)      # always on, westward
        self.assertEqual({row["reason"] for row in rows},
                         {battle.SEARCH_REASON, battle.DISARM_REASON, battle.WALK_REASON})
        searches = collections.Counter(cell for cell, row in zip(cells, rows)
                                       if row["reason"] == battle.SEARCH_REASON)
        self.assertLessEqual(max(searches.values()), VALUES.trap_searches, searches)
        self.assertEqual(searches[(1, 9)], 7)

    def test_the_policy_decides_as_recorded(self):
        decided = [(sequence, key, reason) for sequence, _, key, reason in self.answers]
        recorded = [(row["sequence"], *CHANGED.get(row["sequence"], (row["key"], row["reason"])))
                    for row in CASE["recorded"]]
        self.assertEqual(decided, recorded)
        self.assertEqual(next((row["key"], row["reason"]) for row in CASE["recorded"]
                              if row["sequence"] == 4083), ("4", "quest-strategy:melee"))

    def test_the_wounded_tyrannosaur_breathes_from_its_band(self):
        snapshot = next(snapshot for sequence, snapshot, _, _ in self.answers if sequence == 4083)
        tyrannosaur = next(m for m in snapshot.visible_monsters if m.race_id == 705)
        self.assertEqual((tyrannosaur.hp, tyrannosaur.max_hp), (1770, 3000))

    def test_the_trapped_row_is_no_cell_loop(self):
        self.assertIn(battle.SEARCH_REASON, cli.STATIONARY_EXEMPT_REASONS)
        self.assertIsNone(guard_stop(self.answers))

    def test_control_counted_the_searches_stop_it_where_it_stopped(self):
        exempt = cli.STATIONARY_EXEMPT_REASONS - {battle.SEARCH_REASON}
        with patch.object(cli, "STATIONARY_EXEMPT_REASONS", exempt):
            self.assertEqual(guard_stop(self.answers), STOPPED_AT)

    def test_control_the_disarm_still_counts(self):
        self.assertNotIn(battle.DISARM_REASON, cli.STATIONARY_EXEMPT_REASONS)


if __name__ == "__main__":
    unittest.main()
