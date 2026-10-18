"""Replay the C4-A town chase of a piranha the bot never caught (issue #71).

Fixture rows (copied as-is, raw encoding):
  0, 1: state rows 52 and 53 of c4a-loops-20261016/20261018-215136-town-blocked-
        owner-retired-burst (turns 2925188, 2925196; town, Level 28).  Row 0 sees
        ピラニア (race 70, AQUATIC) at (50,134), nine cells away in deep water;
        row 1 sees nothing.  The recorded decisions were town:kill-mob-approach
        '3' and '2' (the second one the walk to where the fish was last seen).
  2:    state row 11 of .../20261018-144457-town-blocked-owner-retired-burst
        (turn 2535038): やせこけた馬, a land monster, at (24,118).

DECLARED CONSTRUCTED: the runtime state a single row cannot carry -- an empty
Home catalogue (the recorded policy had scanned Home), the ~f skill-exp cache
and the cross-area fundraising switch; in the adjacent control, the piranha
moved next to the player.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "town-aquatic-chase-20261018.jsonl.gz"
SHA256 = "ec8fff0f4c71ea4510e2c41c6829b42f6faf253ff0d6d0ce2df1d84ebb1f7d8c"
PIRANHA = 70


class TownAquaticChaseRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == SHA256
        cls.lines = gzip.decompress(data).decode("utf-8").splitlines()
        assert len(cls.lines) == 3
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.policy = _policy(self.directory, self.monrace)
        self.policy._crossarea_fundraising_enforced = True
        # DECLARED CONSTRUCTED: the Home catalogue the recorded policy held.
        self.assertTrue(self.policy.consume_home_knowledge(()))

    def _board(self, index):
        _decoded, snapshots = _consume_response_sequence(
            [self.lines[index]], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        self.assertEqual(len(snapshots), 1)
        board = snapshots[-1]
        # DECLARED CONSTRUCTED: the ~f skill-exp cache.
        self.policy._skill_exp_cache = (
            0, 0, board.player.level, self.policy._town_visit_epoch
        )
        return board

    def test_recorded_far_piranha_is_not_chased_and_travel_resumes(self):
        seen = self._board(0)
        self.assertEqual(seen.turn, 2925188)
        (fish,) = seen.visible_monsters
        self.assertEqual((fish.race_id, fish.position), (PIRANHA, Position(50, 134)))
        self.assertIn("AQUATIC", self.monrace[PIRANHA].flags)
        self.assertEqual(seen.player.position.distance_to(fish.position), 9)
        self.policy._build_grid_index(seen)
        self.assertIsNone(self.policy._town_kill_mob_key(seen))
        self.assertIsNone(self.policy._town_hunt_target)
        # The ordinary ranged rule handles the visible hostile instead.
        self.assertEqual(
            (self.policy.choose_key(seen), self.policy.last_reason),
            ("fp2", "ranged:fire"),
        )

        lost = self._board(1)
        self.assertEqual((lost.turn, lost.visible_monsters), (2925196, []))
        self.assertEqual(
            (self.policy.choose_key(lost), self.policy.last_reason),
            ("\x1b`n%.", "shop:travel"),
        )

    def test_control_land_monster_is_still_chased(self):
        board = self._board(2)
        (horse,) = board.visible_monsters
        self.assertNotIn("AQUATIC", self.monrace[horse.race_id].flags)
        self.policy._build_grid_index(board)
        self.assertEqual(
            (self.policy._town_kill_mob_key(board), self.policy.last_reason),
            ("9", "town:kill-mob-approach"),
        )
        self.assertEqual(self.policy._town_hunt_target, Position(24, 118))

    def test_control_adjacent_piranha_is_still_fought(self):
        board = self._board(0)
        here = board.player.position
        # DECLARED CONSTRUCTED: the piranha in the deep water next to the player.
        cell = next(
            position for position, grid in sorted(board.grids.items())
            if here.distance_to(position) == 1 and grid.terrain_id == 83
        )
        (fish,) = board.visible_monsters
        fish = replace(fish, position=cell, distance=1)
        grids = dict(board.grids)
        grids[fish.position] = replace(
            grids[fish.position], has_monster=True,
            monster_index=fish.index,
        )
        old = board.visible_monsters[0].position
        grids[old] = replace(grids[old], has_monster=False, monster_index=0)
        board = replace(board, visible_monsters=[fish], grids=grids)
        self.policy._build_grid_index(board)
        self.assertIsNone(self.policy._town_kill_mob_key(board))
        self.assertEqual(self.policy._town_hunt_target, cell)
        key = self.policy.choose_key(board)
        self.assertEqual(
            (key, self.policy.last_reason),
            (self.policy._direction_key(here, cell), "melee"),
        )


if __name__ == "__main__":
    unittest.main()
