"""n1-c life-216's loop stop on Angband 50F (2026-11-17 02:40): the hunt melted toward vetoed ground
that had nothing to do with its target.

Live (Magic-Eater Lv47, RANDOM quest 40, build bb4fb7c5a): the target 『世界の裁判長』 (race 1134)
stood at (33,34) behind rock.  Telepathy shows a monster up to MAX_PLAYER_SIGHT (20) cells away
(monster-update.cpp decide_sight_invisible_monster, gamevalue.h), so from (33,54) the target was
shown and from (33,55) it was not.  On (33,54) the hunt (hunt_target ``route_key``) found no walk
and no unspent frontier closer to the target, gave the cell up and asked
retreat_enclosure.walled_off_key, which answered for the only ground the floor's retreat vetoes
walled off: 13 cells at row 49 behind the veto (49,55), 20+ cells from the target, whose one
frontier (49,42) the walk had already spent.  Its Stone to Mud route went east: '6' to (33,55),
``stuck:walled-off-stone-to-mud``.  There the target was not shown, the hunt did not answer, and
the livelock's 50F+ stuck walk (deep_teleport ``stuck_key``) went back west: '4' to (33,54),
``stuck:deep-walk``.  The same pair had alternated on (41,52)/(41,53) before, until the loop
detector stopped the bot.

The vetoes answer the hunt only when the ground they wall off holds what the walk would go to
(``_vetoes_close_the_way``: a cell beside the shown cell, or an unspent frontier closer to it).

Recorded: tests/fixtures/n1c-216-hunt-veto-loop-1117.jsonl.gz
(tests/extract_n1c_216_hunt_veto_loop_1117_fixture.py): the boards of turns 3873594 and 3873599,
their decisions, the stop's vetoes, and the floor memory (walkable, door, rubble and marked cells,
the probed frontiers) and the
hunt's floor visit (race, spent frontiers) of the incident's town-arrival checkpoint replayed through
the captured boards to turn 3873591 (its stuck decisions matched the live log turn for turn): the
board alone does not show the Magic-Mapped strip at row 49.  DECLARED CONSTRUCTED: the shown cell,
(33,34) where the board's telepathy shows the target (the replayed visit had given it up on the
previous board), and in the guard case moved onto the vetoed strip.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import hunt_target, retreat_enclosure
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-hunt-veto-loop-1117.jsonl.gz"
FIXTURE_SHA256 = "ecb8d5aa6f17bc4b8e363a4c47b8550c2b325191bd627b969bc7e24579c3350a"
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
TARGET_CELL = Position(33, 34)


def _rows():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


ROWS = _rows()
VETOES = frozenset(Position(y, x) for y, x in next(row for row in ROWS if row["role"] == "vetoes")["cells"])
BOARDS = {row["board"]["turn"]: row["board"] for row in ROWS if row["role"] == "board"}
DECISIONS = {row["decision"]["turn"]: row["decision"] for row in ROWS if row["role"] == "decision"}
MEMORY = next(row for row in ROWS if row["role"] == "memory")
SPENT = frozenset(Position(y, x) for y, x in MEMORY["hunt_visit"]["spent_frontiers"])


class HuntVetoLoopTest(unittest.TestCase):
    def hunt(self, turn, shown=TARGET_CELL):
        """``route_key`` on the board of ``turn`` with the stop's vetoes and the hunt's visit."""
        with TemporaryDirectory() as directory:
            policy = _policy(Path(directory), MONRACE)
            snapshot = parse_snapshot(copy.deepcopy(BOARDS[turn]), MONRACE)
            policy.prime(snapshot)
            policy._floor_t = {tuple(cell) for cell in MEMORY["floor_t"]}
            policy._door_t = {tuple(cell) for cell in MEMORY["door_t"]}
            policy._rubble_t = {tuple(cell) for cell in MEMORY["rubble_t"]}
            policy._marked_t = {tuple(cell) for cell in MEMORY["marked_t"]}
            policy._probed_frontiers = {Position(y, x) for y, x in MEMORY["probed_frontiers"]}
            policy._engagement_owned_avoid_cells |= VETOES
            policy._engagement_avoid_cells |= VETOES
            setattr(policy, hunt_target.MEMORY, hunt_target.FloorVisit(
                snapshot.floor_key, race=MEMORY["hunt_visit"]["race"], position=shown,
                spent_frontiers=SPENT))
            key = hunt_target.route_key(policy, snapshot, policy._physical_hostiles(snapshot))
            return policy, snapshot, key

    def test_the_recorded_alternation(self):
        self.assertEqual(
            [(DECISIONS[turn]["key"], DECISIONS[turn]["reason"]) for turn in sorted(DECISIONS)],
            [("6", retreat_enclosure.MELT_REASON), ("4", "stuck:deep-walk")])

    def test_vetoed_ground_away_from_the_target_does_not_answer_the_hunt(self):
        policy, snapshot, key = self.hunt(3873594)
        walled = retreat_enclosure.walled_off(policy, snapshot)
        self.assertIsNotNone(walled)  # the strip at row 49 behind (49,55)
        self.assertFalse(any(cell.distance_to(TARGET_CELL) <= 1 for cell in walled.ground))
        self.assertIn(Position(49, 42), SPENT)  # the strip's one frontier closer to the target
        self.assertIsNone(key)
        self.assertNotEqual(policy.last_reason, retreat_enclosure.MELT_REASON)
        self.assertIsNone(getattr(policy, hunt_target.MEMORY).position)  # the cell is given up

    def test_vetoed_ground_beside_the_shown_cell_still_answers(self):
        # Guard: the target shown on the vetoed strip (n1-b life-317's shape).
        policy, snapshot, key = self.hunt(3873599, shown=Position(49, 48))
        self.assertIsNotNone(retreat_enclosure.walled_off(policy, snapshot))
        self.assertIsNotNone(key)


if __name__ == "__main__":
    unittest.main()
