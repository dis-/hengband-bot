"""n1-c life-221: a restart on the Mountain's 50F does not climb on a means not read yet.

n1-c life-221 (Magic-Eater Lv46, the absorbed *Destruction* at 96%) left town at 15:16:04 on
2026-11-23 with depth_safety's missing [] and recalled to the Mountain's 50F.  The server
redeployed the bot and restarted it at 15:17:34 (turn 4507414).  On the restarted process's first
board the absorbed-power lists were not read yet (they live in the process only; 'bA' came on the
second decision), me_capability.reliable read the absorbed *Destruction* as no means, and
deep_climb.observe's ``_standing_without_means`` held the climb (the Mountain, safe_fallback).
From the next board on, the lists read and depth_safety's missing [] again, the climb went on:
``castle-climb-landing-50:search-upstairs``, 50F -> 49F -> 47F -> 46F (owner
「n1-cはなぜ山を登っている？」「破壊の手段は十分にあるが？」).

Pinned: means not read yet (me_powers_refresh.list_pending) are not "no means" -- the first board
holds no climb, and once the staff list is read the board is the means' own (no climb reason); a
climb held anyway is dropped on a floor of its dungeon as soon as the kit admits the 50F landing
as depth_safety reads it, the band's reset-recall answer with it; a restart without the means
(the staff list read, no *Destruction* in it) still holds the climb.

Recorded: the 15:15:13 town-arrival checkpoint (tests/fixtures/n1c-221-restart-climb-1123, the
visit the departure ended) and the restarted process's boards on the Mountain's 50F (turn
4507414, the first; turn 4507417, the first climb decision).

DECLARED CONSTRUCTED:

* the restart: the arrival policy with the process-only state of a fresh process
  (``_me_device_lists`` and ``_me_power_resume_attempts`` empty, the decision sequence 0, no
  deep_climb arrival record), the switch as the departure left it (no alternate, the Mountain
  the target);
* the staff list the restarted process read ('bA', decision 1) is the arrival policy's own list
  (the boards' log keeps no list; the same life two minutes before, *Destruction* at 96%).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-restart-climb-1123"
MOUNTAIN = 14


class N1c221RestartClimbTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.arrival, _journal, _steps = load(FIXTURE, Path(cls.scratch.name))
        raws = json.loads(lzma.decompress((FIXTURE / "dungeon-boards.json.xz").read_bytes()))
        cls.first, cls.climbed = (parse_snapshot(raw, cls.arrival._monrace_knowledge)
                                  for raw in raws)
        cls.lists = copy.deepcopy(cls.arrival._me_device_lists)

    @classmethod
    def tearDownClass(cls):
        cls.arrival._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def _restarted(self):
        """DECLARED CONSTRUCTED (module docstring): the fresh process of 15:17:34."""
        from hengbot import deep_climb

        policy = copy.deepcopy(self.arrival)
        policy._me_device_lists = {}
        policy._me_power_resume_attempts = {}
        policy._me_power_resume_reads = True
        policy._decision_sequence = 0
        setattr(policy, deep_climb.MEMORY, None)
        return policy

    def _read_staff_list(self, policy, lists=None):
        """The 'bA' of decision 1 (DECLARED CONSTRUCTED: the arrival's list)."""
        policy._me_device_lists = copy.deepcopy(self.lists if lists is None else lists)
        policy._me_power_resume_attempts = {"staff": (1, 1), "wand": (1, 2), "rod": (1, 3)}
        policy._decision_sequence = 4

    def _choose(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def test_the_recorded_boards(self):
        self.assertEqual((self.first.floor_key, self.first.turn), ((MOUNTAIN, 50, 0), 4507414))
        self.assertEqual((self.climbed.floor_key, self.climbed.turn),
                         ((MOUNTAIN, 50, 0), 4507417))
        self.assertIsNone(self.arrival._alternate_dungeon)
        self.assertEqual(self.arrival._target_dungeon_id, MOUNTAIN)
        self.assertIn("staff", self.lists)

    def test_the_first_board_before_the_staff_list_holds_no_climb(self):
        from hengbot import destruction_use, dive_floor, me_powers_refresh

        policy = self._restarted()
        # Recorded: the climb held here (alternate-dungeon.json: 14, safe_fallback, [14, 45]).
        self._choose(policy, self.first)
        self.assertIsNone(dive_floor.climb_dungeon(policy))
        self.assertIsNone(policy._alternate_dungeon)
        self.assertTrue(me_powers_refresh.list_pending(self._restarted(), self.first, "staff"))
        # The staff list read: the means, and the board is no climb's.
        self._read_staff_list(policy)
        self.assertFalse(me_powers_refresh.list_pending(policy, self.climbed, "staff"))
        self.assertTrue(destruction_use.holds_means(policy, self.climbed))
        self.assertFalse(policy._missing_required_abilities(self.climbed, 50))
        _key, reason = self._choose(policy, self.climbed)
        # Recorded: castle-climb-landing-50:search-upstairs.
        self.assertFalse((reason or "").startswith("castle-climb"), reason)
        self.assertIsNone(dive_floor.climb_dungeon(policy))

    def test_a_held_climb_is_dropped_once_the_means_are_read(self):
        from hengbot import deep_climb, dive_floor

        policy = self._restarted()
        # The climb as the recorded process held it on the first board.
        self.assertTrue(deep_climb._hold_climb(policy, self.first, MOUNTAIN))
        self.assertEqual(dive_floor.climb_dungeon(policy), MOUNTAIN)
        self._read_staff_list(policy)
        deep_climb.observe(policy, self.climbed)
        self.assertIsNone(dive_floor.climb_dungeon(policy))
        self.assertFalse(deep_climb.on_floor(policy, self.climbed))
        self.assertFalse(deep_climb.climb_floor(policy, self.climbed))
        self.assertIsNone(deep_climb.key(policy, self.climbed))
        # No band to set the Mountain's recall depth back to.
        dive_floor.observe_recall_reset(policy, self.climbed)
        self.assertIsNone(getattr(policy, dive_floor.RECALL_RESET))
        _key, reason = self._choose(policy, self.climbed)
        self.assertFalse((reason or "").startswith("castle-climb"), reason)

    def test_a_restart_without_the_means_still_climbs(self):
        from hengbot import deep_climb, destruction_use, dive_floor, me_capability
        from hengbot.model import SV_STAFF_DESTRUCTION

        policy = self._restarted()
        listed = me_capability.names("staff", SV_STAFF_DESTRUCTION)
        lists = copy.deepcopy(self.lists)
        turn, rows = lists["staff"]
        lists["staff"] = (turn, [row for row in rows if row.get("name") not in listed])
        self.assertLess(len(lists["staff"][1]), len(rows))
        self._read_staff_list(policy, lists)
        self.assertFalse(destruction_use.holds_means(policy, self.first))
        deep_climb.observe(policy, self.first)
        self.assertEqual(dive_floor.climb_dungeon(policy), MOUNTAIN)
        self.assertTrue(deep_climb.on_floor(policy, self.first))
        # Never read after every bounded attempt: no means either.
        policy = self._restarted()
        policy._me_power_resume_attempts = {"staff": (3, 1)}
        policy._decision_sequence = 20
        deep_climb.observe(policy, self.first)
        self.assertEqual(dive_floor.climb_dungeon(policy), MOUNTAIN)


if __name__ == "__main__":
    unittest.main()
