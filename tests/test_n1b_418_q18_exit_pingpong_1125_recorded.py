"""n1-b life-418's Q18 livelock stop (2026-11-25 06:22, Magic-Eater Lv38 with telepathy, floor (0,35,18)).

What happened (the decision tail, turns 3420023-3420056): the quiet wait on the choke (1,15) spent,
the walk went on through the shouted (1,16) (1,17) (2,18), took the siren's shriek on (1,16)
(「何かがかん高い金切り声をあげた。」, 「付近で何かが突如興奮したような感じを受けた！」), walked off the choke
(1,19) at once, and from the open (3,20) saw the giant squid 482 (index 8) on (9,24), distance 6:
'8' exit-to-choke onto (2,20).  There the squid was out of sight, shown by ESP only, and read by
the far rule (owner 2026-11-06, ``approaching``: it had moved away), so '2' exit-walk stepped back
onto (3,20), and so on until the ping-pong guard escalated to the livelock stop.  Two verdicts of
one plan on one monster: in view, its 50-action wait (owner 2026-11-08) said it comes; sensed, the
far rule said it does not.

1. The in-view verdict holds while the monster is sensed out of sight (quest_find_exit
   ``_in_view_waits``, as it already did for one not known at all): the walk to the choke goes on.
2. The shriek hold (owner 2026-11-22, 「叫びを受けた理由を調査すること。受けないように立ち回る指示
   なので。」; quest_find_exit ``_shriek_hold``) was skipped on (1,19): another giant squid sensed in
   the lake with a breath's line to the player (``firing``, 9a474abadd, after the shriek hold)
   made the board engaged, and that branch never asked the choke's wait.  It does now.

Recorded: tests/fixtures/n1b-418-q18-1125.jsonl.gz (tests/extract_n1b_418_q18_pingpong_1125_fixture.py),
the absorbed power lists of the same capture's town-arrival checkpoint
(tests/fixtures/n1b-418-me-lists-1125.json).  A fresh policy decides the recorded boards from the
walk on from (1,15) (3420023) through the public ``choose_key``.  The closed loop
(``walk``) moves the player as each step key does and answers the next recorded board of that cell
(DECLARED CONSTRUCTED: a recorded board is used again, its turn moved on 10 game turns a board).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import gzip
import io
import json
import unittest
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import quest_find_exit
from hengbot.me_device_attacks import observe_lists
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.quest_strategies import load_quest_strategies
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "n1b-418-q18-1125.jsonl.gz", "rt", encoding="utf-8") as _stream:
    BOARDS = {raw["turn"]: raw for raw in map(json.loads, _stream)}
LISTS = json.loads((FIXTURES / "n1b-418-me-lists-1125.json").read_text(encoding="utf-8"))["lists"]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
_PROFILE = load_quest_strategies(Path(__file__).parents[1] / "strategy" / "quests")[18]

START = 3420023                 # (1,15): recorded exit-walk '6', the choke's quiet wait spent
SHRIEK = 3420028                # (1,16): the siren's shriek
CHOKE = 3420039                 # (1,19): recorded exit-walk '3'
SEEN = (3420046, 3420052)       # (3,20): the squid in view, recorded '8' exit-to-choke
SENSED = (3420044, 3420050, 3420056)  # (2,20): the squid by ESP only, recorded '2' exit-walk
SQUID, SQUID_INDEX = 482, 8
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1),
         "8": (-1, 0), "9": (-1, 1)}
WALK, TO_CHOKE, HOLD = (quest_find_exit.WALK_REASON, quest_find_exit.TO_CHOKE_REASON,
                        quest_find_exit.HOLD_REASON)


def _cell(raw):
    return raw["player"]["y"], raw["player"]["x"]


def _new_policy(directory):
    policy = _policy(Path(directory), MONRACE)
    first = parse_snapshot(copy.deepcopy(BOARDS[START]), MONRACE)
    policy.prime(first)
    policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
    for kind in ("staff", "wand", "rod"):
        listed = dict(copy.deepcopy(BOARDS[START]), turn=START - 1,
                      _magic_eater_power_list={"kind": kind, "rows": LISTS[kind]})
        observe_lists(policy, parse_snapshot(listed, MONRACE))
    return policy


def _decide(policy, raw, previous):
    if previous is not None:
        raw["_completed_operation_owner"] = previous
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, MONRACE)))
    if key:
        policy.confirm_key_posted(key)
    return key, (policy.last_reason if key else None)


def drive(last, *, edit=None):
    """[(turn, cell, key, reason)] of the recorded boards from START to ``last``, in order."""
    with TemporaryDirectory() as directory:
        policy = _new_policy(directory)
        decided, previous = [], None
        for turn in sorted(BOARDS):
            if turn < START:
                continue
            if turn > last:
                break
            raw = copy.deepcopy(BOARDS[turn])
            if edit is not None:
                edit(turn, raw)
            key, previous = _decide(policy, raw, previous)
            decided.append((turn, _cell(raw), key, policy.last_reason))
        return policy, decided


def walk(decisions, *, edit=None, setup=None):
    """The closed loop from START: [(cell, key, reason)] and the policy.  ``setup(navigator)``
    runs after the first decision (DECLARED CONSTRUCTED where a test says so)."""
    by_cell = defaultdict(list)
    for turn in sorted(BOARDS):
        if turn >= START:
            by_cell[_cell(BOARDS[turn])].append(turn)
    used = defaultdict(int)
    with TemporaryDirectory() as directory:
        policy = _new_policy(directory)
        cell, turn, previous, rows = _cell(BOARDS[START]), START, None, []
        for _ in range(decisions):
            turns = by_cell[cell]
            if not turns:
                break  # no recorded board of this cell
            recorded = turns[min(used[cell], len(turns) - 1)]
            used[cell] += 1
            raw = copy.deepcopy(BOARDS[recorded])
            if edit is not None:
                edit(recorded, raw)
            raw["turn"] = turn
            key, previous = _decide(policy, raw, previous)
            rows.append((cell, key, policy.last_reason))
            if setup is not None and len(rows) == 1:
                setup(policy._quest_navigators[18])
            step = STEPS.get(str(key))
            if step is not None:
                cell = (cell[0] + step[0], cell[1] + step[1])
            turn += 10
        return policy, rows


def _alternations(cells) -> list:
    """Where the walk goes A, B, A, B: one there and back is a hand-over, twice a ping-pong."""
    return [index for index in range(3, len(cells))
            if cells[index] == cells[index - 2] != cells[index - 1] == cells[index - 3]]


def _spent_1_19(navigator):
    """DECLARED CONSTRUCTED: (1,19) spent by its quiet wait before this walk, as the recorded
    floor's navigator had it (the whole floor's replay from the town-arrival checkpoint, turn
    3420023: spent (1,3) (1,5) (1,9) (1,15) (1,19))."""
    choke = Position(1, 19)
    navigator.exit_spent_chokes = navigator.exit_spent_chokes | {choke}
    navigator.exit_quiet_spent = {**navigator.exit_quiet_spent, choke: 0}


def _no_shrieks(turn, raw):
    """DECLARED CONSTRUCTED: the corridor's boards without the shriek lines."""
    raw["messages"] = [message for message in raw["messages"]
                       if not any(mark in message for mark in quest_find_exit.SHRIEK_MARKS)]


class RecordedBoardsTest(unittest.TestCase):

    def test_the_squid_is_seen_from_3_20_and_sensed_from_2_20(self):
        for turn in SEEN:
            seen = {row["index"]: (row["race_id"], row["y"], row["x"]) for row in BOARDS[turn]["visible_monsters"]}
            self.assertEqual(seen[SQUID_INDEX], (SQUID, 9, 24))
            self.assertEqual(_cell(BOARDS[turn]), (3, 20))
        for turn in SENSED:
            self.assertEqual(BOARDS[turn]["visible_monsters"], [])
            sensed = {row["index"]: (row["race_id"], row["y"], row["x"]) for row in BOARDS[turn]["detected_monsters"]}
            self.assertEqual(sensed[SQUID_INDEX], (SQUID, 9, 24))
            self.assertEqual(_cell(BOARDS[turn]), (2, 20))
        self.assertTrue(any(mark in message for message in BOARDS[SHRIEK]["messages"]
                            for mark in quest_find_exit.SHRIEK_MARKS))


class SensedSquidKeepsTheWalkToTheChokeTest(unittest.TestCase):

    def test_the_corridor_is_walked_as_recorded(self):
        _, decided = drive(3420036)
        self.assertEqual([(cell, key, reason) for _, cell, key, reason in decided],
                         [((1, 15), "6", WALK), ((1, 16), "6", WALK), ((1, 17), "3", WALK),
                          ((2, 18), "9", WALK)])

    def test_the_shriek_holds_the_choke_1_19(self):
        """Recorded exit-walk '3' off (1,19); the shriek on (1,16) holds it (owner 2026-11-22)."""
        policy, decided = drive(CHOKE)
        self.assertEqual(decided[-1][1:], ((1, 19), "5", HOLD), decided)
        navigator = policy._quest_navigators[18]
        self.assertEqual((navigator.exit_fought_at.y, navigator.exit_fought_at.x), (1, 19))
        self.assertFalse(navigator.exit_shrieked)

    def test_control_no_shriek_walks_on_from_1_19(self):
        """DECLARED CONSTRUCTED: without the shriek lines nothing holds (1,19): the walk goes on."""
        _, decided = drive(CHOKE, edit=_no_shrieks)
        self.assertEqual(decided[-1][1:], ((1, 19), "3", WALK), decided)

    def test_one_verdict_on_the_squid_sensed_from_2_20(self):
        """The recorded alternation: (1,19) spent by its quiet wait and no shriek on the corridor
        (DECLARED CONSTRUCTED, so the walk reaches the open as recorded).  The squid seen from
        (3,20) sends the walk back to the choke (1,19) (``_readmitted``, recorded '8'); on (2,20),
        sensed only, the walk goes on to it (recorded '2' exit-walk back onto (3,20))."""
        _, rows = walk(12, edit=_no_shrieks, setup=_spent_1_19)
        cells = [cell for cell, _, _ in rows]
        self.assertEqual(cells[:7], [(1, 15), (1, 16), (1, 17), (2, 18), (1, 19), (2, 20), (3, 20)], rows)
        self.assertEqual(rows[6][1:], ("8", TO_CHOKE), rows)
        self.assertEqual(rows[7], ((2, 20), "7", TO_CHOKE), rows)
        self.assertEqual(rows[8], ((1, 19), "5", HOLD), rows)
        self.assertEqual(_alternations(cells), [], rows)

    def test_the_recorded_walk_holds_1_19_and_never_alternates(self):
        """As recorded (the shriek on (1,16)): (1,19) holds its 30 quiet turns, the walk goes on,
        the squid seen from (3,20) sends it back and the sensed squid keeps it going there."""
        _, rows = walk(40)
        cells = [cell for cell, _, _ in rows]
        plan = quest_find_exit._plan_of(_PROFILE)
        holds = int(plan["choke_hold_turns"])
        self.assertEqual(rows[4:4 + holds], [((1, 19), "5", HOLD)] * holds, rows)
        seen = cells.index((3, 20))
        self.assertEqual(rows[seen][1:], ("8", TO_CHOKE), rows)
        self.assertEqual(rows[seen + 1], ((2, 20), "7", TO_CHOKE), rows)
        self.assertEqual(rows[seen + 2], ((1, 19), "5", HOLD), rows)
        self.assertEqual(_alternations(cells), [], rows)

if __name__ == "__main__":
    unittest.main()
