"""Recorded pins: the unseen retreat and seek-loot alternated at a dead end (Forest 32F).

Live incident: 2026-10-03 11:11:09-11:11:27, Forest (dungeon 7) 32F, one bot
process.  Decision 4638 read an emergency teleport after 「何かが混乱のブレスを
吐いた。」; from 4639 the armed unseen-attacker retreat walked its reverse
direction (taken from the last pre-teleport cell, (-1, 75)) for 135
decisions without finding a cell of at most two open neighbours, and reached
the dead end (1, 196) at the floor's east wall.  There no neighbour lies
further along the reverse direction, so ``_unseen_retreat_key`` returned None
-- but left the retreat armed -- and ``seek-loot`` (target (2, 183)) stepped
west to (1, 195).  On that board the still-armed retreat had a reverse step
again and took the decision back east.  The two owners undid each other one
cell apart (4774-4809, one ``nav:break-oscillation`` that did not break it)
until the loop detector stopped the bot at turn 6189355.  HP was 731/731 and
no hostile was visible on the alternation boards.

The fix is ownership: a retreat whose reverse route is exhausted without a
choke retires (as it already does when its choke wait ends) instead of
staying armed and silent.

Substrate: tests/fixtures/reverse-choke-loot-loop-20261003.* frozen by
tests/extract_reverse_choke_loot_loop_fixture.py (sources and selection in
its docstring): the character's skill_exp row, the 433 boards of this floor
before the first recorded decision (warm-up: the policy's floor terrain
memory decides the retreat's route, and the earlier decisions were rotated
out of the decision log, so their keys are not asserted), and the input
board of each recorded decision 4552-4775.

Replay fidelity (R4): before the fix a fresh process fed these boards
reproduces the recorded (key, reason) of every decision 4552-4809.  With the
fix it reproduces 4552-4774 -- including the arming at 4639 and the walk into
the dead end -- and 4775, the first board on which live stepped back into
the vacated dead end, is the first divergence; nothing later is asserted,
because every later recorded board follows the recorded reversal.

Walls: tests/__init__ runtime-file isolation; Home history/disposal files and
the calibration file live in a temporary directory.  The boards are dungeon
floors, so no Home/town/shop producer is reached.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "reverse-choke-loot-loop-20261003.jsonl.gz"
RECORDED = FIXTURES / "reverse-choke-loot-loop-20261003.recorded.json"
CALIBRATION = FIXTURES / "reverse-choke-loot-loop-20261003.character-calibration.json"
# R9: digests of the bytes with CRLF normalized to LF.
SHA256 = {
    FIXTURE: "8718cbf7f3f7d07ac3d83d6d454238dfd8a897776c6032476283ff7c5b3619bf",
    RECORDED: "e417251d41e2530c32e883c7b4a45856eb20fa0c716d897ffa7b845b21d863a4",
    CALIBRATION: "d76c2847286be477b89a7ddaedf6a77b9188a6a4664527459b6327606fb6a748",
}

FIRST = 4552
TELEPORT = 4638
ARMED = 4639
DEAD_END_REACHED = 4774  # the first board on the dead end (1, 196)
REVERSAL = 4775  # live stepped back into the dead end on this board
LOOP_STOP_TURN = 6189355
DEAD_END = Position(1, 196)
BACK = Position(1, 195)
LOOT = [2, 183]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class ReverseChokeLootLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        knowledge = json.loads(
            next(r for r in records if r["role"] == "skill-knowledge")["line"])
        warm_up = [r["line"] for r in records if r["role"] == "warm-up"]
        inputs = {
            r["sequence"]: r["line"] for r in records if r["role"] == "decision-input"
        }
        payload = json.loads(RECORDED.read_text(encoding="utf-8"))
        cls.recorded = {row[0]: row for row in payload["recorded"]}
        cls.stop = payload["stop"]
        cls.inputs = inputs

        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        tmp = TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        policy = _policy(directory, monrace)
        policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        policy.consume_skill_knowledge(knowledge)

        def decide(line):
            _decoded, snapshots = _consume_response_sequence(
                [line], policy, lambda _key: True, monrace,
                knowledge_ledger_path=directory / "knowledge.jsonl",
            )
            board = snapshots[-1]
            key = policy.choose_key(board)
            row = (str(key), policy.last_reason)
            policy.confirm_key_posted(key)
            return row, board

        for line in warm_up:
            decide(line)
        cls.rows, cls.boards = {}, {}
        for sequence in sorted(inputs):
            cls.rows[sequence], cls.boards[sequence] = decide(inputs[sequence])

    def _live(self, sequence):
        row = self.recorded[sequence]
        return (row[2], row[3])

    def test_recorded_rows_are_the_incident(self):
        self.assertEqual(self._live(TELEPORT), ("rg", "emergency:teleport"))
        self.assertTrue(any(
            message.startswith("何か") for message in self.recorded[TELEPORT][9]
        ))
        walked = [n for n in range(ARMED, DEAD_END_REACHED)
                  if self._live(n)[1] == "unseen:reverse-choke"]
        self.assertGreaterEqual(len(walked), 120)
        self.assertEqual(self.recorded[DEAD_END_REACHED - 1][4], [BACK.y, BACK.x])
        # The uninterrupted alternation: seek-loot vacates the dead end, the
        # still-armed retreat steps back into it.
        self.assertEqual(
            [tuple(self.recorded[n][2:5]) for n in range(DEAD_END_REACHED, 4781)],
            [
                ("4", "seek-loot", [DEAD_END.y, DEAD_END.x]),
                ("6", "unseen:reverse-choke", [BACK.y, BACK.x]),
            ] * 3 + [("4", "seek-loot", [DEAD_END.y, DEAD_END.x])],
        )
        for n in range(DEAD_END_REACHED, 4810):
            row = self.recorded[n]
            with self.subTest(sequence=n):
                self.assertIn(
                    tuple(row[4]),
                    {(1, 192), (1, 193), (1, 194), (1, 195), (1, 196), (2, 194)},
                )
                self.assertEqual(row[6], 731)
                if row[3] == "seek-loot":
                    self.assertEqual(row[7], LOOT)
        reasons = [self._live(n)[1] for n in range(DEAD_END_REACHED, 4810)]
        self.assertEqual(reasons.count("unseen:reverse-choke"), 17)
        self.assertEqual(reasons.count("seek-loot"), 17)
        self.assertEqual(self.stop["reason"], "loop-detected")
        self.assertEqual(self.stop["turn"], LOOP_STOP_TURN)

    def test_dead_end_has_no_cell_further_east(self):
        board = self.boards[DEAD_END_REACHED]
        self.assertEqual(board.player.position, DEAD_END)
        open_neighbours = {
            Position(DEAD_END.y + dy, DEAD_END.x + dx)
            for dy in (-1, 0, 1) for dx in (-1, 0, 1)
            if (dy, dx) != (0, 0)
            and (grid := board.grid_at(Position(DEAD_END.y + dy, DEAD_END.x + dx)))
            is not None and grid.known and grid.passable
        }
        self.assertEqual(
            open_neighbours, {Position(1, 195), Position(2, 195), Position(2, 196)}
        )

    def test_replay_reproduces_live_into_the_dead_end(self):
        self.assertEqual(
            {n: self.rows[n] for n in range(FIRST, REVERSAL)},
            {n: self._live(n) for n in range(FIRST, REVERSAL)},
        )
        self.assertEqual(self.boards[REVERSAL].player.position, BACK)

    def test_retired_retreat_does_not_take_the_dead_end_back(self):
        self.assertEqual(self._live(REVERSAL), ("6", "unseen:reverse-choke"))
        key, reason = self.rows[REVERSAL]
        self.assertFalse(reason.startswith("unseen:"), reason)
        self.assertEqual((key, reason), ("4", "seek-loot"))
        # '4' is the step west, away from the vacated dead end, toward the loot.
        self.assertNotEqual(key, self._live(REVERSAL)[0])


if __name__ == "__main__":
    unittest.main()
