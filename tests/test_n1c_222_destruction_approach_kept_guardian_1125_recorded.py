"""n1-c life-222's loop-detected stop (2026-11-25 13:21, Magic-Eater Lv45, Mountain 50F).

What happened (the decision tail, turns 6851315-6851527): after the wall searches the 全感知 at
(40,180) showed Thorondor's flock to the north -- 大鷲王『ソロンドール』 (race 468, index 5, the
floor's guardian, kept: not T1 alone) on (8,172) with his eagles (race 1312, 335, 998) -- and a
race 361 (index 96) on (58,168) to the south.  The sensed T1 approach walked north up the melted
corridor; at (26,176) the guardian was shown by telepathy (18 off), at (27,177) it was not (19
off).  From (26,176) every use cell of the nearer eagle (index 15, (9,173)) had the guardian
within the worst radius 17, so the walk's subject passed to the next one with a way, race 361 in
the south, and stepped '3'; from (27,177) the guardian was not on the board, (21,175) was a use
cell for the eagle again, and the walk stepped '7' back.  25 alternations, with the livelock's
Stone to Mud and the oscillation breaker in between, until the loop detector.

Now the guardian to be kept is judged at its last shown cell while out of detection
(destruction_use ``_spared_positions``, monster_memory.KEPT_GUARDIAN), as the remembered approach
judges its targets: both cells read the same use cells, and the walk goes on south.

Owner 2026-11-25 (maintainability review contradictions 1125, answer (b)-4): the memory restrains
only the walk toward a use.  The use itself (destruction_use ``_spared_in_circle``, the emergency
and escape uses with it) reads the board only, owner 2026-11-17 「*破壊* の決まりに『起きている敵だけ』
『感知範囲の中だけ』は無い」: on a board without the guardian, a circle that would reach its last
shown cell is not refused for it, while the walk still keeps that cell out of its use cells.

Recorded: tests/fixtures/n1c-222-destruction-approach-1125.jsonl.gz (the floor from its arrival,
tests/extract_n1c_222_destruction_approach_1125_fixture.py), the absorbed power lists of the same
capture's town-arrival checkpoint (tests/fixtures/n1c-222-me-lists-1125.json).  A fresh policy
decides every recorded board of the floor from its arrival (6850301) through the public
``choose_key``, so the map, the *Destruction* circle and the remembered approach are the replay's
own.  The closed loop (``walk``) then moves the player from (26,176) as each step key does and
answers the latest recorded board of that cell (DECLARED CONSTRUCTED: a recorded board is used
again, its turn moved on 4 game turns a board).
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

from hengbot import destruction_use, threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.model import Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "n1c-222-destruction-approach-1125.jsonl.gz", "rt", encoding="utf-8") as _stream:
    BOARDS = {raw["turn"]: raw for raw in map(json.loads, _stream)}
LISTS = json.loads((FIXTURES / "n1c-222-me-lists-1125.json").read_text(encoding="utf-8"))["lists"]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

ARRIVAL = min(BOARDS)
# The guardian shown (26,176), recorded '3'; not shown (27,177), recorded '7'.
SHOWN = (6851393, 6851403, 6851411, 6851428, 6851441, 6851455, 6851478, 6851500, 6851521)
LOST = (6851399, 6851407, 6851415, 6851434, 6851450, 6851460, 6851474, 6851496, 6851516)
LAST = max(BOARDS)
APPROACH = threat_tiers.APPROACH_REASON
# The guardian's last shown cell, and a cell north of the player within its worst radius.
GUARDIAN = Position(8, 172)
NORTH = Position(21, 175)
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1),
         "8": (-1, 0), "9": (-1, 1)}


def _cell(raw):
    return raw["player"]["y"], raw["player"]["x"]


def _decide(policy, raw, previous):
    if previous is not None:
        raw["_completed_operation_owner"] = previous
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, MONRACE)))
    if key:
        policy.confirm_key_posted(key)
    return key, (policy.last_reason if key else None)


class KeptGuardianApproachRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = TemporaryDirectory()
        policy = _policy(Path(cls.directory.name), MONRACE)
        first = parse_snapshot(copy.deepcopy(BOARDS[ARRIVAL]), MONRACE)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        for kind in ("staff", "wand", "rod"):
            listed = dict(copy.deepcopy(BOARDS[ARRIVAL]), turn=ARRIVAL - 1,
                          _magic_eater_power_list={"kind": kind, "rows": LISTS[kind]})
            observe_lists(policy, parse_snapshot(listed, MONRACE))
        cls.decided, previous, cls.before_shown = {}, None, None
        for turn in sorted(BOARDS):
            if turn == SHOWN[0]:
                # The policy as it meets (26,176) the first time: the closed loop starts here.
                cls.before_shown = (copy.deepcopy(policy), previous)
            key, previous = _decide(policy, copy.deepcopy(BOARDS[turn]), previous)
            cls.decided[turn] = (_cell(BOARDS[turn]), key, policy.last_reason)
            if turn in (SHOWN[0], LOST[0]):
                # The policy right after it decided the board, with the board.
                cls.after = getattr(cls, "after", {})
                cls.after[turn] = (copy.deepcopy(policy),
                                   parse_snapshot(copy.deepcopy(BOARDS[turn]), MONRACE))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_both_cells_walk_the_same_way(self):
        # Recorded: '3' at (26,176) and '7' at (27,177), alternating.  Now both step toward
        # (28,176): the guardian's last shown cell keeps the eagle's use cells out on both.
        for turn in SHOWN:
            self.assertEqual(self.decided[turn], ((26, 176), "3", APPROACH), turn)
        for turn in LOST:
            self.assertEqual(self.decided[turn], ((27, 177), "1", APPROACH), turn)

    def test_the_memory_restrains_the_walk_only(self):
        self.assertLessEqual(game_distance(NORTH, GUARDIAN), destruction_use.WORST_RADIUS)
        policy, board = self.after[LOST[0]]
        self.assertNotIn(GUARDIAN, [monster.position for monster in (
            *board.visible_monsters, *board.detected_monsters)])
        target = destruction_use.quest_target_race(policy, board)
        # The walk: the remembered cell is kept out of the use cells.
        self.assertIn(GUARDIAN, destruction_use.spared_positions(policy, board))
        # The use: the board only, so a circle reaching the remembered cell is not refused.
        self.assertNotIn(GUARDIAN, destruction_use._use_spared_positions(policy, board, target))
        self.assertFalse(destruction_use._spared_in_circle(policy, board, target, centre=NORTH))

    def test_a_shown_guardian_still_refuses_the_use(self):
        policy, board = self.after[SHOWN[0]]
        target = destruction_use.quest_target_race(policy, board)
        self.assertIn(GUARDIAN, destruction_use._use_spared_positions(policy, board, target))
        self.assertTrue(destruction_use._spared_in_circle(policy, board, target, centre=NORTH))

    def test_no_livelock_melt_in_the_alternation(self):
        # Recorded: livelock:stone-to-mud on 6851424, 6851463, 6851491, 6851506, 6851527.
        reasons = [self.decided[turn][2] for turn in sorted(BOARDS) if turn >= SHOWN[0]]
        self.assertNotIn("livelock:stone-to-mud", reasons)

    def test_closed_loop_walks_on_south(self):
        by_cell = defaultdict(list)
        for turn in sorted(BOARDS):
            by_cell[_cell(BOARDS[turn])].append(turn)
        policy, previous = copy.deepcopy(self.before_shown[0]), self.before_shown[1]
        cell, turn, cells = (26, 176), SHOWN[0], []
        for _ in range(8):
            turns = by_cell[cell]
            if not turns:
                break  # no recorded board of this cell
            raw = copy.deepcopy(BOARDS[turns[-1]])
            raw["turn"] = turn
            key, previous = _decide(policy, raw, previous)
            cells.append(cell)
            step = STEPS.get(str(key))
            if step is None:
                break
            cell = (cell[0] + step[0], cell[1] + step[1])
            turn += 4
        self.assertGreaterEqual(len(cells), 4, cells)
        self.assertEqual(cells[:4], [(26, 176), (27, 177), (28, 176), (29, 175)])
        self.assertEqual(len(cells), len(set(cells)), cells)


if __name__ == "__main__":
    unittest.main()
