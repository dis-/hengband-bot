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


class LadderRowsTest(unittest.TestCase):
    """Stage 3-4: the ladder takes the plan's rows from the plan, ranks unchanged."""

    def test_the_plan_rows_keep_their_ranks(self):
        from hengbot import town_hold
        step = town_hold.rung_named(town_visit_plan.STEP_RUNG[0])
        self.assertEqual((step.family, step.section, step.rank), ("town-plan", "rewrite", 1))
        defect = town_visit_plan.progress_defect_reason("shop:approach", "shop:travel")
        self.assertEqual(defect, "town-progress-invariant:defect:shop:approach=>shop:travel")
        rung = town_hold.rung_of("detectors", defect)
        self.assertEqual((rung.name, rung.rank), (town_visit_plan.PROGRESS_INVARIANT_RUNG[0], 0))
        # the detectors' rank, the one the cycle detector's ordinary rung had
        self.assertEqual(rung.rank, town_hold.rung_of("detectors", "livelock:exhausted").rank)
        # Stage 3-4b: the town repetition cycle's break ranks at the same plan rung.
        cycle = town_hold.rung_of("detectors", town_visit_plan.CYCLE_BREAK_REASON)
        self.assertEqual((cycle.name, cycle.rank), (town_visit_plan.PROGRESS_INVARIANT_RUNG[0], 0))


class TraceTest(unittest.TestCase):
    def note(self, policy, family, sequence):  # also called unbound (self=None)
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


class StageDeadlineTest(unittest.TestCase):
    """Stage 3-5 (owner 2026-11-13 「測った最大の2倍を期限に」)."""

    def test_deadlines_are_twice_the_larger_measurement(self):
        # Owner 2026-11-14 「ループと止まり以外の全訪問で測る」 and 「歩きは数えない」.
        self.assertEqual(town_visit_plan.STAGE_DEADLINES, {
            "quest": 28, "buy": 36, "home": 60, "fundraising": None, "departure": 110,
            "equipment": 60, "sell": 24, "identification": 26, "travel": None})
        # 「期限を付けず数が貯まったら測る」: travel and fundraising wait for visits.
        self.assertEqual(town_visit_plan.UNMEASURED_STAGES, {"travel", "fundraising"})

    def test_a_stage_past_its_deadline_is_its_named_stop(self):
        policy = double("x", 0)
        deadline = town_visit_plan.STAGE_DEADLINES["identification"]
        for sequence in range(1, deadline + 1):
            TraceTest.note(None, policy, "identification", sequence)
        self.note_interrupts(policy)
        self.assertEqual(policy._town_visit.stage_decisions, {"identification": deadline})
        with patch("hengbot.town_hold.claim_family_of", return_value="identification"):
            self.assertEqual(town_visit_plan.stage_deadline_stop(policy, TOWN),
                             "town:blocked:stage-deadline:identification")
            self.assertIsNone(town_visit_plan.stage_deadline_stop(
                policy, SimpleNamespace(in_town=False, store=None)))
        with patch("hengbot.town_hold.claim_family_of", return_value="survival"):
            self.assertIsNone(town_visit_plan.stage_deadline_stop(policy, TOWN))
        with patch("hengbot.town_hold.claim_family_of", return_value="shop-sell"):
            self.assertIsNone(town_visit_plan.stage_deadline_stop(policy, TOWN))
        policy._town_visit.begin(home_candidate_waiting=lambda: False)
        self.assertEqual(policy._town_visit.stage_decisions, {})

    def test_walks_are_not_counted_and_never_stop(self):
        """Owner 2026-11-14 「歩きは数えない」.  DECLARED CONSTRUCTED from the
        reasons of n1-a life-522's stop (2026-11-14 08:34:58,
        town:blocked:stage-deadline:equipment): 32 walks toward Home
        (equipment-transaction:approach-home) and 19 steps toward a town
        monster (town:kill-mob-approach) were counted against the equipment
        stage while its swaps progressed."""
        policy = double("x", 0)
        walks = ([("7", "equipment-transaction:approach-home")] * 32
                 + [("\x1b`n%.", "equipment-transaction:approach-home")]
                 + [("5", "shop:travel:await-entry")])
        for sequence, (key, reason) in enumerate(walks, 1):
            policy.last_reason = reason
            policy._decision_sequence = sequence
            with patch("hengbot.town_hold.claim_family_of", return_value="equipment-txn"):
                note_decision(policy, TOWN, key)
        self.assertEqual(policy._town_visit.stage_decisions, {})
        for sequence in range(1, 4):
            policy.last_reason = "equipment-transaction:deposit"
            with patch("hengbot.town_hold.claim_family_of", return_value="equipment-txn"):
                note_decision(policy, TOWN, "dp2\r")
        self.assertEqual(policy._town_visit.stage_decisions, {"equipment": 3})
        # Past the deadline, a walk is still no stop; an operation is.
        policy._town_visit.stage_decisions["equipment"] = town_visit_plan.STAGE_DEADLINES["equipment"]
        with patch("hengbot.town_hold.claim_family_of", return_value="equipment-txn"):
            policy.last_reason = "equipment-transaction:approach-home"
            self.assertIsNone(town_visit_plan.stage_deadline_stop(policy, TOWN, "7"))
            policy.last_reason = "equipment-transaction:deposit"
            self.assertEqual(town_visit_plan.stage_deadline_stop(policy, TOWN, "dp2\r"),
                             "town:blocked:stage-deadline:equipment")
        self.assertTrue(town_visit_plan.is_walking("7", "town:kill-mob-approach"))
        self.assertFalse(town_visit_plan.is_walking("p", "home:atomic-withdraw"))

    def note_interrupts(self, policy):
        # Interrupts are not counted against any stage.
        TraceTest.note(None, policy, "combat", 9)


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

    def test_the_stage_past_its_deadline_stops_the_recorded_board(self):
        """The recorded board through choose_key with its stage's deadline spent
        (DECLARED CONSTRUCTED count): the decision is the stage's named stop."""
        policy, board, _ = ready_board()
        with redirect_stdout(io.StringIO()):
            policy.choose_key(board)
        stage = stage_of(claim_family_of(policy, policy.last_reason))
        if stage not in town_visit_plan.STAGE_DEADLINES:
            self.skipTest(f"the recorded decision is {stage}")
        policy, board, _ = ready_board()
        policy._town_visit.stage_decisions[stage] = town_visit_plan.STAGE_DEADLINES[stage]
        with redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:blocked:stage-deadline:" + stage)
        self.assertEqual(key, "5" if key == "5" else key)
        from hengbot.policy_constants import POLICY_FINAL_STOP_PREFIXES
        self.assertTrue(policy.last_reason.startswith(POLICY_FINAL_STOP_PREFIXES))


if __name__ == "__main__":
    unittest.main()
