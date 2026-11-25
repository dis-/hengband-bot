"""n1-b life-418's walks back to a choke over the siren's reach on Q18 (2026-11-25, floor (0,35,18)).

Owner 2026-11-25, to 「Q18 で隘路の待ちが尽きて別の隘路へ戻る時、叫ぶ敵の届くマスを通らない隘路を先に
選びますか？」: 「叫びの届かない隘路を先に」.  The walk to a choke (quest_find_exit ``_to_choke``) goes to
one that no cell of a caster heard shrieking reaches lies on; with none, as before.

What happened: the shriek heard on (2,6) (3417300) is the siren's on (6,14), the one plan caster
reaching that cell.  The walks back from (1,19) to (1,15), (1,12) and (1,5) went over (2,18) (1,17)
(1,16) and (2,6), all in its reach, and were shrieked at there (3419105, 3419447, 3419507, 3419865).

1. Attribution (``_attribute_shriek``): the shriek lines name no caster («何かが»), the cell they
   are heard on does; after the floor's boards the shrieking casters are the siren (6,14) alone.
2. As recorded, no choke was reachable off its reach: the chokes (2,26) and (1,24) lie past the vein
   (5,25), not dug, and (1,19) was the one left (spent by its enemy bound).  The walks back stay
   as recorded (owner: with none, the order as it was).
3. The replayed (1,9) (3419495): the replay held (1,12) one board longer than the recorded floor, so
   it is still a choke to go to; the change walks there over (1,10) (2,11), where no caster was
   heard, and not to (1,5) over the siren's (2,6), where the recorded walk was shrieked at.
4. DECLARED CONSTRUCTED: the vein (5,25) dug before (2,20) (3419092): the walk goes to (2,26), off
   the siren's reach, rather than to (1,15) over it.

Recorded: tests/fixtures/n1b-418-q18-floor-1125.jsonl.gz
(tests/extract_n1b_418_q18_choke_shriek_1125_fixture.py) and the absorbed lists of
tests/fixtures/n1b-418-me-lists-1125.json.  A fresh policy decides the recorded boards from the
floor's entry (3416674) through the public ``choose_key``; ``before(turn, navigator)`` edits the
navigator just before a board's decision where a test says DECLARED CONSTRUCTED.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import quest_find_exit
from hengbot.me_device_attacks import observe_lists
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.quest_strategies import load_quest_strategies
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "n1b-418-q18-floor-1125.jsonl.gz", "rt", encoding="utf-8") as _stream:
    BOARDS = {raw["turn"]: raw for raw in map(json.loads, _stream)}
LISTS = json.loads((FIXTURES / "n1b-418-me-lists-1125.json").read_text(encoding="utf-8"))["lists"]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
PLAN = quest_find_exit._plan_of(load_quest_strategies(Path(__file__).parents[1] / "strategy" / "quests")[18])

ENTRY = min(BOARDS)              # (1,2): the floor's first board
FIRST_SHRIEK = 3417300           # (2,6): the siren's shriek
SIREN = (6, 14)
SIREN_CELLS = {Position(2, 18), Position(1, 17), Position(1, 16), Position(2, 6)}
OFF_1_19 = 3419092               # (2,20): recorded '7' exit-to-choke toward (1,15)
BACK = {3419092: "7", 3419096: "1", 3419453: "1", 3419857: "7"}  # the recorded walks back
REPLAYED_1_9 = 3419495           # (1,9): recorded '4' exit-to-choke toward (1,5) over (2,6)
VEIN = (5, 25)
TO_CHOKE = quest_find_exit.TO_CHOKE_REASON
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1),
         "8": (-1, 0), "9": (-1, 1)}


def _new_policy(directory):
    policy = _policy(Path(directory), MONRACE)
    first = parse_snapshot(copy.deepcopy(BOARDS[ENTRY]), MONRACE)
    policy.prime(first)
    policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
    for kind in ("staff", "wand", "rod"):
        listed = dict(copy.deepcopy(BOARDS[ENTRY]), turn=ENTRY - 1,
                      _magic_eater_power_list={"kind": kind, "rows": LISTS[kind]})
        observe_lists(policy, parse_snapshot(listed, MONRACE))
    return policy


def drive(last, *, before=None):
    """{turn: (cell, key, reason, choke goal)} of the recorded boards from ENTRY to ``last``, and
    the floor's navigator."""
    with TemporaryDirectory() as directory:
        policy = _new_policy(directory)
        decided, previous = {}, None
        for turn in sorted(BOARDS):
            if turn > last:
                break
            raw = copy.deepcopy(BOARDS[turn])
            if previous is not None:
                raw["_completed_operation_owner"] = previous
            navigator = policy._quest_navigators.get(18)
            if before is not None and navigator is not None:
                before(turn, navigator)
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, MONRACE)))
            if key:
                policy.confirm_key_posted(key)
            previous = policy.last_reason if key else None
            navigator = policy._quest_navigators[18]
            goal = navigator.exit_choke_goal
            decided[turn] = ((raw["player"]["y"], raw["player"]["x"]), key, policy.last_reason,
                             None if goal is None else (goal.y, goal.x))
        return decided, policy._quest_navigators[18]


def _walk(navigator, start, goal) -> list:
    return quest_find_exit._least_exposed(navigator, PLAN, Position(*start), {Position(*goal)}, as_it_is=True)


def _shrieks(turn) -> bool:
    return any(mark in message for message in BOARDS[turn]["messages"]
               for mark in quest_find_exit.SHRIEK_MARKS)


class RecordedFloorTest(unittest.TestCase):

    def test_the_shrieks_heard_and_where(self):
        heard = {turn: (BOARDS[turn]["player"]["y"], BOARDS[turn]["player"]["x"])
                 for turn in sorted(BOARDS) if _shrieks(turn)}
        self.assertEqual(heard[FIRST_SHRIEK], (2, 6))
        self.assertLessEqual({(1, 17), (1, 16), (2, 18), (2, 6)}, set(heard.values()), heard)


class ShriekAttributionTest(unittest.TestCase):

    def test_the_siren_6_14_is_the_one_heard(self):
        decided, navigator = drive(FIRST_SHRIEK - 1)
        self.assertEqual(navigator.exit_shriekers, frozenset())
        decided, navigator = drive(FIRST_SHRIEK)
        self.assertEqual(navigator.exit_shriekers, frozenset({SIREN}))
        self.assertLessEqual(SIREN_CELLS, quest_find_exit._shriek_reach(navigator, PLAN))

    def test_the_whole_floor_hears_the_siren_only(self):
        _, navigator = drive(max(BOARDS))
        self.assertEqual(navigator.exit_shriekers, frozenset({SIREN}))


class WalksBackTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.decided, cls.navigator = drive(max(BACK))

    def test_no_choke_off_the_siren_so_the_walks_back_stay(self):
        """The owner's fallback: as recorded, every choke to go to lies over the siren's cells."""
        for turn, key in BACK.items():
            cell, decided_key, reason, goal = self.decided[turn]
            self.assertEqual((decided_key, reason), (key, TO_CHOKE), (turn, self.decided[turn]))
            self.assertIn(goal, {(1, 15), (1, 12), (1, 5)}, (turn, self.decided[turn]))
            self.assertTrue(SIREN_CELLS & set(_walk(self.navigator, cell, goal)[1:]), turn)

    def test_the_chokes_east_are_past_the_vein(self):
        self.assertNotIn(VEIN, self.navigator.exit_dug)
        for goal in ((2, 26), (1, 24)):
            self.assertEqual(_walk(self.navigator, (2, 20), goal), [])


def _no_shrieker(at):
    """DECLARED CONSTRUCTED (the control, the order before the change): no shriek attributed
    when the board of ``at`` is decided."""
    def before(turn, navigator):
        if turn == at:
            navigator.exit_shriekers = frozenset()
    return before


def _vein_dug(turn, navigator):
    """DECLARED CONSTRUCTED: the vein (5,25) dug before (2,20)."""
    if turn == OFF_1_19:
        navigator.exit_dug = navigator.exit_dug | {VEIN}


class ReplayedOneNineTest(unittest.TestCase):

    def test_goes_to_1_12_off_the_siren(self):
        decided, navigator = drive(REPLAYED_1_9)
        cell, key, reason, goal = decided[REPLAYED_1_9]
        self.assertEqual((cell, key, reason, goal), ((1, 9), "6", TO_CHOKE, (1, 12)))
        self.assertFalse(SIREN_CELLS & set(_walk(navigator, cell, goal)[1:]))

    def test_control_without_the_shrieker_goes_over_2_6(self):
        decided, navigator = drive(REPLAYED_1_9, before=_no_shrieker(REPLAYED_1_9))
        cell, key, reason, goal = decided[REPLAYED_1_9]
        self.assertEqual((cell, key, reason, goal), ((1, 9), "4", TO_CHOKE, (1, 5)))
        self.assertIn(Position(2, 6), _walk(navigator, cell, goal))
        self.assertTrue(_shrieks(3419507))  # where the recorded walk was shrieked at


class VeinDugTest(unittest.TestCase):

    def test_goes_east_off_the_siren(self):
        decided, navigator = drive(OFF_1_19, before=_vein_dug)
        cell, key, reason, goal = decided[OFF_1_19]
        self.assertEqual((cell, goal), ((2, 20), (2, 26)), decided[OFF_1_19])
        self.assertFalse(SIREN_CELLS & set(_walk(navigator, cell, goal)[1:]))
        if reason == TO_CHOKE:
            step = STEPS[key]
            self.assertNotIn(Position(cell[0] + step[0], cell[1] + step[1]), SIREN_CELLS)

    def test_control_without_the_shrieker_goes_west_over_it(self):
        def both(turn, navigator):
            _vein_dug(turn, navigator)
            _no_shrieker(OFF_1_19)(turn, navigator)
        decided, navigator = drive(OFF_1_19, before=both)
        cell, key, reason, goal = decided[OFF_1_19]
        self.assertEqual((cell, key, reason, goal), ((2, 20), "7", TO_CHOKE, (1, 15)))
        self.assertTrue(SIREN_CELLS & set(_walk(navigator, cell, goal)[1:]))


if __name__ == "__main__":
    unittest.main()
