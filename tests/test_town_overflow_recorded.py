"""Home remedy on the three captured overflow stop boards of 2026-10-03.

Replay wall: captures contain boards and decision facts, not the preceding
process's Python memory. Prime a fresh policy and restore only the recorded
mining/identification facts and the recorded exhausted stop list/index. Stop
categories are not exported; the real planner recomputes the new Home need.
Run the real town-space producer at its normal
ladder entry (which precedes the terminal overflow producer), including the
planner, Home visit selection, and travel composer. Earlier ladder producers
are outside this pin; no public choose_key trajectory is claimed. Each replay
ends at the first divergent key. No later captured board is treated as the
response to that key. Deposit composition and rejection checks below are
separate policy checks, not a continuation of the recorded game.
"""

import tests  # noqa: F401 -- isolate runtime writes

import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.model import STORE_HOME, STORE_WEAPON, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import MIN_TERMINAL_FREE_PACK_SLOTS, PACK_CAPACITY
from hengbot.policy_types import TownErrandPlan


FIXTURE = Path(__file__).parent / "fixtures" / "town-overflow-20261003.json.gz"
SHA256 = "81fbc948a1030c8834a0c9424371224cfaa6c7aa2b9ce1ac1580f8edcca9da2c"


class TownOverflowRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.records = json.load(stream)

    def policy_board(self, record):
        board = parse_snapshot(record["board"])
        policy = HengbotPolicy()
        policy.prime(board)
        facts = record["decision"]
        # Declared attach wall: these are facts from this board's decision.
        policy._fundraising_mode = facts["fundraising"]["mode"]
        policy._planned_mining_runs = facts["fundraising"]["planned_runs"]
        policy._identification_need = facts["identification_need"]
        policy._home_candidate_waiting = facts["home_candidate_waiting"]
        self.assertEqual(facts["town_plan"]["stops"], ["Weapon Smiths"])
        policy._town_errand_plan = TownErrandPlan(
            [STORE_WEAPON], {}, index=facts["town_plan"]["index"],
        )
        return policy, board

    def test_capture_is_the_three_overflow_stops(self):
        self.assertEqual([r["capture"] for r in self.records],
                         ["141604", "141633", "141702"])
        for record in self.records:
            policy, board = self.policy_board(record)
            self.assertEqual(board.turn, record["decision"]["turn"])
            self.assertEqual(record["decision"]["reason"],
                             "town:blocked:overflow-no-legal-disposal")
            self.assertEqual((len(board.inventory), board.player.gold), (20, 2682))
            self.assertIsNone(policy._overflow_disposal_item(board))
            self.assertEqual(record["decision"]["home_scan"]["item_count"],
                             201 if record["capture"] == "141604" else 200)

    def test_stop_boards_route_to_home_before_terminal_overflow(self):
        for record in self.records:
            with self.subTest(capture=record["capture"]):
                policy, board = self.policy_board(record)
                key = policy._town_producer_entry(
                    "_town_space_deposit_key",
                    lambda: policy._town_space_deposit_key(board),
                )
                self.assertEqual((key, policy.last_reason),
                                 ("\x1b`n(.", "shop:travel"))
                self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)
                self.assertEqual(policy._find_home_deposit(board).slot, "d")

    def test_preserve_restore_potions_through_existing_deposit_composer(self):
        policy, board = self.policy_board(self.records[0])
        deposit = policy._find_home_deposit(board)
        self.assertIsNotNone(deposit)
        self.assertTrue(policy._item_is_procurement_protected(board, deposit))
        self.assertEqual(policy._retention_reservation(board, deposit), 0)
        self.assertEqual(policy._home_deposit_key(board, deposit), "dd")
        self.assertEqual(policy.last_reason, "home:deposit")
        self.assertEqual(
            [(item.slot, count) for item, count in
             policy._home_deposit_batch(board, deposit)],
            [("d", 1)],
        )

    def test_mining_tools_and_identification_pending_equipment_stay_carried(self):
        policy, board = self.policy_board(self.records[0])
        for slot in ("p", "q", "r", "t"):
            item = next(i for i in board.inventory if i.slot == slot)
            self.assertFalse(policy._home_deposit_candidate(item, board))
        for slot in ("q", "r"):
            item = next(i for i in board.inventory if i.slot == slot)
            self.assertEqual(policy._retention_reservation_detail(board, item),
                             (1, "mining:digging-tool"))

    def test_space_remedy_respects_home_rejections(self):
        policy, board = self.policy_board(self.records[0])
        policy._home_deposit_abandoned = True
        self.assertFalse(policy._town_space_deposit_actionable(board))
        policy._home_deposit_abandoned = False
        policy._home_rejected_deposits.update(
            policy._item_signature(i) for i in board.inventory[3:8]
        )
        self.assertFalse(policy._town_space_deposit_actionable(board))

    def test_prior_home_visit_does_not_suppress_new_space_need(self):
        policy, board = self.policy_board(self.records[0])
        # Separate policy check: an earlier Home visit fulfilled a different need.
        policy._set_town_store_attempted(STORE_HOME, board.turn, "visit-complete")
        key = policy._town_producer_entry(
            "_town_space_deposit_key", lambda: policy._town_space_deposit_key(board),
        )
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))

    def test_restore_potion_deposit_is_only_for_pack_pressure(self):
        policy, board = self.policy_board(self.records[0])
        roomy = replace(
            board, inventory=board.inventory[:PACK_CAPACITY - MIN_TERMINAL_FREE_PACK_SLOTS],
        )
        for item in roomy.inventory[3:8]:
            self.assertFalse(policy._home_deposit_candidate(item, roomy))
        self.assertIsNone(policy._town_overflow_destroy_key(roomy))
        unknown = replace(board.inventory[3], known=False, aware=False)
        self.assertFalse(policy._home_deposit_candidate(unknown, board))

    def test_restore_potion_for_a_drained_stat_stays_carried(self):
        policy, board = self.policy_board(self.records[0])
        drained = replace(board, player=replace(board.player, drained_stats=("str",)))
        self.assertFalse(policy._home_deposit_candidate(board.inventory[3], drained))
        self.assertTrue(policy._home_deposit_candidate(board.inventory[4], drained))


if __name__ == "__main__":
    unittest.main()
