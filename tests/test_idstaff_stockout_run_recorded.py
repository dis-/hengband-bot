"""D54: the recorded n1-a life-453 Identify-staff stock-out stop (2026-11-01 00:57).

The warrior (Lv26, 20,202 gold, build bot-f9c921d32) had bought the Magic
shop's last Identify staves: 16 of the 20 charges a 10F+ departure needs.
The Identify-staff stock-out time-pass ("one Yeek Cave 1F mining run, then
retry Home and Magic") descended at turn 885633 and the very next decision on
Yeek cave 1F was fundraise:ascend: the gold already exceeded the 15,000
fundraising target and no treasure was known yet, so the gold return fired
on the arrival board.  A shelf restocks only after 10,000 game turns
(store/cmd-store.cpp:94, STORE_TICKS), so the next visit found Magic sold
out again.  The Black Market's page of the earlier visit (turn 883949, within
its retry window) made the need registry skip that stop, while
_identify_staff_procurement_impossible still waited for the Black Market to
be attempted or observed in this visit; no owner was left and the visit
stopped with departure_block.failed ["identify_staff_ready"] three times.

Root 1 (stop board): a supplier the need registry skips on its shelf
evidence counts as tried (policy_instore._shelf_stop_tried), so the stock-out
run is installed again.  Root 2 (Yeek board): a restock time-pass is not
ended by the gold target (policy_fundraising._restock_time_pass_run, the D35
rule of the Magic-Eater's stock-out run).

The stop board test attaches the recorded visit to the established harness
of tests/test_unid_deposit_recorded.py (DECLARED RECONSTRUCTED boundary; the
earlier Black Market page is filed as this process's shelf evidence, as the
recorded process had observed it).  The Yeek board test builds the dungeon
policy as tests/test_me_stockout_run_recorded.py does (DECLARED
RECONSTRUCTED: the town decision's stock-out plan, the mining mode the
departure sets and the cross-area purpose it posts).  Every key comes from
the public chooser and goes through the production executor; the replies are
constructed.  Fixture: tests/extract_idstaff_stockout_run_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from pathlib import Path

from hengbot.cli import _ExecutorInputPort, SendResult, _transport_key
from hengbot.model import STORE_BLACK, parse_snapshot
from hengbot.policy_fundraising import (
    FundraisingPurpose, FundraisingPurposeRecord, FundraisingTransportChild,
    fundraising_run_verdict,
)
from tests.support.recorded import _policy
import tests.test_unid_deposit_recorded as recorded
from tests.support.recorded import FaithfulHookGame, command_screen


FIXTURE = Path(__file__).with_name("fixtures") / "idstaff-stockout-run-20261101.json.gz"
STOCKOUT = "town:identify-staff-stockout-mining"


class IdstaffStockoutRunRecordedTest(recorded.UnidentifiedDepositRecordedTest):
    fixture = FIXTURE

    def boundary(self):
        policy, raw = super().boundary()
        # DECLARED RECONSTRUCTED: the recorded process observed the Black
        # Market's page at 883949 (no Identify staff within gold) and kept it
        # as the shelf evidence its planner read (decision 1545,
        # shelf_evidence_skips store 6 identify-staff).
        page = parse_snapshot(copy.deepcopy(self.case["earlier_black_market"]),
                              policy._monrace_knowledge)
        policy._observe_shelf_evidence(page)
        return policy, raw

    def test_recorded_stop(self):
        decision = self.case["decision"]
        self.assertEqual((decision["turn"], decision["reason"], decision["key"]),
                         (886291, "town:blocked:departure-unsatisfiable", "9"))
        self.assertEqual(decision["departure_block"]["failed"], ["identify_staff_ready"])
        self.assertEqual(decision["procurement_requirements"],
                         [{"item": "Identify staff charges", "current": 16, "target": 20,
                           "missing": 4}])
        descend, ascend = self.case["yeek_decisions"]
        self.assertEqual((descend["turn"], descend["reason"]), (885633, "descend"))
        self.assertEqual((ascend["turn"], ascend["reason"], ascend["key"]),
                         (885634, "fundraise:ascend", "<"))
        self.assertEqual(ascend["fundraising"]["planned_runs"], 1)
        self.assertEqual(ascend["player"]["gold"], 20202)
        self.assertEqual(ascend["mining"]["collected"], 0)
        self.assertEqual(self.case["earlier_black_market"]["store"]["store_type"], STORE_BLACK)
        policy, raw = self.boundary()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(policy._total_identify_staff_charges(board), 16)
        self.assertTrue(policy._home_knowledge_current)

    def test_stop_board_installs_the_stockout_run_again(self):
        policy, raw = self.boundary()
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        key = str(policy.choose_key(board))
        self.assertFalse(policy.last_reason.startswith("town:blocked:"), policy.last_reason)
        self.assertTrue(policy.last_reason.endswith(STOCKOUT), policy.last_reason)
        self.assertTrue(policy._identify_staff_mining_plan)
        self.assertEqual((policy._fundraising_mode, policy._planned_mining_runs), ("prepare", 1))
        self.post(policy, raw, key, self.reply(raw, key))

    # ------------------------------------------------------------ Yeek 1F
    def dungeon_policy(self):
        raw = copy.deepcopy(self.case["yeek_board"])
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        policy._in_store_ops_enabled = True
        policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        # DECLARED RECONSTRUCTED (module docstring): the stock-out plan of
        # _identify_staff_stockout_key and the departure's mining mode and
        # cross-area purpose (fundraising mine, one planned run, none done).
        policy._identify_staff_mining_plan = True
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs, policy._mining_runs_completed = 1, 0
        policy._fundraising_runs_started = 1
        purpose = FundraisingPurpose(1, "mine", False)
        policy._fundraising_run_purpose = purpose
        policy._fundraising_purpose_record = FundraisingPurposeRecord(
            purpose, child=FundraisingTransportChild(
                purpose.identity, "depart", (0, 0, 0), 1, state="complete"))
        # As the stop board's harness: this process has read the skill list.
        policy._skill_exp_cache = (0, 0, raw["player"]["level"], policy._town_visit_epoch)
        return policy, raw

    def post_dungeon_key(self, policy, raw, key):
        """DECLARED CONSTRUCTED: the board unchanged, ten game turns later."""
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), _transport_key(key, True))

    def test_stockout_run_mines_instead_of_returning_on_the_gold_target(self):
        policy, raw = self.dungeon_policy()
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        self.assertGreater(board.player.gold, policy._fundraising_gold_target())
        key = str(policy.choose_key(board))
        # The run stays on the floor: the arrival board's first decision walks
        # off the stairs while the mining loadout's quiet streak builds
        # (fundraise:wield-digger), instead of fundraise:ascend.
        self.assertNotEqual((policy.last_reason, key), ("fundraise:ascend", "<"))
        self.assertFalse(policy._returning_to_town)
        verdict = fundraising_run_verdict(policy._fundraising_facts(board),
                                          policy._fundraising_run_purpose)
        self.assertEqual((verdict.must_return, verdict.may_continue), (False, True))
        self.post_dungeon_key(policy, raw, key)

    # The inherited Identify-staff scenarios belong to the life-427 fixture.
    test_shelved_equipment_is_taken_back_and_identified_with_a_source = None
    test_waiting_equipment_is_shelved_and_the_staff_bought = None


if __name__ == "__main__":
    import unittest
    unittest.main()
