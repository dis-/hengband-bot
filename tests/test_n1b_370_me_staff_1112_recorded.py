"""n1-b life-370's no-key-exhausted and quest:blocked:me-staff (2026-11-12 02:19-02:20).

Recorded: two town-arrival checkpoints with their visit journals and
sidecar files (tests/extract_n1b_370_me_staff_1112_fixture.py): ``arrival``,
the first process's visit (rows 0-20, row 20 the chest drop), and
``restart``, the restarted process's whole visit (five rows, row 4 the stop).

The Magic-Eater Lv45 came back to the Outpost from Morivant with 19 of 23
pack slots used (the terminal reserve is four free).  At the Home entrance
(45,123), a pocket whose only open side is the three cells to the east, the
town chest pass dropped a carried chest (the entrance holds no object, so it
landed on (45,124)) and opened it there; a polearm and a mithril armour
scattered onto (44,124) and (46,124).  Every way out of the pocket now
carried a pile the floor-step budget refused:

* 02:19:49, first process: the town's WAIT on the entrance went to the
  entrance step-off, which had no step; the empty key stopped the bot as
  no-key-exhausted.
* 02:20:00, the restart (this journal): the staff sequence read the staff
  list alone (``bA``), so the two carried Wands of Stone to Mud (the power
  absorbed at 168 before the restart) counted as below the cap, a Morivant
  expedition was due, and the inn route had no legal path: the sequence
  stopped as travel-morivant-unavailable.

Recorded keys are replayed up to the board under test.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import me_staff_sequence
from hengbot.model import STORE_HOME, Position
from hengbot.policy_constants import MORIVANT_TOWN_ID, WAIT_KEY
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from hengbot.town_pack_budget import floor_step_fits, pile_fits
from replay_town_arrival import adopt_calibration, decisions, journal, restore


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-370-me-staff-1112"
STOP_ROW = 4
CHEST_DROP_ROW = 20
HOME_ENTRANCE = Position(45, 123)
POCKET_EXITS = frozenset({Position(44, 124), Position(45, 124), Position(46, 124)})


class N1b370MeStaff1112RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, name):
        fixture = FIXTURE / name
        visit = self.scratch / name / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((fixture / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(sidecars["manifest"], ensure_ascii=False), encoding="utf-8")
        for role, data in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(base64.b64decode(data))
        runtime = self.scratch / name / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path",
                          runtime)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def stop_board(self):
        policy, recorded, steps = self.load("restart")
        for row, supply in steps[:STOP_ROW]:
            policy.choose_key(supply())
            policy.confirm_key_posted(recorded[row["row"]]["key"])
        self.assertEqual((recorded[3]["key"], recorded[3]["reason"]),
                         ("bA", "me-staff:read-powers"))
        self.assertEqual((recorded[STOP_ROW]["key"], recorded[STOP_ROW]["reason"]),
                         ("", "quest:blocked:me-staff"))
        board = steps[STOP_ROW][1]()
        self.assertEqual(board.player.position, HOME_ENTRANCE)
        self.assertEqual(board.grids[HOME_ENTRANCE].store_number, STORE_HOME)
        self.assertEqual((len(board.inventory), board.player.gold), (19, 7066))
        return policy, board

    def test_restart_reads_the_wand_list_before_a_tower_trip(self):
        """Row 4: the carried Stone to Mud wands' list is read, not a stop."""
        policy, board = self.stop_board()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("bB", "me-staff:read-powers"))
        record = me_staff_sequence.state(policy)
        self.assertIsNone(record.failure)
        # The staff list (``bA``) was read; the wands' power count is unknown
        # to this process, so the wands still look like an extra to charge.
        self.assertTrue(record.powers_read)
        self.assertIn("staff", policy._me_device_lists)
        self.assertNotIn("wand", policy._me_device_lists)
        self.assertEqual(set(me_staff_sequence.carried_extras(policy, board)), {"wand:6"})

    def test_piles_sealing_the_home_pocket_are_its_way_out(self):
        """Row 4: the pocket's three piles are walkable as its only exits."""
        policy, board = self.stop_board()
        for cell in POCKET_EXITS:
            self.assertEqual(board.grids[cell].object_count, 1)
            self.assertFalse(pile_fits(board, cell))
            self.assertTrue(floor_step_fits(board, cell))
        self.assertEqual(
            set(policy._walkable_neighbors(board, board.player.position)), POCKET_EXITS)
        # The inn route of the expedition (travel-morivant-unavailable).
        route = policy._town_teleport_route(board, MORIVANT_TOWN_ID)
        self.assertIsNone(route.failure)
        self.assertIn(route.route.first_step, POCKET_EXITS)
        # The entrance step-off whose WAIT became the empty key at 02:19:49.
        key = policy._town_entrance_step_off_key(board, "policy:none-wait")
        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "town:entrance-step-off:policy:none-wait")

    def test_the_carried_chest_is_not_dropped_on_the_home_entrance(self):
        """Arrival row 20: the chest drop that sealed the Home pocket."""
        policy, recorded, steps = self.load("arrival")
        for row, supply in steps[:CHEST_DROP_ROW]:
            policy.choose_key(supply())
            policy.confirm_key_posted(recorded[row["row"]]["key"])
        self.assertEqual((recorded[CHEST_DROP_ROW]["key"], recorded[CHEST_DROP_ROW]["reason"]),
                         ("dt", "chest:drop"))
        board = steps[CHEST_DROP_ROW][1]()
        self.assertEqual(board.player.position, HOME_ENTRANCE)
        self.assertTrue(any(item.slot == "t" and policy._is_processable_chest(item)
                            for item in board.inventory))
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "chest:drop")
        self.assertFalse(key.startswith("d"))


if __name__ == "__main__":
    unittest.main()
