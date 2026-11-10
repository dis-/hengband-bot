"""n1-a life-508's town:blocked:survival:identify_staff_ready stops (2026-11-11 03:20, 04:19).

Recorded: each capture's town-arrival checkpoint, visit journal and sidecar files
(tests/extract_identify_staff_supplier_1111_fixture.py).  The rows before the
fixed decision go through the public chooser and the live CLI's owner-retirement
entrance (--owner-retired-log-only, as the viewing bots run).

Both visits had an identification need open and the Identify staves short of the
20 charges the departure needs (19 at 03:20, 6 at 04:19).  The town need
candidates filed the staff's suppliers under an identification need only while
no identification source was held; each visit bought *Identify* scrolls, the
Magic shop's identify-staff need dropped out, nothing served the
departure-minimum leaf and the town stopped.
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
from hengbot.model import STORE_MAGIC
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import adopt_calibration, decisions, journal, restore


FIXTURES = Path(__file__).with_name("fixtures") / "identify-staff-supplier-1111"
# The viewing bots' CLI flag (owner retirements logged and forgiven).
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
END_STEP_OFF = "town:entrance-step-off:town:end-step-off"


class IdentifyStaffSupplier1111RecordedTest(unittest.TestCase):
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

    def assert_magic_shop_travel(self, stop, row, live_key, bought_row):
        policy, recorded, steps = self.load(stop)
        self.replay_live(policy, recorded, steps[:row])
        self.assertTrue(recorded[bought_row]["reason"].startswith("shop:"))
        self.assertEqual((recorded[row]["key"], recorded[row]["reason"]),
                         (live_key, END_STEP_OFF))
        board = steps[row][1]()
        self.assertFalse(policy._identify_staff_ready(board))
        self.assertIsNotNone(policy._identification_need)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b`n&.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_MAGIC)
        self.assertIsNone(policy._town_blocked_reason)

    def test_0320_identify_staff_shortage_keeps_its_supplier(self):
        """03:20, row 19: 19 of 20 charges after the *Identify* scrolls of row 16.

        Live: ``7`` town:entrance-step-off:town:end-step-off, then the stop.
        """
        self.assert_magic_shop_travel("n1a-508-0320", 19, "7", 16)

    def test_0419_identify_staff_shortage_keeps_its_supplier(self):
        """04:19, row 13: 6 of 20 charges after the *Identify* scroll of row 11.

        Live: ``8`` town:entrance-step-off:town:end-step-off, then the stop.
        """
        self.assert_magic_shop_travel("n1a-508-0419", 13, "8", 11)


if __name__ == "__main__":
    unittest.main()
