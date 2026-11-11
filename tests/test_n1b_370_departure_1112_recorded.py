"""n1-b life-370's town:blocked:survival:recall_departure_ready (2026-11-12 02:08).

Recorded: the capture's town-arrival checkpoint, visit journal and sidecar
files (tests/extract_n1b_370_departure_1112_fixture.py).

The visit came back with nine Word of Recall scrolls and 2,438 gold, so the
recall shortage opened a fundraising set (mode prepare) whose mining kit
(a digger) waited in Home.  The Home pass deposited three items in one
batch (``dmdedd``); Home was full and the game refused the Short Teleport
scroll (「我が家にはもう置く場所がない。」).  The deposit kept waiting for an
effect that could not come (STORE_STUCK_LIMIT boards), its pending held
the Home visit executor in EXIT_PENDING, the digger's take was refused
(home-request-unavailable) and the town end stopped on the first unmet
survival leaf, the Recall the set was to pay for.  The departure minimum
and the supply ledger agreed (nine scrolls, short either way).

The rows replay the recorded keys (declared: row 0's periodic dump decision
depends on a calibration the replay cannot re-read, so the live decisions
are driven), so the boards and the pending deposit are the live ones.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import adopt_calibration, decisions, journal, restore


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-370-departure-1112"
SHORT_TELEPORT = ("ショート・テレポートの巻物", 70, 8)
REFUSED_ROW = 6


class N1b370Departure1112RecordedTest(unittest.TestCase):
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
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def drive_recorded(self, policy, recorded, steps):
        for (row, supply) in steps:
            board = supply()
            policy.choose_key(board)
            key = recorded[row["row"]]["key"]
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def test_refused_home_deposit_settles_on_the_next_outside_board(self):
        """Row 6: the outside board after the refused deposit.

        Live: ``5`` home:atomic-deposit-await-confirmation, the leave, the town
        end's step-off, and at row 10 town:blocked:survival:recall_departure_ready.
        """
        policy, recorded, steps = self.load()
        self.drive_recorded(policy, recorded, steps[:REFUSED_ROW])
        self.assertEqual((recorded[5]["key"], recorded[5]["reason"]),
                         ("dmdedd\x1b", "home:atomic-deposit"))
        self.assertEqual((recorded[REFUSED_ROW]["key"], recorded[REFUSED_ROW]["reason"]),
                         ("5", "home:atomic-deposit-await-confirmation"))
        self.assertEqual((recorded[10]["key"], recorded[10]["reason"]),
                         ("5", "town:blocked:survival:recall_departure_ready"))
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertIsNotNone(policy._home_atomic_deposit_pending)
        board = steps[REFUSED_ROW][1]()
        self.assertIsNone(board.store)
        self.assertIn("我が家にはもう置く場所がない。", board.messages)
        self.assertEqual(policy._count_recall_scrolls(board), 9)
        self.assertTrue(any(item.name.startswith("ショート・テレポート")
                            for item in board.inventory))
        key = policy.choose_key(board)
        self.assertIsNone(policy._home_atomic_deposit_pending)
        self.assertIn(SHORT_TELEPORT, policy._home_rejected_deposits)
        # The Home list is read again; the Home visit is free for the kit take.
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        self.assertNotEqual(policy._home_visit.state.name, "EXIT_PENDING")


if __name__ == "__main__":
    unittest.main()
