"""n1-a life-530 2026-11-18 04:57:08, equipment-transaction:restore-blocked-terminal (bot 130789a3c).

Back from a mining run, the Lv47 warrior's equipment transaction swapped the digging gear
for its fighting gear: it took off the battle pick (sub hand) and the Dwarven Shovel (main
hand), wielded Zantetsuken and Eriril (rows 4-7), walked to the Home and shelved the shovel
(row 9).  The battle pick was still to be shelved.  A Home errand filed before this visit
(the Olog mithril plate's take for *Identify*, identification-catalog) rode the
transaction's Home approach: its outside ``~9`` went out on row 11 and made it the town's
holder.  On row 12 the hold deferred the transaction's own Home approach (family
equipment-txn, ``shopping-approach``); the transaction read the empty approach as no route
to the Home and stopped with the pick still owed.  While a transaction owns the town no other
producer runs, so the errand's take, composed only by that approach
(``_atomic_home_withdraw_key``), could not run either.

The store router's Home approach already passes this hold once the errand's knowledge is
back (town_hold.home_route_opened_for, n1-c life-195 2026-11-11); the equipment
transaction's approach now does too.  Row 12 takes the plate at the entrance.

Recorded: the incident capture's town-arrival checkpoint and all 14 journal rows
(tests/extract_n1a_530_equip_restore_1118_fixture.py), posted through the live CLI's
owner-retirement entrance (--owner-retired-log-only).  Rows 0-11 are decided through the
public choose_key and compared with the record.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.cli import _handle_owner_retirement
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-equip-restore-1118"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
STOP_ROW = 12
TVAL_DIGGING = 20


def post(policy, board, key, visit_before):
    """Post ``key`` as the live CLI does."""
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1a530EquipRestore1118RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            if row == STOP_ROW:
                cls.board = board
                break
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post(policy, board, recorded["key"], before)
        cls.policy = policy

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_visit_replays_to_the_stop(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.assertEqual(self.journal[STOP_ROW]["reason"],
                         "town:entrance-step-off:equipment-transaction:restore-blocked-terminal")
        self.assertEqual(self.journal[11]["reason"],
                         "home-errand:request-knowledge:identification-catalog")

    def test_the_transaction_takes_its_home_approach_under_the_errand(self):
        policy, board = self.policy, self.board
        session = policy._equipment_transaction_session
        action = session.current_action
        self.assertEqual(action.kind, "deposit")
        [pick] = [item for item in board.inventory if item.tval == TVAL_DIGGING]
        self.assertEqual(policy._equipment_transaction_owned_items[0][1], "sub_hand")
        self.assertTrue(policy._home_errand.active)
        self.assertEqual(policy._home_errand.request.purpose, "identification-catalog")

        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("5  py\x1b", "home-errand:atomic-withdraw:identification-catalog"))
        self.assertIsNone(policy._equipment_transaction_restore_terminal)
        # The transaction still owes the pick's deposit.
        self.assertIs(policy._equipment_transaction_session, session)
        self.assertEqual(session.current_action, action)
        self.assertIn(pick, board.inventory)


if __name__ == "__main__":
    unittest.main()
