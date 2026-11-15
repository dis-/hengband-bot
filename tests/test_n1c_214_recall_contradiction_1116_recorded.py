"""n1-c life-214's town:blocked:recall-readiness-contradiction (2026-11-16 06:26).

Recorded: the capture's town-arrival checkpoint, journal rows 0-43 and sidecar
files (tests/extract_n1c_214_recall_contradiction_1116_fixture.py), through the
public choose_key.

The zombie Magic-Eater (Lv44) read Word of Recall at row 33 (turn 6,468,445)
with every departure leaf true.  The optimizer's obtainable ammunition then
held the General Store's arrows and iron shots, seen on its page as shelf
evidence.  During the countdown that evidence aged out (row 43, turn
6,468,542): the optimizer's memo key changed, it searched again from the same
worn kit and chose the Ring of Speed for the Ring of Damage.  The fixed-quest
readiness read the departure gate on the countdown's board, which started that
equipment transaction; equipment_departure_ready failed, the canceller read a
second scroll to cancel the recall the read point had authorised (row 43,
town:cancel-unready-recall), the transaction swapped the ring, and the read
point refused to read twice in a visit (journal row 72,
recall-readiness-contradiction).

Every reader of the equipment leaf reads the board the armed read was
authorised on (``_recall_departure_board``), at the read's turn: row 43 keeps
the recall.

DECLARED: the replay has no dump file written by the game, so after the
character dump of row 32 the retained C response is dropped and the
calibration recorded at the arrival is kept.  Live, rows 33-42 answered from
the optimizer's memo (signature-cache-hit), so the dump re-derived the same
constants.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.model import TVAL_ARROW, TVAL_SHOT
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-214-recall-contradiction-1116"
DUMP_ROW = 32
READ_ROW = 33
CANCEL_ROW = 43
READ_TURN = 6468445
# The General Store's plain arrows and iron shots on its aged-out page.
SHELF_TVALS = {TVAL_ARROW, TVAL_SHOT}


class N1c214RecallContradiction1116RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.recorded, self.steps = load(FIXTURE, Path(scratch.name))

    def replay(self, rows):
        policy = self.policy
        for row, supply in self.steps[:rows]:
            board = supply()
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason),
                             (self.recorded[row["row"]]["key"], self.recorded[row["row"]]["reason"]),
                             row["row"])
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
            if row["row"] == DUMP_ROW:
                policy._calibration_dump_pending = None
                policy._calibration_dump_response = None
        return self.steps[rows][1]()

    def test_aged_shelf_evidence_does_not_cancel_the_authorised_recall(self):
        recorded = self.recorded
        self.assertEqual(recorded[DUMP_ROW]["reason"], "town:character-dump")
        self.assertEqual(recorded[READ_ROW]["reason"], "town:recall-to-angband")
        self.assertEqual((recorded[CANCEL_ROW]["key"], recorded[CANCEL_ROW]["reason"]),
                         ("re", "town:cancel-unready-recall"))
        board = self.replay(CANCEL_ROW)
        policy = self.policy
        self.assertTrue(board.player.recalling)
        self.assertEqual(policy._town_recall_issue_watch[1], READ_TURN)
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "town:cancel-unready-recall")
        self.assertEqual((key, policy.last_reason), EXPECTED_CANCEL_ROW)
        self.assertFalse(policy._town_visit_unready_recall_cancelled)
        # No equipment transaction was started for the same worn kit.
        self.assertIsNone(policy._equipment_transaction_session)
        # The countdown's board no longer sees the General Store's page ...
        live = {item.tval for item in policy._obtainable_launcher_ammunition(board)}
        self.assertFalse(SHELF_TVALS & live)
        # ... the board the read was authorised on still does.
        departure = policy._recall_departure_board(board)
        self.assertEqual(departure.turn, READ_TURN)
        authorised = {item.tval for item in policy._obtainable_launcher_ammunition(departure)}
        self.assertLessEqual(SHELF_TVALS, authorised)
        destination = (policy._pending_recall_dungeon_id
                       if policy._pending_recall_dungeon_id is not None
                       else board.recall_dungeon_id)
        self.assertEqual(policy._recall_unready_blockers(board, destination), [])


# The recall the departure authorised keeps counting down.
EXPECTED_CANCEL_ROW = ("5", "town:wait-recall")


if __name__ == "__main__":
    unittest.main()
