"""A forgiven owner retirement's exit leaves the store visit too (n1-b life-407, 2026-11-16).

Recorded: n1-b life-407's town visit of 2026-11-16 13:30 (Magic-Eater Lv50, 9 of 11 Word
of Recall, Home full; tests/extract_n1b_407_retired_home_exit_1116_fixture.py).  Journal
row 43 is the Home page after the equipment transaction's deposit: the policy decided
``home:full-skip:sale-item-held`` (Enter), the town arbiter retired the Home owner and
the live CLI's owner-retirement entrance (--owner-retired-log-only, as the viewing bots
run) forgave it and posted the exit instead.  ``_choose_key`` arms the visit's LEAVING
only for an exit it decides itself, so the equipment-transaction visit stayed OPERATING
with its posted operation outside the store.  Every later board refused the Temple's
visit (acquire ``refused``) and the released Word of Recall supplier was reported
``town:blocked:restock-store-unreachable`` 24 times until the loop detector stopped the
bot.

Rows 0-42 replay through the public chooser and the CLI entrance and decide as
recorded; row 43 decides as recorded and the entrance posts the exit.  Row 44 is the
first outside board: the exit has closed the visit and the bot walks to the Temple.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.cli import _handle_owner_retirement
from hengbot.model import STORE_HOME, STORE_TEMPLE
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import LEAVE_STORE_KEY
from hengbot.policy_types import StoreVisitPhase
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-407-retired-home-exit-1116" / "n1b-407-1330"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
RETIRED_ROW = 43
OUTSIDE_ROW = 44
BLOCKED = "town:blocked:restock-store-unreachable"


def post(policy, board, key, visit_before):
    """Post ``key`` as the live CLI does; returns what was posted."""
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    return key


class RetiredHomeExit1116RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURE, Path(scratch.name))
        cls.mismatches = []
        for row, supply in steps[:RETIRED_ROW]:
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            entry = recorded[row["row"]]
            if (key, policy.last_reason) != (entry["key"], entry["reason"]):
                cls.mismatches.append((row["row"], key, policy.last_reason))
            post(policy, board, entry["key"], before)
        board = steps[RETIRED_ROW][1]()
        before = copy.copy(policy._store_visit)
        cls.retired_decision = (policy.choose_key(board), policy.last_reason)
        cls.retired_board = board
        cls.visit_before_exit = copy.copy(policy._store_visit)
        cls.posted = post(policy, board, cls.retired_decision[0], before)
        cls.visit_after_exit = copy.copy(policy._store_visit)
        cls.outside = steps[OUTSIDE_ROW][1]()
        cls.policy = policy
        cls.recorded = recorded

    def test_rows_before_the_retirement_decide_as_recorded(self):
        self.assertEqual(self.mismatches, [])
        entry = self.recorded[RETIRED_ROW]
        self.assertEqual(self.retired_decision, (entry["key"], entry["reason"]))
        self.assertEqual(self.retired_decision, ("\r", "home:full-skip:sale-item-held"))
        self.assertEqual(self.retired_board.store.store_type, STORE_HOME)
        # The equipment transaction's deposit visit, its operation posted.
        visit = self.visit_before_exit
        self.assertEqual((visit.owner, visit.store_type, visit.phase, visit.operation_posted),
                         ("equipment-transaction", STORE_HOME, StoreVisitPhase.OPERATING, True))
        # The forgiven retirement posts the exit in place of the Enter.
        self.assertEqual(self.posted, LEAVE_STORE_KEY)
        self.assertEqual(self.recorded[OUTSIDE_ROW]["reason"], BLOCKED)

    def test_the_posted_exit_leaves_the_visit(self):
        visit = self.visit_after_exit
        self.assertEqual(visit.phase, StoreVisitPhase.LEAVING)

    def test_the_outside_board_walks_to_the_temple(self):
        policy = copy.deepcopy(self.policy)
        board = self.outside
        self.assertIsNone(board.store)
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, BLOCKED, (key, policy.last_reason))
        visit = policy._store_visit
        self.assertFalse(visit is not None and visit.owner == "equipment-transaction", visit)
        self.assertEqual(policy._shopping_approach_store_type, STORE_TEMPLE, (key, policy.last_reason))
        self.assertTrue(key.startswith("\x1b`"), (key, policy.last_reason))


if __name__ == "__main__":
    unittest.main()
