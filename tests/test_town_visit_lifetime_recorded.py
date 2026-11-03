"""Structure stage 3-2: state that ends with its town visit (recorded boards).

Owner 2026-11-03 「3つから始める」: the two stockout mining plans and the
identification candidates move into the town visit (town_visit.TownVisit),
so the fresh-visit reset (the first town board after a floor change) ends
them.  A stockout plan is set in town and read on its run, so it lives
through the trip out and ends on the return; the next visit's shelves
decide whether another run is due.  An identification candidate ends with
the visit that bound it, together with the request it holds.

Each class arrives in town on a recorded board after a recorded or
reconstructed trip; the arrival is the board's observation (``prime``, the
launcher's observation entry), the decision is the public ``choose_key`` and
its key goes through the production executor.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
from unittest.mock import patch

from hengbot.model import DUNGEON_YEEK_CAVE, parse_snapshot
# Modules, not classes: a test class bound here would run again in this module.
import tests.test_hourly_0700_1102_recorded as town_harness
import tests.test_hourly_2300_1102_recorded as hourly_2300
import tests.test_idstaff_stockout_run_recorded as idstaff_run
import tests.test_input_executor as executor_harness
import tests.test_recall_churn_stockout_recorded as recall_churn
import tests.test_unid_deposit_recorded as unid_deposit
from tests.test_supply_shortfall_owner_recorded import _segments


def post_unchanged(test, policy, raw, key):
    """The key through the production executor (the board ten turns later)."""
    idstaff_run.IdstaffStockoutRunRecordedTest.post_dungeon_key(test, policy, raw, key)


def on_floor(raw, dungeon_id, level):
    """DECLARED CONSTRUCTED: the trip's last dungeon board (the town board's
    character on ``dungeon_id``/``level``, one game turn earlier)."""
    board = copy.deepcopy(raw)
    board["floor"] = dict(board["floor"], dungeon_id=dungeon_id, level=level, in_town=False)
    board["turn"] -= 1
    board["store"] = None
    return board


class IdentifyStaffPlanEndsWithVisitTest(idstaff_run.IdstaffStockoutRunRecordedTest):
    """n1-a life-453 (2026-11-01 00:57): the Identify-staff stockout plan.

    The recorded run (descend 885633, Yeek Cave 1F 885634, back in town
    885635) is followed by the recorded stop board (886291: 16 of 20
    charges, Magic sold out).  DECLARED CONSTRUCTED: the plan outlived the
    set that opened it, as a set end that does not clear it leaves it (the
    conquest supersession in policy_observation, the detection-stockout exit
    _try_normal_expedition_after_detection_stockout: fundraising mode None).
    Before slice 3-2 the left plan kept the next stockout run from being
    installed (_identify_staff_procurement_impossible and the departure
    gate's own check read it), so the stop board had no owner for the
    shortage; now the arrival ends it and the stop board installs the run.
    """

    def boundary(self):
        made = unid_deposit._policy

        def policy_on_the_run(directory, monrace):
            policy = made(directory, monrace)
            policy.prime(parse_snapshot(copy.deepcopy(self.case["yeek_board"]),
                                        policy._monrace_knowledge))
            policy._identify_staff_mining_plan = True
            return policy

        with patch.object(unid_deposit, "_policy", policy_on_the_run):
            return super().boundary()

    def test_arrival_ends_the_left_plan_so_the_stockout_run_is_installed(self):
        policy, raw = self.boundary()
        # The recorded arrival (885635) began this visit.
        self.assertFalse(policy._identify_staff_mining_plan)
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        key = str(policy.choose_key(board))
        self.assertTrue(policy.last_reason.endswith(idstaff_run.STOCKOUT), policy.last_reason)
        self.assertTrue(policy._identify_staff_mining_plan)
        self.assertEqual((policy._fundraising_mode, policy._planned_mining_runs), ("prepare", 1))
        self.post(policy, raw, key, self.reply(raw, key))

    # The inherited scenarios belong to their own modules.
    test_recorded_stop = None
    test_stop_board_installs_the_stockout_run_again = None
    test_stockout_run_mines_instead_of_returning_on_the_gold_target = None


class RecallStockoutPlanEndsWithVisitTest(recall_churn.RecallChurnStockoutRecordedTest,
                                          executor_harness.ProductionHarness):
    """c4-a life-013 (2026-10-18 14:42): the recall stockout plan.

    The recorded Alchemist page (row 47) starts the recall stockout
    time-pass.  DECLARED CONSTRUCTED: the run: the mining mode the departure
    sets once the kit is carried, the Yeek Cave 1F board and the walk back
    into town (the recorded town board, store closed).  The plan lives
    through the trip out (the run mines its floor out instead of returning
    on the gold target) and the return ends it with the visit.
    """

    def arrival_raw(self):
        lines, decisions = self.pin["lines"], self.pin["decisions"]
        end = next(end for index, _start, end in _segments(lines, decisions)
                   if index == recall_churn.PIN)
        raw = json.loads(lines[end - 1])
        raw["store"] = None
        raw["turn"] += 2
        return raw

    def test_plan_lives_through_the_run_and_ends_on_the_return(self):
        policy, _results, _boards = self.replay(stop=recall_churn.PIN)
        self.assertTrue(policy._recall_stockout_mining_plan)
        raw = self.arrival_raw()
        policy.prime(parse_snapshot(on_floor(raw, DUNGEON_YEEK_CAVE, 1), self.monrace))
        policy._fundraising_mode = "mine"
        self.assertTrue(policy._recall_stockout_mining_plan)
        self.assertTrue(policy._restock_time_pass_run())

        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
        policy.prime(board)
        # The return began a new visit: the plan ended with the one that set it.
        self.assertFalse(policy._recall_stockout_mining_plan)
        self.assertFalse(policy._restock_time_pass_run())
        self.assertEqual(policy._mining_runs_completed, 1)
        key = str(policy.choose_key(board))
        # The arrival's own work (shop:approach); the run-count end follows.
        self.assertEqual((key, policy.last_reason), ("9", "shop:approach"))
        self.assertFalse(policy._recall_stockout_mining_plan)
        post_unchanged(self, policy, raw, key)

    # The inherited scenarios belong to their own module.
    test_captured_rows = None
    test_churn_refused_recall_starts_the_recall_stockout_time_pass = None
    test_supply_stockout_owner_keeps_its_three_round_stop = None
    test_mining_return_ends_the_churn_scope_so_the_retry_buys = None
    test_control_an_offered_recall_without_churn_is_still_bought = None


class IdentificationCandidateEndsWithVisitTest(town_harness.RecordedTownPolicy,
                                               executor_harness.ProductionHarness):
    """n1-a life-466 (2026-11-02 23:18): the identification candidate.

    In town (decision 5129) the town-item owner bound the unknown robe as
    the identification candidate and requested a normal Identify source; on
    the next trip (5137) the game destroyed the robe.  DECLARED
    RECONSTRUCTED: those latches (need normal, candidate the robe, Home
    candidate waiting) on the trip's last board (constructed: the stop
    board's character on 5F of the Yeek cave).  The arrival on the recorded
    stop board ends the candidate with its request, before any departure
    gate, so no departure leaf waits for the robe.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = hourly_2300._cases()["identify"]

    def test_arrival_ends_the_last_visits_candidate_and_its_request(self):
        case = self.case
        stop = case["stop"]
        policy = self.primed(on_floor(stop, DUNGEON_YEEK_CAVE, 5),
                             case["home"]["knowledge"]["items"], case["skill"])
        robe = ("ローブ [2]", 36, 2)
        policy._identification_need = "normal"
        policy._identification_candidate = robe
        policy._home_candidate_waiting = True

        board = self.board(policy, stop)
        policy.prime(board)
        self.assertIsNone(policy._identification_candidate)
        self.assertIsNone(policy._identification_need)
        self.assertFalse(policy._home_candidate_waiting)
        key = policy.choose_key(board)
        # Recorded: '5' town:blocked:departure-unsatisfiable.  No departure
        # leaf waits for the robe; the new visit shops first (the store
        # latches ended with the last visit as well).
        self.assertEqual(policy._departure_block_state(board)["failed"], [])
        self.assertEqual((key, policy.last_reason), ("\x1b`n#.", "shop:travel"))
        self.assertIsNone(policy._identification_need)
        post_unchanged(self, policy, stop, key)


if __name__ == "__main__":
    import unittest
    unittest.main()
