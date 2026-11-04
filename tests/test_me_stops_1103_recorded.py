"""n1-c night stops of 2026-11-03 (Magic-Eater), one recorded visit per root.

* shovel-deposit (life-121, quest:blocked:me-staff): the plan shelved the two
  worn Shovels, Home refused (retain-digging-tool), the abandonment wore them
  again, and the next plan took them off.
* sparrow-travel (life-122, quest:blocked:me-staff): the inn travel was refused
  on one game turn by a friendly sparrow beside the player, seven times.
* stuck-browse (life-122, stuck-prompt periodic:magic-eater-powers): the
  transaction waited behind its own suspended Home walk; the wait, with no
  reason of its own, carried the previous browse's into the executor.
* staple-hold (life-120, depth-gate into owner-retired-burst): Q31 held the
  Outpost, so the staple at 0-1 of 15 never went to the Tower.

Recorded: each capture's arrival checkpoint, calibration and journal rows
(tests/extract_me_stops_1103_fixtures.py), decided through the public chooser.
Only the stuck-browse replay constructs anything (see its test).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.equipment_optimizer import equipment_identity
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from hengbot.town_hold import hold_claims
from recorded_digger_carry import pre_digger_home_replay, pre_digger_home_rule
from replay_town_arrival import adopt_calibration, decisions, restore


FIXTURES = Path(__file__).with_name("fixtures") / "me-stops-1103"


class Visit:
    """A case's arrival policy and its journalled boards in a scratch directory."""

    def __init__(self, name):
        source = FIXTURES / name
        self._directory = TemporaryDirectory()
        root = Path(self._directory.name)
        self.scratch = root / "scratch"
        self.scratch.mkdir()
        visit = root / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((source / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((source / "journal.jsonl.xz").read_bytes())))
        self.policy = restore(visit, self.scratch)
        adopt_calibration(self.policy, source / "calibration.json", self.scratch)
        self.rows = decisions(self.policy, visit, self.scratch)

    def close(self):
        self._directory.cleanup()

    def post(self, key):
        policy = self.policy
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def replay_until_last(self, test):
        """Decide and post every row as recorded; return the last row and board."""
        rows = list(self.rows)
        for recorded, supply in rows[:-1]:
            key = self.policy.choose_key(supply())
            test.assertEqual((key, self.policy.last_reason), (recorded["key"], recorded["reason"]))
            self.post(key)
        return rows[-1][0], rows[-1][1]()


class MagicEaterStopsRecordedTest(unittest.TestCase):
    def visit(self, name):
        visit = Visit(name)
        self.addCleanup(visit.close)
        return visit

    def test_worn_shovels_off_duty_go_to_the_home_that_takes_them(self):
        # Owner 2026-11-04 「採掘に行かない時はシャベルも仕舞う」: the plan's deposit stands and
        # the Home executor, reading the same rule, does not refuse it, so
        # the abandon/re-wear alternation has no way back.
        visit = self.visit("shovel-deposit")
        recorded, board = visit.replay_until_last(self)
        self.assertEqual(recorded["reason"], "equipment-transaction:travel-home")
        self.assertIsNone(visit.policy._fundraising_mode)
        shovels = [item for item in board.inventory if item.is_digging_tool]
        self.assertEqual(sum(item.count for item in shovels), 2)
        visit.policy.choose_key(board)
        self.assertEqual(visit.policy.last_reason, "equipment-transaction:travel-home")
        self.assertIsNotNone(visit.policy._equipment_transaction_session)
        for shovel in shovels:
            self.assertFalse(visit.policy._digging_tool_stays_carried(board, shovel))

    def test_worn_shovels_of_a_mining_set_are_not_planned_into_home(self):
        visit = self.visit("shovel-deposit")
        recorded, board = visit.replay_until_last(self)
        self.assertEqual(recorded["reason"], "equipment-transaction:travel-home")
        self.assertEqual(sum(item.count for item in board.inventory if item.is_digging_tool), 2)
        self.assertEqual([item.is_digging_tool for item in board.equipment
                          if item.slot == "main_hand"], [False])
        # DECLARED CONSTRUCTED: the mining set open on the recorded board, and
        # the recorded plan dropped as the executor's refusal drops it; no new
        # plan takes the tools off again (the life-121 alternation).
        visit.policy._fundraising_mode = "prepare"
        for shovel in board.inventory:
            if shovel.is_digging_tool:
                self.assertTrue(visit.policy._digging_tool_stays_carried(board, shovel))
        visit.policy._abandon_blocked_equipment_transaction(board)
        visit.policy._equipment_transaction_failed_items.clear()
        visit.policy.choose_key(board)
        session = visit.policy._equipment_transaction_session
        identities = {equipment_identity(item) for item in board.inventory if item.is_digging_tool}
        self.assertFalse(session is not None and any(
            action.kind == "deposit" and action.item_identity in identities
            for action in session.plan.actions))

    # declared wall: tests/recorded_digger_carry.py (the subject is not the digger).
    @pre_digger_home_replay
    def test_travel_beside_the_sparrow_walks_a_step(self):
        visit = self.visit("sparrow-travel")
        recorded, board = visit.replay_until_last(self)
        self.assertEqual((recorded["key"], recorded["reason"]),
                         ("\x1b`n332.", "me-staff:return-outpost"))
        sparrow = board.visible_monsters[0]
        self.assertTrue(sparrow.friendly)
        self.assertEqual(board.player.position.distance_to(sparrow.position), 1)
        key = visit.policy.choose_key(board)
        self.assertEqual((key, visit.policy.last_reason), ("3", "me-staff:return-outpost"))

    def test_transaction_takes_its_home_walk_back_after_the_flee(self):
        # DECLARED CONSTRUCTED: the plans keep the recorded Home deposits of
        # the worn diggers (the shovel-deposit fix ends that plan earlier), as
        # any other deposit's plan would, and the recorded travel beside a
        # town monster stays (the sparrow-travel fix walks there); the rows up
        # to this board stay recorded.
        visit = self.visit("stuck-browse")
        with mock.patch.object(HengbotPolicy, "_transaction_retain_identities",
                               lambda *_args: frozenset()), mock.patch.object(
                HengbotPolicy, "_native_travel_refused_beside_monster",
                lambda *_args: False):
            # Owner 2026-11-04: the off-duty diggers' stow plan takes over the
            # recorded Home walk and then walks elsewhere, so only the recorded
            # rule reaches this board (the recorded rows are the scene); the
            # rule is on for the decision under test, the suspended walk's release.
            with pre_digger_home_rule():
                recorded, board = visit.replay_until_last(self)
            policy = visit.policy
            # The first flee step left the Home walk suspended, both weapons
            # off.  The recorded transaction waited behind it: its wait became
            # no-wait:flee for 40 boards, a Black Market agent stole a digger,
            # and the wait reached the executor as the browse that came next.
            self.assertEqual((recorded["key"], recorded["reason"]), ("2", "no-wait:flee"))
            self.assertTrue(policy._equipment_transaction_owned_items)
            self.assertEqual(policy._equipment_transaction_session.required_context, "home")
            key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")
        self.assertEqual(key, "8")
        self.assertEqual(hold_claims(policy).suspended, ())

    def test_staple_short_of_the_departure_goes_to_the_tower(self):
        visit = self.visit("staple-hold")
        recorded, board = visit.replay_until_last(self)
        self.assertEqual(recorded["reason"], "town:restore-combat-weapon")
        policy = visit.policy
        head = policy._fixed_quest_head(board)
        self.assertEqual(head.id, 31)
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant")


if __name__ == "__main__":
    unittest.main()
