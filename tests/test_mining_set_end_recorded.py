"""n1-c life-117/118 (2026-11-03 14:22/14:34): the mining set ended mid-decision.

The Magic-Eater came back from its mining run (Yeek Cave 1F) with the set's
runs made.  The set's run-count end ran inside the town special key, so the
owners earlier in the same decision (the departure supplier, the town
claims) planned under the still open "mine" set, where the shop selector
wants no Cure Critical Wounds: the Temple stop was skipped.  The town end,
after the set closed, saw the Temple neither visited nor skipped -- no
purchase gap, so no mining cycle -- and stopped under
town:blocked:survival:cure_critical_ready.  The Temple sold the potion at
125 and 167 gold with 1295 carried.

The run-count end now happens on the observation side, before any owner
decides on the board (policy_town._mining_set_runs_done).

Recorded: the capture's arrival checkpoint and journal
(tests/extract_mining_set_end_fixture.py), decided through the public
chooser.  Nothing is constructed.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.model import STORE_TEMPLE
from hengbot.policy import HengbotPolicy
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore


FIXTURE = Path(__file__).with_name("fixtures") / "mining-set-end-20261103"
CURE = "cure-critical"


class MiningSetEndRecordedTest(unittest.TestCase):
    def test_owners_decide_the_arrival_board_after_the_set_ended(self):
        with TemporaryDirectory() as raw:
            visit = Path(raw) / "town-arrival"
            visit.mkdir()
            (visit / POLICY_FILE).write_bytes(
                lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
            (visit / JOURNAL_FILE).write_bytes(gzip.compress(
                lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes())))
            rows = journal(visit)
            self.assertEqual([row["reason"] for row in rows], [
                "town:restore-combat-weapon", "town:restore-combat-weapon",
                "town:blocked:survival:cure_critical_ready"])
            scratch = Path(raw) / "scratch"
            scratch.mkdir()
            policy = restore(visit, scratch)
            # Recorded: the run is back with the set's runs made.
            self.assertEqual(policy._fundraising_mode, "mine")
            board = next(decisions(policy, visit, scratch))[1]()
            self.assertTrue(board.in_town)
            self.assertEqual(board.player.gold, 1295)
            temple = policy._in_store_attribute("_shelf_evidence")["pages"][
                (0, STORE_TEMPLE)]["page"]
            self.assertEqual(sorted(item.price for item in temple.items
                                    if item.name.startswith("致命傷の治癒の薬")), [125, 167])

            seen = []
            decide = HengbotPolicy._decide

            def recording(self, snapshot):
                # The mode every owner of this decision plans under.
                seen.append(self._fundraising_mode)
                return decide(self, snapshot)

            with mock.patch.object(HengbotPolicy, "_decide", recording):
                key = policy.choose_key(board)
            temple_skipped = policy._shelf_evidence_skips_need(board, STORE_TEMPLE, CURE)

        # The set ended on the observation side: the owners decided the
        # board with it closed, the Temple's Cure Critical Wounds is not
        # skipped, and the board goes shopping instead of to a stop.
        self.assertEqual(seen, [None])
        self.assertFalse(temple_skipped)
        self.assertIsNone(policy._fundraising_mode)
        self.assertEqual((key, policy.last_reason), ("\x1b`n&.", "shop:travel"))
        self.assertIsNone(policy._town_blocked_reason)


if __name__ == "__main__":
    unittest.main()
