"""Recorded pin: '<' on a dungeon's top floor is not an escape when it exits to the wilderness.

Live 2026-10-02 11:50 (commit 9cf0af6f), the root of the 11:51 wilderness
loop (tests/test_wild_ambush_recorded.py): after a
``town:unsafe-recall-fallback`` recall the bot was on 城 (Castle, dungeon 12)
level 20 -- the dungeon's top floor (lib/edit/DungeonDefinitions.jsonc
``minDepth`` 20).  A ピンク・ホラー counted as an unresisted melee status
threat; ``status-threat:stairs`` (policy.py ``_escape_by_stairs``) posted '<'
because the player stood on an up staircase.  Going up from a floor whose
``dun_level - 1`` is below ``mindepth`` lands on the surface
(src/floor/floor-leaver.cpp:335-338) at the dungeon's entrance tile, and the
Castle's entrance (wild_y 34, wild_x 88) is open wilderness, not a town: the
next board was floor (0, 0, 0) at (32, 171), where the ambush followed.

Fix: ``_is_upstairs_target`` -- the predicate every ordinary '<' producer
uses (status-threat/flee/emergency/summoner stairs, return:ascend,
survival:ascend, fundraise:ascend, breeder-breakthrough, livelock:ascend,
stuck:ascend, quest:regen:ascend) -- rejects an up staircase when '<' would
leave the dungeon for a non-town tile (``_up_stairs_exit_to_wilderness``).
The bot returns to town by recall.  A dungeon entered from a town tile (Yeek
cave on the Outpost) still lands in the town.

Substrate: tests/fixtures/castle-top-floor-exit-20261002.jsonl.gz, frozen by
tests/extract_castle_top_floor_exit_fixture.py: the boards of decisions
1063..1077 and, first, the next process's ``skill_exp`` knowledge row
(declared wall: a fresh policy needs the ~f list before its first board).
A fresh policy started on 1063 reproduces every live key 1063..1075 and the
live '<' at 1076 before the fix; with the fix 1076 is the first divergence
(R4) and nothing later is asserted from the recorded boards.
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
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import UP_STAIRS_KEY

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "castle-top-floor-exit-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "castle-top-floor-exit-20261002.boundaries.json"
# The process's calibration file (live jsonlog, written 11:07:59, before both
# processes); committed with the wild-ambush pin.
CALIBRATION = FIXTURES / "wild-ambush-20261002.character-calibration.json"
SHA256 = {
    FIXTURE: "a6469df8e139299e623602f9f389e4bbfe7458ffca5f1f7b7edf32c3637b6873",
    BOUNDARIES: "69c1700fc29192565fa5cd0f722b9cccd6684ff29b6b9d8b06fd2c9deb44c4a0",
    CALIBRATION: "a71a507ffe45da1e8ca3c32a59886b3be1c88c6f68b4c6f5d691ab51e0fb6ce5",
}
CASTLE = 12
YEEK_CAVE = 2
STAIRS_EXIT = 1076  # live '<' status-threat:stairs on Castle 20F
ARRIVAL = 1077  # floor (0, 0, 0): the surface wilderness


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class CastleTopFloorExitRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        cls.recorded = {
            row[0]: dict(zip(fields, row)) for row in boundaries["recorded"]
        }
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            lines = stream.read().splitlines(keepends=True)
        cls.knowledge = json.loads(lines[0])
        cls.boards = {
            sequence: line
            for sequence, line in zip(sorted(cls.recorded), lines[1:])
        }
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        directory = Path(self._tmp.name)
        self.policy = _policy(directory, self.monrace)
        self.policy._character_calibration_path.write_bytes(
            CALIBRATION.read_bytes()
        )
        self.policy._crossarea_fundraising_enforced = True  # live argv
        self.policy.consume_skill_knowledge(self.knowledge)  # declared wall

    def _board(self, sequence):
        _decoded, snapshots = _consume_response_sequence(
            [self.boards[sequence]], self.policy, lambda _key: True,
            self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        return snapshots[-1]

    def _replay_through(self, last):
        rows = {}
        board = None
        for sequence in range(min(self.recorded), last + 1):
            board = self._board(sequence)
            key = self.policy.choose_key(board)
            rows[sequence] = (str(key), self.policy.last_reason)
            self.policy.confirm_key_posted(key)
        return rows, board

    def _live(self, sequence):
        row = self.recorded[sequence]
        return (row["key"], row["reason"])

    def test_recorded_window_is_the_incident(self):
        castle = self.policy._dungeon_knowledge[CASTLE]
        self.assertEqual(castle.min_depth, 20)
        self.assertEqual((castle.wild_y, castle.wild_x), (34, 88))
        self.assertEqual(self.policy._wilderness_map.rows[34][88], ".")
        self.assertEqual(
            self._live(STAIRS_EXIT), (UP_STAIRS_KEY, "status-threat:stairs")
        )
        self.assertEqual(self.recorded[STAIRS_EXIT]["floor"], [CASTLE, 20, 0])
        self.assertEqual(self.recorded[ARRIVAL]["floor"], [0, 0, 0])
        board = self._board(STAIRS_EXIT)
        self.assertTrue(board.grid_at(board.player.position).has_up_stairs)
        arrival = self._board(ARRIVAL)
        self.assertTrue(arrival.on_open_wilderness)

    def test_fresh_policy_reproduces_the_live_keys_before_the_exit(self):
        rows, _board = self._replay_through(STAIRS_EXIT - 1)
        self.assertEqual(
            rows,
            {sequence: self._live(sequence)
             for sequence in range(min(self.recorded), STAIRS_EXIT)},
        )

    def test_top_floor_up_stairs_is_not_an_escape(self):
        rows, board = self._replay_through(STAIRS_EXIT)
        key, reason = rows[STAIRS_EXIT]
        # First divergence (R4): live '<' status-threat:stairs.
        self.assertNotEqual(key, UP_STAIRS_KEY)
        self.assertNotIn("stairs", reason)
        # The existing status-threat ladder's next rung: read the Teleportation
        # scroll in slot e.
        self.assertEqual((key, reason), ("re", "status-threat:scroll"))
        self.assertEqual(
            next(item.name for item in board.inventory if item.slot == "e"),
            "テレポートの巻物",
        )
        self.assertTrue(self.policy._up_stairs_exit_to_wilderness())
        self.assertFalse(
            self.policy._is_upstairs_target(board.grid_at(board.player.position))
        )

    def test_the_gate_reads_the_dungeon_depth_and_the_entrance_tile(self):
        policy = self.policy
        cases = {
            (CASTLE, 20, 0): True,  # top floor, entrance in the wilderness
            (CASTLE, 21, 0): False,  # '<' reaches Castle 20F
            (1, 1, 0): True,  # Angband's entrance (40, 57) is wilderness
            (YEEK_CAVE, 1, 0): False,  # Yeek cave's entrance is the Outpost
            (0, 0, 0): False,  # the surface itself
            (999, 1, 0): False,  # unknown dungeon: previous behaviour
        }
        for floor_key, expected in cases.items():
            with self.subTest(floor_key=floor_key):
                policy._floor_key = floor_key
                self.assertEqual(policy._up_stairs_exit_to_wilderness(), expected)
        yeek = policy._dungeon_knowledge[YEEK_CAVE]
        self.assertEqual(policy._wilderness_map.rows[yeek.wild_y][yeek.wild_x], "1")


if __name__ == "__main__":
    unittest.main()
