"""The 2026-09-28 Home scans and blocked town board retain a usable curse scroll."""

import tests  # noqa: F401

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import (STORE_HOME, SV_SCROLL_STAR_REMOVE_CURSE, TVAL_SCROLL,
                           _parse_items, parse_snapshot)
from hengbot.policy import HengbotPolicy
from hengbot.protocol import snapshot_protocol_version


FIXTURE = (Path(__file__).parent / "fixtures" /
           "star-remove-curse-unused-20260928.json.gz")
SHA256 = "6f33b3d5b99e4aa438584c0f6f2881b6b772da7e21687a9b4d37a26056ad8bdb"


class StarRemoveCurseUnusedRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.capture = json.load(stream)
        cls.board = parse_snapshot(cls.capture["board"])

    def _policy(self):
        policy = HengbotPolicy()
        policy.prime(self.board)
        knowledge = self.capture["knowledge"]
        policy.consume_home_knowledge(tuple(_parse_items(
            knowledge["knowledge"]["items"],
            protocol=snapshot_protocol_version(knowledge),
        )))
        return policy

    def test_every_recorded_scan_typed_the_scroll_and_blocked_board_needs_it(self):
        self.assertEqual(self.capture["decision"], {
            "decision_sequence": 1292,
            "key": "5",
            "reason": "town:blocked:owner-retired",
            "turn": 7131951,
            "town_plan": {"stops": ["Alchemist"], "index": 1,
                          "inserted_this_visit": [], "skipped_latched": []},
        })
        scans = self.capture["scan_scrolls"]
        self.assertEqual(len(scans), 22)
        self.assertTrue(all(row["matches"] == [{
            "name": "*解呪*の巻物", "tval": TVAL_SCROLL,
            "sval": SV_SCROLL_STAR_REMOVE_CURSE, "count": 1,
            "aware": True,
        }] for row in scans))
        policy = self._policy()
        self.assertEqual((policy._home_star_remove_curse_count,
                          policy._carried_star_remove_curse_count(self.board),
                          policy._recall_departure_shortage(self.board),
                          policy._has_unremovable_curse_target(self.board)),
                         (1, 0, False, True))
        self.assertIn("home-star-remove-curse-use",
                      {need.category for need in policy._enumerate_town_needs(self.board)})

    def test_restored_board_binds_withdrawal_then_reads_and_observes_cure(self):
        policy = restore_checkpoint(HengbotPolicy, checkpoint(self._policy()))
        policy._home_pending_item = None
        policy._home_withdrawal_queued = False
        reserve = next(item for item in policy._home_knowledge_items
                       if item.tval == TVAL_SCROLL
                       and item.sval == SV_SCROLL_STAR_REMOVE_CURSE)
        policy._bind_home_star_remove_curse_withdrawal(self.board)
        self.assertEqual(policy._derived_home_visit_request(self.board).item_identity,
                         policy._item_signature(reserve))
        self.assertIsNotNone(policy._shopping_approach_step(
            self.board, STORE_HOME, requester="store-router"))
        self.assertTrue(policy._star_remove_curse_reserve_withdraw_pending)
        entrance_position = next(
            pos for pos, grid in self.board.grids.items()
            if grid.store_number == STORE_HOME
        )
        entrance = replace(self.board, player=replace(
            self.board.player, position=entrance_position,
        ))
        policy._home_page_size = self.capture["home_store_page_size"]
        take = policy._atomic_home_withdraw_key(entrance, entrance_position)
        self.assertEqual(take, "5pv\x1b")
        self.assertEqual(policy._home_atomic_withdraw_pending[0],
                         policy._item_signature(reserve))
        carried = replace(reserve, slot="s")
        gained = replace(self.board, inventory=(*self.board.inventory, carried))
        policy.confirm_key_posted(take)
        policy._observe(gained)
        self.assertEqual(policy._town_remove_curse_key(gained), "rs")
        self.assertFalse(policy._star_remove_curse_reserve_withdraw_pending)
        cured = replace(gained, equipment=tuple(
            replace(item, is_cursed=False) if item.slot == "body" else item
            for item in gained.equipment
        ), inventory=self.board.inventory)
        policy._observe(cured)
        self.assertIsNone(policy._remove_curse_watch)
        self.assertFalse(policy._has_unremovable_curse_target(cured))


if __name__ == "__main__":
    unittest.main()
