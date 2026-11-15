"""A wield after the takeoff, refused by the full-Home retry ledger (n1-c life-214).

Recorded: n1-c life-214 (Magic-Eater Lv42) stopped in town twice with
``town:blocked:unmet:equipment_departure_ready``: 2026-11-16 00:46:37 (build
bot-37d6ee994) and 01:14:54 (bot-2449505d8).  Both visits ran the same two
sessions: the first withdrew a piece from the Home and wore it, its deposit of
the replaced piece was refused (``我が家にはもう置く場所がない``), the session
was abandoned with the swap restored, and the Home's full relief parked the
withdrawn piece in its retry ledger (``_home_full_retry_deposits``) for a later
deposit.  After the Home full sale made room, the optimizer planned the same
piece again (00:46 強撃のセスタス, 01:14 ドラゴン・グローブ, both for the arms
slot): the takeoff was posted and observed, and the wield was refused at its
terminal admission as ``item-command-reserved`` (owner ``home-full-retry``).
The session was abandoned on that refusal, the piece went into
``_equipment_transaction_failed_items``, and every later preparation of the
visit answered ``equipment-transaction-failed``.  The optional-failure
departure (owner 2026-10-03 「失敗した任意の装備の変更は今の確定した装備で
出発」) stayed closed because the Home was still a reachable, unattempted route
(``_equipment_failure_unexecutable_this_visit``), though no producer had work
there, so the town end blocked.  A restart cleared both the retry ledger and the
failed set (process memory), which is why the next process departed.

Fixture: tests/extract_n1c_214_equip_departure_1116_fixture.py, the 00:46
capture's arrival replayed on main 2449505d8 through row 281, then rows
282-340 (fixture rows 0-58; ``ROW_OFFSET``).  The 01:14 capture's arrival
journal ends when that visit left for Zul, so it is not replayable; its decision
log shows the same refusal (``ドラゴン・グローブ`` wield, ``item-command-reserved``)
and is pinned by its mechanism here.

Pins:
* rows 282-283 decide as recorded; at row 284 (the board after the takeoff)
  the session wears the planned cestus instead of being abandoned, and the
  piece is the session's, not the retry ledger's;
* with the session gone (DECLARED CONSTRUCTED: the same board) the retry ledger
  still owns the parked piece against a sale;
* with the reclaim reverted (the wield refused as live), the visit replays as
  recorded through row 339 and the town end departs on the confirmed current
  loadout instead of blocking.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot import item_reservation
from hengbot.cli import _handle_owner_retirement
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-214-equip-departure-1116" / "n1c-214-0044"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
ROW_OFFSET = 282
WIELD_ROW = 284 - ROW_OFFSET
STOP_ROW = 340 - ROW_OFFSET
CESTUS = "強撃のセスタス (-1,+15) [5,+9] (-1) {+攻;麻|強}"
STOP = "town:blocked:unmet:equipment_departure_ready"


def post(policy, board, key, visit_before):
    """Post ``key`` as the live CLI does."""
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    return key


def replay(policy, recorded, steps, mismatches):
    """Decide and post each row as the live CLI did; collect differences."""
    for row, supply in steps:
        board = supply()
        before = copy.copy(policy._store_visit)
        key = policy.choose_key(board)
        entry = recorded[row["row"]]
        if (key, policy.last_reason) != (entry["key"], entry["reason"]):
            mismatches.append((row["row"] + ROW_OFFSET, key, policy.last_reason))
        post(policy, board, entry["key"], before)


class EquipDeparture1116RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """The fix's visit to the board after the takeoff, and the live refusal's to the stop."""
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURE, Path(scratch.name) / "fixed")
        cls.recorded = recorded
        cls.arrival_retry = policy._home_full_retry_deposits
        cls.arrival_session = policy._equipment_transaction_session
        cls.mismatches = []
        replay(policy, recorded, steps[:WIELD_ROW], cls.mismatches)
        cls.before_wield = policy
        cls.wield_board = steps[WIELD_ROW][1]()
        # Revert-proof: the reclaim off, as it was live (the wield refused).
        live, _recorded, live_steps = load(FIXTURE, Path(scratch.name) / "live")
        live._equipment_transaction_wields_item = lambda item: False
        cls.live_mismatches = []
        replay(live, recorded, live_steps[:WIELD_ROW], cls.live_mismatches)
        live_wield_board = live_steps[WIELD_ROW][1]()
        cls.live_before_wield = copy.deepcopy(live)
        cls.live_wield_board = live_wield_board
        before = copy.copy(live._store_visit)
        key = live.choose_key(live_wield_board)
        entry = recorded[WIELD_ROW]
        if (key, live.last_reason) != (entry["key"], entry["reason"]):
            cls.live_mismatches.append((WIELD_ROW + ROW_OFFSET, key, live.last_reason))
        post(live, live_wield_board, entry["key"], before)
        replay(live, recorded, live_steps[WIELD_ROW + 1:STOP_ROW], cls.live_mismatches)
        cls.stop_board = live_steps[STOP_ROW][1]()
        cls.stop_key = live.choose_key(cls.stop_board)
        cls.stop_reason = live.last_reason
        cls.live = live

    def policy(self):
        return copy.deepcopy(self.before_wield)

    def cestus(self, board):
        return next(item for item in board.inventory if item.name == CESTUS)

    def test_rows_before_the_wield_decide_as_recorded(self):
        self.assertEqual(self.mismatches, [])
        # The checkpoint (before row 282): the first session's withdrawn cestus
        # is parked in the retry ledger, and the second session plans it.
        self.assertEqual([entry[0][0] for entry in self.arrival_retry], [CESTUS])
        session = self.before_wield._equipment_transaction_session
        self.assertEqual([action.kind for action in session.plan.actions],
                         ["takeoff", "equip", "deposit"])
        # The takeoff is posted; this board is its observed effect.
        self.assertEqual(session.pending_action.kind, "takeoff")
        # The session took its piece back from the ledger at the Home exit.
        self.assertIsNone(self.before_wield._home_full_retry_deposits)
        # Live, this board answered the step off the shop entrance after the
        # wield was refused and the session blocked.
        entry = self.recorded[WIELD_ROW]
        self.assertEqual((entry["key"], entry["reason"]),
                         ("3", "town:entrance-step-off:equipment-transaction:takeoff"))

    def test_the_session_wears_the_piece_it_reclaims_from_the_retry_ledger(self):
        policy = self.policy()
        board = self.wield_board
        cestus = self.cestus(board)
        self.assertIsNone(item_reservation.item_reserved_by_other(
            policy, board, cestus, ("equipment-txn", "wield")))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("w" + cestus.slot, "equipment-transaction:equip"))
        self.assertEqual(policy._equipment_transaction_failed_items, set())
        session = policy._equipment_transaction_session
        self.assertTrue(session.executable)
        self.assertEqual(session.prepared_action.kind, "equip")

    def test_a_reclaimed_piece_still_in_the_ledger_is_the_sessions(self):
        # The live state before row 284: the ledger still holds the cestus.
        policy = copy.deepcopy(self.live_before_wield)
        del policy._equipment_transaction_wields_item
        board = self.live_wield_board
        self.assertEqual([entry[0][0] for entry in policy._home_full_retry_deposits], [CESTUS])
        cestus = self.cestus(board)
        self.assertIsNone(item_reservation.item_reserved_by_other(
            policy, board, cestus, ("equipment-txn", "wield")))
        verdict = item_reservation.item_reserved_by_other(
            policy, board, cestus, ("shop-sell", "sell"))
        self.assertEqual(verdict.owner, "equipment-txn")
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("w" + cestus.slot, "equipment-transaction:equip"))

    def test_without_a_session_the_retry_ledger_keeps_the_piece(self):
        # DECLARED CONSTRUCTED: the live state before row 284 with no session.
        policy = copy.deepcopy(self.live_before_wield)
        del policy._equipment_transaction_wields_item
        policy._equipment_transaction_session = None
        board = self.live_wield_board
        for work in (("shop-sell", "sell"), ("equipment-txn", "wield")):
            verdict = item_reservation.item_reserved_by_other(
                policy, board, self.cestus(board), work)
            self.assertEqual(verdict.owner, "home-full-retry", work)

    def test_an_abandoned_session_departs_on_the_current_loadout(self):
        """The live refusal (the reclaim reverted): the visit departs, not blocks."""
        self.assertEqual(self.live_mismatches, [])
        self.assertEqual(self.recorded[STOP_ROW]["reason"], STOP)
        # The town end departs: the Word of Recall read for the 49F landing,
        # with the failed swap's named outcome staged on the worn kit.
        self.assertEqual(self.stop_reason, "town:repetition-depart:recall")
        self.assertTrue(self.stop_key.startswith("r"), self.stop_key)
        pending = self.live._equipment_optional_failure_pending
        self.assertEqual(pending["reason"], "optional-optimization-failure-confirmed-loadout")
        self.assertEqual(pending["depth"], 49)
        self.assertIn("pack:d6fcd5340ff8071b:0", pending["failed_item_ids"])
        # The worn kit (11 slots), the replaced cestus back on.
        self.assertEqual(len(pending["item_ids"]), len(self.stop_board.equipment))
        self.assertTrue(all(item_id.startswith("equipped:") for item_id in pending["item_ids"]))


if __name__ == "__main__":
    unittest.main()
