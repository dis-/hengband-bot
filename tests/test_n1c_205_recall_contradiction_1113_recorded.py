"""n1-c life-205's town:blocked:recall-readiness-contradiction (2026-11-13 06:31).

Recorded: the capture's town-arrival checkpoint, journal rows 0-54 and sidecar
files (tests/extract_n1c_205_recall_contradiction_1113_fixture.py), through the
public choose_key.

The zombie Magic-Eater (Lv43) read Word of Recall with four free pack slots,
accepted on the terminal certificate, which signs the exact stacks, names
included.  During the countdown it absorbed a wand for food (row 49,
survival:mana-absorb, 96 -> 95 charges): the wand's name changed, the
certificate no longer matched, free_pack_slots_ready failed and the canceller
read a second scroll to cancel the recall the departure had authorised (row
50, town:cancel-unready-recall).  Two scrolls were bought back and, the gate
satisfied again, the read point refused to read twice in a visit: row 54
stopped on recall-readiness-contradiction.

Town rebuild stage 3-3b: the read records the pack's occupied slots it was
authorised with, and the pack leaf cancels a recall only when the pack is
fuller than at the read.  Row 50 keeps the recall.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-205-recall-contradiction-1113"
ABSORB_ROW = 49
CANCEL_ROW = 50
STOP_ROW = 54


class N1c205RecallContradiction1113RecordedTest(unittest.TestCase):
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
        return self.steps[rows][1]()

    def test_the_absorbed_wand_does_not_cancel_the_authorised_recall(self):
        recorded = self.recorded
        self.assertEqual(recorded[ABSORB_ROW]["reason"], "survival:mana-absorb")
        self.assertEqual((recorded[CANCEL_ROW]["key"], recorded[CANCEL_ROW]["reason"]),
                         ("ri", "town:cancel-unready-recall"))
        self.assertEqual(recorded[STOP_ROW]["reason"], "town:blocked:recall-readiness-contradiction")
        board = self.replay(CANCEL_ROW)
        policy = self.policy
        self.assertTrue(board.player.recalling)
        # The certificate no longer matches the absorbed wand's name ...
        leaves = policy._recall_town_departure_conjuncts(policy._recall_departure_board(board))
        self.assertFalse(leaves["free_pack_slots_ready"])
        # ... but no slot was taken since the read: nothing to cancel for.
        self.assertFalse(policy._recall_pack_fuller_than_read(board))
        destination = (policy._pending_recall_dungeon_id
                       if policy._pending_recall_dungeon_id is not None
                       else board.recall_dungeon_id)
        self.assertEqual(policy._recall_unready_blockers(board, destination), [])
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "town:cancel-unready-recall")
        self.assertEqual((key, policy.last_reason), EXPECTED_CANCEL_ROW)
        self.assertFalse(policy._town_visit_unready_recall_cancelled)


# The recall the departure authorised keeps counting down.
EXPECTED_CANCEL_ROW = ("5", "town:wait-recall")


if __name__ == "__main__":
    unittest.main()
