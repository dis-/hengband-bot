"""n1-c life-202's town:blocked:survival:inventory_weight_ready stop (2026-11-12 17:18:25).

Recorded: the stop visit's town-arrival checkpoint, its 144 journal rows and sidecar files
(tests/extract_town_weight_torch_1112_fixture.py).  The rows go through the public chooser and
the live CLI's owner-retirement entrance (--owner-retired-log-only, as the viewing bots run).

The Lv8 Magic-Eater (STR index 17: limit ``adj_str_wgt[17] * 50`` = 1350, player-status.cpp
``calc_weight_limit``; weights in 0.1 lb, pack and worn) arrived wielding a sling.  Rows
116-123 shelved a sword, a polearm and the pack's light crossbow (110) for the weight
(1735 -> 1365); rows 129-136 took the crossbow back out of Home and wore it for the sling
(+105, 1470); after the purchases the pack weighed 1500 and row 143 stopped.  Kept: seventeen
throwing torches (510, ``carry-strategy:lit_torch``: Q1's opening carry merged below Lv10).

Owner 2026-11-12 「ライトクロスボウを装備したあと松明を持っているなら全て自宅に仕舞うようにして」
(torch_release): once the crossbow is worn (row 136) the torches are no carry and row 137 shelves
all seventeen at Home (recorded: the General Store trip that bought torches); the pack is then
1470 - 510 = 960.  The equipment swap's withdrawal (row 130) asks the kept weight
(equipment_swap_weight): it may go on because the crossbow releases the torches; without the
owner's release it would end at 1465 kept and is refused.

Walls, each declared:
- row 1's ``periodic:character-dump`` writes the dump file the restored policy reads at row 2;
  the replay writes the dump the live game wrote there (the restarted arrival's sidecar copy,
  see the extractor) once the key is posted;
- ``test_mining_mode_keeps_recall_stock`` sets the fundraising mode to ``mine`` on the row 137
  board and forgets this visit's purchases, so the nine Recall scrolls are a stock carried in
  from an earlier visit (DECLARED CONSTRUCTED state: the 17:13 visit that sold the nine,
  ``overweight-surplus-disposal.jsonl`` in the sidecars, is not captured).
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

from hengbot import torch_release
from hengbot.cli import _handle_owner_retirement
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import adopt_calibration, decisions, journal, restore


FIXTURE = Path(__file__).with_name("fixtures") / "town-weight-torch-1112"
# The viewing bots' CLI flag (owner retirements logged and forgiven).
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
WITHDRAW_ROW = 130
WORN_ROW = 136
STASH_ROW = 137
STOP_ROW = 143
LIMIT = 1350
TORCHES = 17
TORCH_WEIGHT = 30


class TownWeightTorch1112RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self):
        """The arrival policy, its journal rows and its board suppliers."""
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

    def replay_live(self, policy, recorded, steps):
        """Replay ``steps`` as the live CLI decided and posted them."""
        dump = lzma.decompress((FIXTURE / "dump-after-row1.txt.xz").read_bytes())
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
                    # Wall: the game writes the dump after the posted macro.
                    time.sleep(0.05)
                    Path(policy._character_dump_path).write_bytes(dump)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def test_worn_light_crossbow_shelves_every_torch(self):
        """Row 137: the torches go Home; recorded the General Store trip, then the stop."""
        policy, recorded, steps = self.load()
        self.assertEqual((recorded[STOP_ROW]["key"], recorded[STOP_ROW]["reason"]),
                         ("5", "town:blocked:survival:inventory_weight_ready"))
        self.assertEqual(recorded[STASH_ROW]["reason"], "shop:travel")
        self.replay_live(policy, recorded, steps[:STASH_ROW])
        board = steps[STASH_ROW][1]()
        bow = next(item for item in board.equipment if item.slot == "bow")
        self.assertEqual((bow.tval, bow.sval), (19, 23))   # ライトクロスボウ
        self.assertTrue(policy._worn_light(board).is_lantern)
        self.assertTrue(torch_release.released(policy, board))
        self.assertEqual(policy._inventory_weight_limit(board), LIMIT)
        self.assertEqual(policy._inventory_weight(board), 1470)
        torch = next(item for item in board.inventory if item.is_torch)
        self.assertEqual((torch.count, torch.weight), (TORCHES, TORCH_WEIGHT))
        # No torch carry is left: the quest force, the retention and the throwing stock.
        strategy = policy._carry_procurement_strategy(board)
        self.assertEqual(strategy.required_force["throwing_items"]["lit_torch"], 0)
        self.assertEqual(policy._retention_reservation(board, torch), 0)
        self.assertEqual(torch_release.throwing_torch_target(policy, board, 10), 0)
        self.assertTrue(policy._home_deposit_candidate(torch, board))
        self.assertIsNone(policy._find_light_sale(board))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("5", "equipment-transaction:atomic-deposit"))
        deposit = policy._home_atomic_deposit_pending[0]
        self.assertEqual([(entry[0][1:], entry[1], entry[2]) for entry in deposit],
                         [((39, 0), TORCHES, TORCHES)])
        # Shelved, the pack is under the limit with room for the recorded purchases (+30).
        self.assertLessEqual(policy._inventory_weight(board) - TORCHES * TORCH_WEIGHT + 30, LIMIT)

    def test_swap_withdrawal_refused_without_the_torch_release(self):
        """Row 130 without the owner's release: the kept pack cannot carry the crossbow.

        Recorded (and with the release): ``po`` equipment-transaction:withdraw.  Without it the
        swap ends at 1360 - 5 + 110 = 1465 kept, over 1350 and heavier than now: refused.
        """
        policy, recorded, steps = self.load()
        self.assertEqual(recorded[WITHDRAW_ROW]["reason"], "equipment-transaction:withdraw")
        with patch.object(torch_release, "CROSSBOW_SVALS", frozenset()):
            self.replay_live(policy, recorded, steps[:WITHDRAW_ROW])
            board = steps[WITHDRAW_ROW][1]()
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("\x1b", "equipment-transaction:withdraw-overweight"))
        self.assertIn("withdraw-overweight", policy._equipment_transaction_session.blockers)

    def test_mining_mode_keeps_recall_stock(self):
        """The recall stock of the planned depth is no surplus while mining (17:13 sale).

        DECLARED CONSTRUCTED state: fundraising mode ``mine`` on the row 137 board, and no
        purchase of this visit (the stock came from an earlier one).
        """
        policy, recorded, steps = self.load()
        self.replay_live(policy, recorded, steps[:STASH_ROW])
        board = steps[STASH_ROW][1]()
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(recall.count, 9)
        self.assertEqual(policy._recall_target(policy._planned_depth()), 9)
        policy._fundraising_mode = "mine"
        # Carried from an earlier visit, as at 17:13: no visit-purchase hold.
        policy._town_visit_purchases = set()
        policy._town_visit_purchase_quantities = {}
        self.assertEqual(policy._recall_required_target(board), 0)
        self.assertEqual(policy._retention_reservation(board, recall), 9)
        self.assertEqual(policy._retention_surplus(board, recall), 0)
        self.assertNotIn(recall.slot, [entry[2].slot
                                       for entry in policy._overweight_surplus_candidates(board)])


if __name__ == "__main__":
    unittest.main()
