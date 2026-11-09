"""n1-b life-322 (2026-11-06 02:37-02:43, Yeek cave 1F): a mining walk-out sealed in.

A floating eye woke beside the digging player, and the Teleportation landed in the
walled western rooms.  The only way back is a corridor past the eye, so its ring leaves
no walking route to the three known up staircases; exploration has nothing left.
No Recall is carried: this run walked in.  The floor exit of the income run
(``_leave_fundraising_floor``) then wandered for 2,500 decisions, waited and searched,
under the owner's 「掘って進む」 (2026-11-02): the walk-out dig was asked only by the
latched return's owner, and its gate required the latch.  A restart ended it, by
forgetting the eye's cells.  Owner 2026-11-06:
「採掘中に困ったら掘って解決すると決めたが無視されている」.

Now the floor exit digs (rung ``_fundraising_key#1``, walkout_dig), by the route with the
fewest tunnelled cells: over the mapped corridor and round the trap and the ring.
A digger-less walker keeps its wander, and the wander no longer starves the no-progress
bound that sits below this owner in the ladder.
Fixture: tests/extract_n1b_322_walkout_dig_1106_fixture.py.
DECLARED RECONSTRUCTED: terrain, modes and ledger are the 02:43 stop capture's values,
laid over the eye's board (the terrain only grows on this floor).
DECLARED CONSTRUCTED: the run's purpose record (a process value, not in any capture), the
board without its diggers, and the no-progress latch of the livelock pin.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _send_new_decision_key, _transport_key,
)
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import STUCK_WINDOW, TUNNEL_KEY
from hengbot.policy_fundraising import (
    FundraisingPurpose, FundraisingPurposeRecord, FundraisingTransportChild,
)
from recorded_junk_scope import choose_past_junk_key
from tests.support.recorded import EDIT, _policy
from tests import test_input_executor as executor_pins


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-322-walkout-dig-1106.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
# hengbot.policy_constants.RETURN_DIG_UPSTAIRS_REASON, spelled out so the revert check
# runs every test instead of an import error.
DIG_UPSTAIRS = "return:dig-to-upstairs"
WANDER = "fundraise:seek-upstairs-wander"
TVAL_DIGGING = 20  # TV_DIGGING (object/tval-types.h)
EYE_CELL = Position(5, 60)
TRAP_CELL = Position(3, 29)
ROUND_THE_TRAP = TUNNEL_KEY + "9"  # (3,28) -> (2,29), the corner past the trap to (3,30)


class MiningWalkOutDigTest(executor_pins.ProductionHarness):

    def policy(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        policy = _policy(Path(directory.name), monrace)
        eye = CASE["eye_board"]
        policy.prime(parse_snapshot(copy.deepcopy(eye), monrace))
        policy.consume_skill_knowledge(
            {**CASE["skill"], "player": {"level": eye["player"]["level"]}})
        for name, value in CASE["modes"].items():
            setattr(policy, name, value)
        purpose = FundraisingPurpose(1, "mine", False)
        policy._fundraising_run_purpose = purpose
        policy._fundraising_purpose_record = FundraisingPurposeRecord(
            purpose,
            child=FundraisingTransportChild(1, "depart", (0, 0, 0), 1, state="complete"),
        )
        # The eye's own board: the ring, and the grids the decision board remembers.
        key = policy.choose_key(self.board(policy, eye))
        self.assertEqual((key, policy.last_reason), ("re", "status-threat:scroll"))
        policy.confirm_key_posted(key)
        terrain = CASE["terrain"]
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in terrain[f"{name}_t"])
        policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
        ledger = policy._exploration_ledger
        recorded = CASE["ledger"]
        ledger.probed_frontiers.update(Position(*cell) for cell in recorded["probed_frontiers"])
        for y, x, value in recorded["visit_counts"]:
            ledger.visit_counts[Position(y, x)] = value
        for y, x, value in recorded["search_counts"]:
            ledger.search_counts[(y, x)] = value
        for y, x, value in recorded["wall_search_counts"]:
            ledger.wall_search_counts[(y, x)] = value
        ledger.mapped_areas.update(tuple(area) for area in recorded["mapped_areas"])
        return policy

    @staticmethod
    def board(policy, raw):
        return policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))

    def decide(self, policy, raw):
        board = self.board(policy, raw)
        return board, choose_past_junk_key(policy, board)

    def post(self, policy, board, raw, key):
        """Send ``key`` through the production executor; the turn passes."""
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.command_screen(raw["turn"] + 10)]
        # DECLARED CONSTRUCTED: the command spent one player turn.
        game.states = [dict(copy.deepcopy(raw), turn=raw["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract(),
        )
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual("".join(game.accepted), _transport_key(key, True))
        self.assertEqual(port.last_result.outcome, "completed")
        policy.confirm_key_posted(key)

    def test_recorded_rows_wandered_with_no_route_and_a_digger_in_hand(self):
        recorded = {row["turn"]: row for row in CASE["decisions"]}
        self.assertEqual(recorded[CASE["wander_board"]["turn"]]["reason"], WANDER)
        self.assertEqual(recorded[CASE["beside_trap_board"]["turn"]]["reason"],
                         "fundraise:upstairs-not-found")
        self.assertEqual(recorded[CASE["wander_board"]["turn"]]["rung"], "_fundraising_key#1")
        self.assertEqual(sorted(map(tuple, CASE["terrain"]["upstairs"])),
                         [(4, 89), (7, 73), (12, 75)])
        self.assertFalse(CASE["modes"]["_returning_to_town"])
        raw = CASE["wander_board"]
        self.assertEqual(sum(item["tval"] == TVAL_DIGGING for item in raw["equipment"]), 2)
        self.assertFalse(any(item["sval"] == 11 and item["tval"] == 70
                             for item in raw["inventory"]))  # no Word of Recall
        policy = self.policy()
        board = self.board(policy, raw)
        self.decide(policy, raw)
        self.assertIn(EYE_CELL, policy._engagement_avoid_cells)
        self.assertIsNone(policy._nearest_goal_step(board, policy._is_upstairs_target))
        self.assertIsNone(policy._explore_step(board))

    def test_the_walker_goes_to_the_dig_not_the_wander(self):
        raw = CASE["wander_board"]
        policy = self.policy()
        board, key = self.decide(policy, raw)
        self.assertEqual(policy.last_reason, DIG_UPSTAIRS)
        self.assertNotEqual(policy.last_reason, WANDER)
        self.assertFalse(key.startswith(TUNNEL_KEY))  # the floor and corridor come first
        self.post(policy, board, raw, key)

    def test_beside_the_trap_the_dig_goes_round_it(self):
        raw = CASE["beside_trap_board"]
        policy = self.policy()
        board, key = self.decide(policy, raw)
        self.assertTrue(board.grids[TRAP_CELL].trap)
        self.assertEqual((key, policy.last_reason), (ROUND_THE_TRAP, DIG_UPSTAIRS))
        self.post(policy, board, raw, key)

    def test_the_dig_holds_its_cell_past_the_oscillation_window(self):
        raw = CASE["beside_trap_board"]
        policy = self.policy()
        board, key = self.decide(policy, raw)
        for _ in range(STUCK_WINDOW + 1):
            self.assertEqual((key, policy.last_reason), (ROUND_THE_TRAP, DIG_UPSTAIRS))
            policy.confirm_key_posted(key)
            again = copy.deepcopy(raw)
            again["turn"] = raw["turn"] = raw["turn"] + 10
            _board, key = self.decide(policy, again)
        self.assertTrue(policy._is_oscillating())
        self.assertEqual((key, policy.last_reason), (ROUND_THE_TRAP, DIG_UPSTAIRS))

    def test_without_a_digger_the_walker_still_wanders(self):
        raw = copy.deepcopy(CASE["wander_board"])
        raw["equipment"] = [item for item in raw["equipment"]
                            if item["tval"] != TVAL_DIGGING]
        policy = self.policy()
        _board, key = self.decide(policy, raw)
        self.assertEqual(policy.last_reason, WANDER)
        self.assertFalse(key.startswith(TUNNEL_KEY))

    def test_no_progress_bound_reaches_the_walker_below_this_owner(self):
        raw = CASE["wander_board"]
        policy = self.policy()
        policy._nav_exhausted = True
        policy._window_edge_fallback_pending = False
        _board, _key = self.decide(policy, raw)
        self.assertEqual(policy.last_reason, "livelock:teleport-explore")


if __name__ == "__main__":
    import unittest
    unittest.main()
