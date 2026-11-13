"""The town visit's stage table and trace (town rebuild stage 3-1, owner 2026-11-12).

Real last board of tests/fixtures/keep-running-a0 (test_keep_running_a0) through
the public choose_key; the policy doubles below are DECLARED CONSTRUCTED.
"""
import tests  # noqa: F401

import io
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from hengbot import town_visit_plan
from hengbot.town_hold import claim_family_of
from hengbot.town_visit import TownVisit
from hengbot.town_visit_plan import (
    INTERRUPT, facts, note_decision, note_seam, note_transition, stage_of,
)
from test_keep_running_a0 import ready_board

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import town_visit_plan_lint  # noqa: E402


def double(reason, sequence):
    """DECLARED CONSTRUCTED: a policy with a visit, a reason and a sequence."""
    return SimpleNamespace(last_reason=reason, _decision_sequence=sequence,
                           _town_visit=TownVisit())


TOWN = SimpleNamespace(in_town=True, store=None)


class StageTableLintTest(unittest.TestCase):
    def test_every_owner_family_has_a_stage(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(town_visit_plan_lint.main(), 0, out.getvalue())
        self.assertIn("0 gap(s)", out.getvalue())

    def test_a_missing_and_a_stale_row_are_gaps(self):
        rows = dict(town_visit_plan.FAMILY_STAGE)
        del rows["shop-buy"]
        rows["no-such-family"] = "buy"
        with patch.object(town_visit_plan, "FAMILY_STAGE", rows):
            found = town_visit_plan_lint.problems()
        self.assertIn("family 'shop-buy' has no stage row", found)
        self.assertIn("FAMILY_STAGE: 'no-such-family' is no owner family (stale row)", found)

    def test_a_transition_without_an_owner_stage_or_method_is_a_gap(self):
        rows = dict(town_visit_plan.TRANSITIONS)
        rows["rewritten"] = ("town-plan", "_progress_handover_transition")
        rows["lost"] = ("store-router", "_no_such_transition")
        with patch.object(town_visit_plan, "TRANSITIONS", rows):
            found = town_visit_plan_lint.problems()
        self.assertIn("TRANSITIONS: 'rewritten' belongs to 'town-plan', no owner's stage", found)
        self.assertIn("TRANSITIONS: 'lost' names '_no_such_transition', which the policy lacks",
                      found)


class TraceTest(unittest.TestCase):
    def note(self, policy, family, sequence):
        policy._decision_sequence = sequence
        with patch("hengbot.town_hold.claim_family_of", return_value=family):
            note_decision(policy, TOWN)

    def test_runs_of_one_stage_are_one_segment_and_interrupts_stay_inside(self):
        policy = double("x", 0)
        for sequence, family in enumerate(("survival", "home-scan", "home-visit", "combat",
                                           "shop-buy", "store-router", "departure"), 1):
            self.note(policy, family, sequence)
        self.assertEqual(policy._town_visit.plan_segments, [
            ["home", 1, 4, 2, 2], ["buy", 5, 6, 2, 0], ["departure", 7, 7, 1, 0]])
        self.assertEqual(facts(policy)["flow"], ["home", "buy", "departure"])

    def test_a_fresh_visit_forgets_the_trace(self):
        policy = double("x", 0)
        self.note(policy, "shop-sell", 1)
        policy._town_visit.begin(home_candidate_waiting=lambda: False)
        self.assertEqual(policy._town_visit.plan_segments, [])
        self.assertEqual(facts(policy), {})

    def test_a_dungeon_board_is_not_noted(self):
        policy = double("x", 0)
        with patch("hengbot.town_hold.claim_family_of", return_value="shop-buy"):
            note_decision(policy, SimpleNamespace(in_town=False, store=None))
        self.assertEqual(policy._town_visit.plan_segments, [])


class SeamTest(unittest.TestCase):
    def test_only_a_changed_key_or_reason_is_a_seam_rewrite(self):
        policy = double("shop:travel", 4)
        note_seam(policy, TOWN, ("7", "shop:travel"), "7")
        self.assertEqual(policy._town_visit.plan_rewrites, [])
        policy.last_reason = "town-progress-invariant:continue-observed-shop"
        note_seam(policy, TOWN, ("7", "shop:travel"), "")
        self.assertEqual(policy._town_visit.plan_rewrites, [
            [4, "shop:travel", "town-progress-invariant:continue-observed-shop"]])
        note_seam(policy, SimpleNamespace(in_town=False, store=None), ("7", "x"), "8")
        self.assertEqual(len(policy._town_visit.plan_rewrites), 1)

    def test_a_declared_transition_is_the_owners_not_a_seam_rewrite(self):
        """Stage 3-3e: an owner's named transition is recorded as a transition."""
        policy = double("shop:approach", 9)
        note_transition(policy, "progress-handover")
        policy.last_reason = "town-progress-invariant:defect:shop:approach=>shop:travel"
        note_seam(policy, TOWN, ("7", "shop:approach"), "8")
        self.assertEqual(policy._town_visit.plan_rewrites, [])
        self.assertEqual(policy._town_visit.plan_transitions, [
            [9, "progress-handover", "shop:approach", policy.last_reason]])
        self.assertEqual(facts(double("x", 0)), {})
        # The declaration lasts one decision, on a dungeon board too.
        note_transition(policy, "committed-loot")
        note_seam(policy, SimpleNamespace(in_town=False, store=None), ("7", "x"), "8")
        self.assertIsNone(policy._town_visit.transition_declared)
        note_seam(policy, TOWN, ("7", "x"), "8")
        self.assertEqual(len(policy._town_visit.plan_rewrites), 1)


class RecordedBoardTest(unittest.TestCase):
    def test_choose_key_notes_the_stage_of_its_own_reason(self):
        policy, board, _ = ready_board()
        with redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        stage = stage_of(claim_family_of(policy, policy.last_reason))
        segments = policy._town_visit.plan_segments
        self.assertTrue(segments, (key, policy.last_reason))
        if stage == INTERRUPT:
            self.assertGreaterEqual(segments[-1][4], 1)
        else:
            self.assertEqual(segments[-1][0], stage)


if __name__ == "__main__":
    unittest.main()
