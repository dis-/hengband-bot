"""n1-a life-512's town:blocked:survival:identify_staff_ready stop (2026-11-12 07:20).

Recorded: the capture's town-arrival checkpoint, visit journal and sidecar files
(tests/extract_idstaff_stockout_home_kit_1112_fixture.py).  The rows before the
fixed decision go through the public chooser and the live CLI's owner-retirement
entrance (--owner-retired-log-only, as the viewing bots run).

The warrior (Lv46, 7,932 gold) held 17 of the 20 Identify-staff charges a deep
departure needs; neither the Magic shop nor the Black Market sold a staff, so row
15 opened the Identify-staff stockout time-pass (one mining run, fundraising
``prepare``).  Home held the run's kit (eleven diggers, Treasure Detection), but
the visit had already spent Home's pass bound (three unsatisfied passes): the
blocked Home hid the kit claim, prepare refused (no digger, no detection), the
open set made the town end a stop, and row 16 stopped.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import copy
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from hengbot.cli import _handle_owner_retirement
from hengbot.model import STORE_HOME
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import TOWN_TRAVEL_STORE_SYMBOLS
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import adopt_calibration, decisions, journal, restore


FIXTURES = Path(__file__).with_name("fixtures") / "idstaff-stockout-home-kit-1112"
# The viewing bots' CLI flag (owner retirements logged and forgiven).
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
STOCKOUT_ROW = 15
STOP_ROW = 16


class IdstaffStockoutHomeKit1112RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, stop):
        """The stop's arrival policy, its journal rows and its board suppliers."""
        visit = self.scratch / stop / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        fixture = FIXTURES / stop
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((fixture / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(sidecars["manifest"], ensure_ascii=False), encoding="utf-8")
        for role, data in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(base64.b64decode(data))
        runtime = self.scratch / stop / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path",
                          runtime)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def replay_live(self, policy, recorded, steps):
        """Replay ``steps`` as the live CLI decided and posted them."""
        for (row, supply) in steps:
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
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def test_0720_stockout_set_routes_home_for_its_kit(self):
        """Row 16: the set's kit on Home's shelf sends the visit Home.

        Live: ``5`` town:blocked:survival:identify_staff_ready.
        """
        policy, recorded, steps = self.load("n1a-512-0720")
        self.assertEqual(recorded[STOCKOUT_ROW]["reason"],
                         "town:entrance-step-off:town:identify-staff-stockout-mining")
        self.assertEqual((recorded[STOP_ROW]["key"], recorded[STOP_ROW]["reason"]),
                         ("5", "town:blocked:survival:identify_staff_ready"))
        self.replay_live(policy, recorded, steps[:STOP_ROW])
        board = steps[STOP_ROW][1]()
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertTrue(policy._identify_staff_mining_plan)
        self.assertFalse(policy._identify_staff_ready(board))
        self.assertFalse(policy._fundraising_kit_secured(board))
        self.assertTrue(policy._has_withdrawable_digging_tool(board))
        self.assertTrue(policy._has_withdrawable_treasure_detection(board))
        key = policy.choose_key(board)
        self.assertEqual(
            (key, policy.last_reason),
            (f"\x1b`n{TOWN_TRAVEL_STORE_SYMBOLS[STORE_HOME]}.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)
        self.assertIsNone(policy._town_blocked_reason)


if __name__ == "__main__":
    unittest.main()
