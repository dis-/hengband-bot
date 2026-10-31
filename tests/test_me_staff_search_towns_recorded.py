"""#47: a stage staff out of stock at the Outpost sends the sequence to the other towns.

Owner 2026-10-31 「資金に余力が出来たら他の街も見て回ることで時短を図る」.  The
recorded n1-c life-054 061452 visit (ring rows 104-108,
tests/fixtures/me-nokey-20261031.json.gz): the Outpost Magic shop sells no
Staff of Detect Evil, 60,981 gold, every town visited.  Every decision is the
public ``choose_key``; the key is sent through the production executor.

DECLARED CONSTRUCTED (as test_me_nokey_1031_recorded.StaffStockoutTest's
run-limit case): the four carried stage-2 staffs are already absorbed and
out of the pack, so only Detect Evil remains; the record's
``searched_towns`` rows where a case says so; the gold of the no-spare case.
Unfixed, every case mines for the restock (me-staff:fundraise:staff-stockout).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import unittest
from unittest.mock import patch

from hengbot import me_staff_sequence as sequence
from hengbot.model import parse_snapshot
from hengbot.policy_constants import TOWN_TELEPORT_COST
from tests import test_me_nokey_1031_recorded as nokey

ABSORBED = (8, 9, 12, 13)
SEARCH = "me-staff:search-staff"
STOCKOUT = "me-staff:fundraise:staff-stockout:"


class StaffSearchTownsTest(nokey.PostedKey):
    def policy(self):
        absorbed = {**nokey.CASE["recorded_sequence"]["absorbed"],
                    **{str(sval): 9 for sval in ABSORBED}}
        return nokey.staff_policy(nokey.staff_board(0), absorbed=absorbed)

    def last_board(self, gold=None):
        raw = nokey.without_staffs(nokey.staff_board(4), ABSORBED)
        if gold is not None:
            raw["player"]["gold"] = gold
        return raw

    def decide_last(self, policy, raw):
        """Rows 104-107 as recorded, then ``raw``; the teleport destination."""
        nokey.drive_staff_boards(policy, 3, absorbed=ABSORBED)
        with patch.object(policy, "_town_teleport_key", wraps=policy._town_teleport_key) as travel:
            key = nokey.decide(policy, raw, nokey.CASE["staff"]["skill"])
        destination = travel.call_args.args[1] if travel.called else None
        return key, destination

    def test_spare_gold_searches_morivant_first(self):
        policy = self.policy()
        raw = self.last_board()
        key, destination = self.decide_last(policy, raw)
        self.assertTrue(policy.last_reason.startswith(SEARCH), (key, policy.last_reason))
        self.assertEqual(destination, 2)
        self.assertEqual(sequence.state(policy).searched_towns, {0: raw["turn"]})
        self.post(policy, raw, key)

    def test_next_town_after_a_searched_morivant(self):
        policy = self.policy()
        raw = self.last_board()
        sequence.state(policy).searched_towns[2] = raw["turn"] - 10  # seen this wait
        key, destination = self.decide_last(policy, raw)
        self.assertTrue(policy.last_reason.startswith(SEARCH), (key, policy.last_reason))
        self.assertEqual(destination, 1)

    def test_every_town_searched_mines_for_the_restock(self):
        policy = self.policy()
        raw = self.last_board()
        sequence.state(policy).searched_towns.update({1: raw["turn"] - 10, 2: raw["turn"] - 10,
                                                      3: raw["turn"] - 10})
        key, destination = self.decide_last(policy, raw)
        self.assertIn(STOCKOUT, policy.last_reason, key)
        self.assertIsNone(destination)

    def test_a_town_seen_before_the_restock_wait_is_searched_again(self):
        policy = self.policy()
        raw = self.last_board()
        record = sequence.state(policy)
        record.searched_towns[2] = record.shelf_after_turn - 1  # before this wait
        key, destination = self.decide_last(policy, raw)
        self.assertEqual(destination, 2, policy.last_reason)

    def test_without_spare_gold_mines_for_the_restock(self):
        policy = self.policy()
        probe = parse_snapshot(copy.deepcopy(self.last_board()), policy._monrace_knowledge)
        target = sequence._stockout_target(policy, probe, sequence.supply_cost(policy, probe), True)
        raw = self.last_board(gold=target + 2 * TOWN_TELEPORT_COST - 1)
        key, destination = self.decide_last(policy, raw)
        self.assertIn(STOCKOUT, policy.last_reason, key)
        self.assertIsNone(destination)


if __name__ == "__main__":
    unittest.main()
