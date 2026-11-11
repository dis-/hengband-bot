"""n1-a life-508's recall stock-out with a Rod of Recall in Home (2026-11-11 00:40).

Recorded: the capture's town-arrival checkpoint, visit journal and sidecar
files (tests/extract_recall_rod_1111_fixture.py).  The rows before the fixed
decision go through the public chooser and the live CLI's owner-retirement
entrance (--owner-retired-log-only, as the viewing bots run).

The pack held ten Word of Recall scrolls against the eleven the departure
needs (the standing ten and the one the departure reads), Home held a Rod of
Recall, and both recall suppliers had been tried.  The supply ledger counted
scrolls only, so row 13 declared the stock-out and started the one-run
mining (town:recall-stockout-mining) although the rod reads Recall
(cmd-zaprod.cpp SV_ROD_RECALL) and recharges.
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
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import adopt_calibration, decisions, journal, restore


FIXTURES = Path(__file__).with_name("fixtures") / "recall-rod-1111"
FIXTURE = FIXTURES / "n1a-508-0040"
# The viewing bots' CLI flag (owner retirements logged and forgiven).
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
STOCKOUT_ROW = 13


class RecallRod1111RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, fixture=FIXTURE):
        visit = self.scratch / fixture.name / "town-arrival"
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
        runtime = self.scratch / fixture.name / "runtime"
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

    def drive_recorded(self, policy, recorded, steps):
        """Decide each row, then post the recorded key (the recorded boards follow)."""
        for (row, supply) in steps:
            board = supply()
            policy.choose_key(board)
            key = recorded[row["row"]]["key"]
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def test_0040_row1_goes_home_for_the_rod_first(self):
        """Row 1, after the ``~9`` scan: nine scrolls of eleven, the rod in Home.

        Live: ```n%.`` shop:travel to the Alchemist.  Fixed: the rod is a
        Home recall supply, so Home comes first (Home before the shops).
        """
        policy, recorded, steps = self.load()
        self.replay_live(policy, recorded, steps[:1])
        self.assertEqual((recorded[1]["key"], recorded[1]["reason"]),
                         ("`n%.", "shop:travel"))
        board = steps[1][1]()
        self.assertEqual(policy._count_recall_scrolls(board), 9)
        self.assertTrue(any(item.is_recall_rod for item in policy._home_knowledge_items))
        recall = policy._supply_ledger(board, policy._planned_depth())["recall"]
        self.assertEqual((recall.count, recall.required_departure), (9, 11))
        self.assertEqual(recall.stores[0], STORE_HOME)
        rod = next(item for item in policy._home_knowledge_items if item.is_recall_rod)
        self.assertEqual(policy._procurement_missing_amount(board, rod), 1)
        policy.choose_key(board)
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)

    def test_512_1839_rod_counts_at_the_departure_minimum(self):
        """n1-a life-512 18:39, row 33 (the stop): ten scrolls and the rod.

        Live (build bot-d62aa6e00): the ledger counted the rod (11 of 11) and
        nothing was bought, but the departure minimum's own Recall check counted
        scrolls only (10 < 11): ``5`` town:blocked:survival:recall_departure_ready
        (and again at 18:40 after the restart).
        """
        policy, recorded, steps = self.load(FIXTURES / "n1a-512-1839")
        self.replay_live(policy, recorded, steps[:33])
        self.assertEqual((recorded[33]["key"], recorded[33]["reason"]),
                         ("5", "town:blocked:survival:recall_departure_ready"))
        board = steps[33][1]()
        self.assertEqual(policy._count_recall_scrolls(board), 10)
        self.assertIsNotNone(policy._carried_recall_rod(board))
        recall = policy._supply_ledger(board, policy._planned_depth())["recall"]
        self.assertEqual((recall.count, recall.required_departure), (11, 11))
        _destination, dungeon_id = policy._town_recall_destination(board)
        depth = policy._dungeon_entry_depth(board, dungeon_id, via_recall=True)
        self.assertTrue(policy._departure_minimum(board, depth)["values"]["recall_departure_ready"])
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("rhc", "town:repetition-depart:recall"))

    def test_0040_home_recall_rod_is_no_stockout(self):
        """Row 13, on the recorded boards: ten scrolls of eleven, the rod in Home.

        Live: ```` town:recall-stockout-mining.  Fixed: the rod covers the
        departure's read, so the stock-out does not persist and no mining starts.
        """
        policy, recorded, steps = self.load()
        self.drive_recorded(policy, recorded, steps[:STOCKOUT_ROW])
        self.assertEqual((recorded[STOCKOUT_ROW]["key"], recorded[STOCKOUT_ROW]["reason"]),
                         ("", "town:recall-stockout-mining"))
        board = steps[STOCKOUT_ROW][1]()
        self.assertEqual(policy._count_recall_scrolls(board), 10)
        recall = policy._supply_ledger(board, policy._planned_depth())["recall"]
        self.assertEqual((recall.count, recall.required_departure), (10, 11))
        self.assertIn(STORE_HOME, recall.stores)
        self.assertFalse(policy._recall_stockout_persists(board))
        policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "town:recall-stockout-mining")
        self.assertFalse(policy._recall_stockout_mining_plan)

if __name__ == "__main__":
    unittest.main()
