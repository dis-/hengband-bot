"""Quest 25 on n1-b life-384 (2026-11-13 08:42): the stairway phase's two walks, recorded.

The chain (bot-decisions of ~/hengbot-soak/n1-b/life-384/captures/20261113-084238-, -084250- and
-084257-loop-detected, build bot-30771c7cc; battle phase 9, the stairway to hell [13,29]):

 * The door [13,28] open, the phase shot the stairway's grid from [13,27] until every attack was
   spent (the restart's decisions 4-33, ``ranged:magic-eater-device`` '...@13,29' and '...6').
 * Both stands, [13,27] and the door [13,28], had been reached with the stairway unseen (the
   record's ``blind_sights``), so ``_unseen_fire`` walked to another cell that sees it
   (「撃つマスは段の立ち位置の中から選び、無ければどこでもよい」): '7' from [13,27] to [12,26]
   (``quest25:walk-to-sight``).
 * On [12,26] the phase's own approach -- off the stands, walk to [13,27] -- stepped '3' back
   (``quest25:walk``); the two alternated board after board until the loop guard stopped the bot
   at 08:42:38, 08:42:50 and 08:42:57.

The rules (quest25_battle):

 * ``_stands_looked_from``: with the door open and both stands reached unseen, the walk to another
   sight owns the move; the approach to the stand gives way.
 * ``_immobile_gone`` (the tome's rule of life-382, now for the stairway too): every cell that sees
   a never-moving, visible-bodied target's grid reached with it unseen, it is not there and its
   phase ends; the walk to the sights then has an end instead of ``quest:blocked:execute``.  The
   record's ``gone`` replaces the tome's own flag; a record written with ``tome_gone`` still
   carries it (the life-384 record is one).

Recorded: tests/fixtures/n1b-384-q25-walk-sight-1113.json.gz
(tests/extract_n1b_384_q25_walk_sight_1113_fixture.py, copies of the captures in
C:/hengband-backups/pdca/captures/n1b-384-q25-walk-sight-1113): both processes' boards and the
battle record the last process left.  A fresh policy restores the record through the real path
and decides the last restart's boards through the public ``choose_key``; each key is posted
through the production executor (``_ExecutorInputPort``), the game then showing the next
recorded board (tests/test_n1b_382_q25_patrol_owner_1113_recorded ``_Replay``).

DECLARED CONSTRUCTED: the boards carry no magic-eater lists; they are the 01:33 dump's powers
(``kill_all_patrol_test.lists``) with every attack power's charges spent (``exhausted``), as the
recorded process was from decision 34 on, where it stopped firing.  The recorded boards are the
player's recorded cells, not where the replayed keys lead.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import me_device_attacks, quest25_battle as battle, quest25_battle_record
from hengbot.model import parse_snapshot
from tests import test_kill_all_patrol_1113_recorded as kill_all_patrol_test
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-384-q25-walk-sight-1113.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

STAIRWAY_CELL = (13, 29)
STANDS = {battle.geo.STAIRWAY_STAND, battle.geo.STAIRWAY_DOOR}
# The recorded pair: the approach's '3' on [12,26], the walk to a sight's '7' on [13,27].
APPROACH, LOOK = ((12, 26), "3"), ((13, 27), "7")


def exhausted():
    """DECLARED CONSTRUCTED (module note): every attack power of the lists spent."""
    found = {}
    for kind, (stamp, rows) in kill_all_patrol_test.lists().items():
        made = []
        for row in rows:
            row = dict(row)
            if (kind, row["name"]) in me_device_attacks._BY_NAME:
                row.update({"charging": row["max"]} if kind == "rod" else {"current": 0})
            made.append(row)
        found[kind] = (stamp, tuple(made))
    return found


class TheRecordingTest(unittest.TestCase):

    def test_the_two_walks_alternated(self):
        for part in ("first", "second"):
            rows = {((board["player"]["y"], board["player"]["x"]), row["key"], row["reason"])
                    for board, row in zip(CASE[part]["boards"], CASE[part]["recorded"])}
            self.assertIn((*APPROACH, battle.WALK_REASON), rows, part)
            self.assertIn((*LOOK, battle.SIGHT_REASON), rows, part)
        record = CASE["battle_record"]["battle"]
        self.assertEqual(record["phase"], battle.phase_index("stairway"))
        self.assertEqual(record["style"], "ranged")
        pairs = quest25_battle_record._decode(record["blind_sights"])
        self.assertEqual({cell for aimed, cell in pairs if aimed == STAIRWAY_CELL}, STANDS)


class OneWalkPerBoardTest(replay._Replay):
    case = CASE

    def test_spent_the_walk_to_a_sight_owns_the_move(self):
        answers = self.drive(exhausted())
        self.assertEqual(len(answers), len(CASE["second"]["boards"]) - 4, answers[-1])
        moves = {(cell, key) for _sequence, cell, key, reason, _phase in answers
                 if reason in {battle.WALK_REASON, battle.SIGHT_REASON}}
        self.assertFalse({APPROACH, LOOK} <= moves, sorted(moves))
        by_cell = {cell: (key, reason) for _sequence, cell, key, reason, _phase in answers}
        self.assertEqual(by_cell[(13, 27)], ("7", battle.SIGHT_REASON))
        self.assertEqual(by_cell[(12, 26)], ("4", battle.SIGHT_REASON))   # on, west, not back
        self.assertTrue(all(phase == battle.phase_index("stairway") for *_rest, phase in answers))

    def test_stands_not_yet_looked_from_the_approach_owns_it(self):
        # DECLARED CONSTRUCTED control: the record without its reached sights -- the stands not
        # yet looked from -- walks [12,26] back to the stand as before.
        record = copy.deepcopy(CASE["battle_record"])
        record["battle"]["blind_sights"] = {"set": []}
        answers = self.drive(exhausted(), record)
        by_cell = {cell: (key, reason) for _sequence, cell, key, reason, _phase in answers}
        self.assertEqual(by_cell[(12, 26)], ("3", battle.WALK_REASON))


class GoneOverThePhasesTest(replay._Replay):
    case = CASE

    def _sights(self, record=None):
        directory = self.enterContext(TemporaryDirectory())
        policy = replay.new_policy(Path(directory), exhausted(), record, CASE)
        raw = CASE["second"]["boards"][4]
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.choose_key(snapshot)   # the first decision restores the record (real path)
        ctx = battle._ctx(policy, snapshot)
        return ctx, battle.geo.sight_cells(ctx.open_terrain(), STAIRWAY_CELL,
                                           battle._sight_radius(ctx, STAIRWAY_CELL))

    def test_the_old_record_keeps_the_tome_gone(self):
        self.assertIs(CASE["battle_record"]["battle"]["tome_gone"], True)
        ctx, sights = self._sights()
        self.assertIn(battle.geo.TOME, ctx.battle.gone)
        self.assertTrue(sights - STANDS)   # sights left to walk to: the stairway not yet gone
        self.assertNotIn(battle.geo.STAIRWAY, ctx.battle.gone)

    def test_every_sight_looked_from_the_stairway_phase_ends(self):
        # DECLARED CONSTRUCTED: the record with every cell that sees [13,29] reached unseen (the
        # end of the walk to the sights the first rule lets run).
        _ctx, sights = self._sights()
        record = copy.deepcopy(CASE["battle_record"])
        record["battle"]["blind_sights"] = quest25_battle_record._encode(
            frozenset((STAIRWAY_CELL, cell) for cell in sights))
        answers = self.drive(exhausted(), record)
        self.assertTrue(all(phase > battle.phase_index("stairway") for *_rest, phase in answers),
                        answers[:3])
        self.assertNotIn("quest:blocked:execute", {reason for *_rest, reason, _phase in answers})


if __name__ == "__main__":
    unittest.main()
