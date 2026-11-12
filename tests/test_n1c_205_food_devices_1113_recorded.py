"""n1-c life-205's town:blocked:survival:recall_departure_ready stop (2026-11-13 00:11:52).

Recorded: the stop visit's town-arrival checkpoint, its 19 journal rows and sidecar files
(tests/extract_n1c_205_food_devices_1113_fixture.py), replayed through the public chooser and
the live CLI's owner-retirement entrance (--owner-retired-log-only).

The Lv37 zombie Magic-Eater resumed life-203's stop with the identification fix (bc33ba49f7):
rows 7-9 identified the unknown wand (サンダー・ボールの魔法棒, 10 charges) and the Staff of
Light (15 charges).  Both Wands of Wonder (the staple) were still empty.  Two defects then
stopped the visit again:

* the mining set opened at arrival for the Tower trip priced with the unknown wand
  (11,285) still owned the town, though the trip now cost 7,020 against 7,856 gold;
* rows 12-15 sold both identified devices at the Magic shop as surplus, although they were
  the food the drained staple left (``_find_edible``) -- food 0/15.

Fix: a staff-sequence expedition run that has not left town ends once the gold pays the trip
(me_staff_sequence._expedition_run_unneeded), and the retention keeps the carried charged
devices up to the charges the drained staple lacks
(magic_eater_devices.drained_staple_food, ``mana-food:drained-staple``).

Walls, declared: row 3's ``periodic:character-dump`` writes the dump the restored policy reads
next; the replay writes the game's dump (see the extractor).  The sale test holds the old
expedition latch (``_expedition_run_unneeded`` patched to False) so the recorded rows reach the
Magic shop; it pins the retention alone.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import copy
import gzip
import json
import lzma
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot import me_staff_sequence
from hengbot.cli import _handle_owner_retirement
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import adopt_calibration, decisions, journal, restore


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-205-food-devices-1113"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
STOP = "town:blocked:survival:recall_departure_ready"
TVAL_STAFF, TVAL_WAND = 55, 65
SV_WAND_THUNDER_BALL, SV_STAFF_LIGHT = 21, 8


class N1c205FoodDevices1113RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self):
        visit = self.scratch / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((FIXTURE / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(sidecars["manifest"], ensure_ascii=False), encoding="utf-8")
        for role, data in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(base64.b64decode(data))
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path",
                          runtime)
        self.dump = lzma.decompress((FIXTURE / "dump-after-row3.txt.xz").read_bytes())
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def replay_live(self, policy, recorded, steps):
        for row, supply in steps:
            board = supply()
            visit_before = copy.copy(policy._store_visit)
            chosen = policy.choose_key(board)
            self.assertEqual((chosen, policy.last_reason),
                             (recorded[row["row"]]["key"], recorded[row["row"]]["reason"]),
                             row["row"])
            key = policy.validate_read_key(board, chosen)
            key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
            if key:
                policy.confirm_key_posted(key)
                if row["reason"] == "periodic:character-dump":
                    time.sleep(0.05)   # wall: the game writes the dump after the macro
                    Path(policy._character_dump_path).write_bytes(self.dump)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def food_devices(self, board):
        wand = next(item for item in board.inventory
                    if (item.tval, item.sval) == (TVAL_WAND, SV_WAND_THUNDER_BALL))
        staff = next(item for item in board.inventory
                     if (item.tval, item.sval) == (TVAL_STAFF, SV_STAFF_LIGHT))
        self.assertEqual((wand.known, wand.charges, staff.known, staff.charges),
                         (True, 10, True, 15))
        return wand, staff

    def test_identified_trip_leaves_for_the_tower(self):
        """Row 11.  Live: ``3`` shop:approach (the Magic shop sale), row 18 the stop."""
        policy, recorded, steps = self.load()
        self.assertEqual(recorded[18]["reason"], STOP)
        self.assertEqual(recorded[6]["reason"], "me-staff:fundraise:travel-recharge:11285")
        self.replay_live(policy, recorded, steps[:11])
        board = steps[11][1]()
        self.food_devices(board)
        self.assertEqual(policy._fundraising_mode, "prepare")
        supplies = me_staff_sequence.supply_cost(policy, board)
        self.assertEqual(me_staff_sequence._expedition_cost(board, supplies), 7020)
        self.assertEqual(board.player.gold, 7856)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant")
        self.assertTrue(key.startswith("\x1b`n"))
        self.assertIsNone(policy._fundraising_mode)

    def test_magic_shop_keeps_the_drained_staples_food(self):
        """Row 12 under the old expedition latch.  Live: ``{i@0\\r`` then ``d0y`` x2 (sold)."""
        policy, recorded, steps = self.load()
        self.assertEqual([recorded[row]["reason"] for row in (12, 13, 14, 15)],
                         ["shop:in-store-inscribe", "shop:in-store-sell"] * 2)
        # Wall, declared: the Home *Enlightenment* take (owner 2026-11-13,
        # tests/test_n1c_205_enlightenment_home_1113_recorded.py) routes row 11 to Home;
        # this pin is the Magic shop's retention, so the take is held off.
        with patch.object(me_staff_sequence, "_expedition_run_unneeded",
                          lambda *args: False),                 patch.object(type(policy), "_bind_home_drink_potion_withdrawal",
                             lambda *args: None):
            self.replay_live(policy, recorded, steps[:12])
            board = steps[12][1]()
            wand, staff = self.food_devices(board)
            for device in (wand, staff):
                self.assertEqual(policy._retention_reservation_detail(board, device),
                                 (1, "mana-food:drained-staple"))
                self.assertEqual(policy._retention_surplus(board, device), 0)
            self.assertIsNone(policy._find_device_sale(board))
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b", "shop:observe-and-leave"))


if __name__ == "__main__":
    unittest.main()
