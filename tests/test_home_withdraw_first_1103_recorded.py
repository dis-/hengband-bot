"""n1-c life-112 2026-11-02 23:43:54 town:blocked:owner-retired-burst.

The equipment session's next action was to withdraw 六尺棒 (1d11) {Q34}
from Home (phase home_prepare, nothing of it in the pack); the town plan
routed to the Armoury instead.  Every Armoury approach met the session's
route refusal (equipment_route_handoff: route-refused:2, ``5``), whose Home
work was left to a Home dispatcher that never came, until the store router
retired three times (decisions 629-671).

Owner 2026-11-03 (answer, verbatim): 「先に自宅で取り出す」 -- the session's
own Home route goes first, re-entering Home even when this visit was there
already; the other errand follows.  Pinned through the public choose_key,
the Home travel goes through the production executor.
Fixture: tests/extract_home_withdraw_first_1103_fixture.py.
DECLARED RECONSTRUCTED: captures omit the session object; every recorded
row of the visit shows this one unposted withdraw (transaction_next).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from tests.test_me_nokey_1031_recorded import PostedKey
from test_hourly_0700_1102_recorded import RecordedTownPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "home-withdraw-first-1103.json.gz"
WITHDRAW = {"phase": "home_prepare", "kind": "withdraw",
            "item_id": "home:1dca1f54e16658a2:0", "target_slot": None}
HOME_TRAVEL = "\x1b`n(."
STAFF = "六尺棒 (1d11) {Q34}"


def _case():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class HomeWithdrawFirstTest(RecordedTownPolicy, PostedKey):
    @classmethod
    def setUpClass(cls):
        cls.case = _case()

    def policy(self):
        case = self.case
        raw = case["boards"]["approach"]
        policy = self.primed(raw, case["home"]["knowledge"]["items"], case["skill"])
        board = self.board(policy, raw)
        staff = policy._equipment_catalog._home[WITHDRAW["item_id"]].item
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((EquipmentTransaction(
                **WITHDRAW, item_identity=equipment_identity(staff),
                move_identity=equipment_move_identity(staff)),), (), len(raw["inventory"])))
        return policy, board, raw

    def test_recorded_refusals(self):
        rows = {row["decision_sequence"]: row for row in self.case["decisions"]}
        self.assertEqual({row["transaction_next"]["item_id"] for row in rows.values()},
                         {WITHDRAW["item_id"]})
        self.assertEqual({row["context"] for row in rows.values()}, {"home"})
        self.assertEqual((rows[629]["reason"], rows[629]["key"], rows[629]["store_type"]),
                         ("shop:approach", "5", 2))
        self.assertEqual(rows[671]["reason"], "town:blocked:owner-retired-burst")
        self.assertNotIn(STAFF, [item["name"] for item in
                                 self.case["boards"]["approach"]["inventory"]])
        self.assertIn(STAFF, [item["name"] for item in self.case["home"]["knowledge"]["items"]])

    def test_pending_home_withdraw_travels_home_first(self):
        policy, board, raw = self.policy()
        key = policy.choose_key(board)
        # Recorded: '5' shop:approach (the Armoury route refused).
        self.assertEqual((key, policy.last_reason),
                         (HOME_TRAVEL, "equipment-transaction:travel-home"))
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
