"""Town defined end: no owner answers -> depart, mine once, or a named stop.

Owner 2026-11-02 「決まった終わり方だけにする」 and 「満たせなければ採掘を
1サイクル行い再度トライ。条件未達の出発は拒否する。」: on a town board on
which no owner answers, the visit (1) departs when every departure condition
holds, (2) with a condition unmet starts one mining cycle through the
fundraising owners (town_end_mining) and retries the conditions, never
departing with them unmet, or (3) stops under town:blocked:survival:<leaf>
(a departure-minimum leaf) or town:blocked:unmet:<name> when that cycle
cannot leave.  The dungeon wander fallbacks (breakout:least-visited,
stuck:wander) and the boxed-breakout store travel are not used in town; the
existing visit-closing stops (departure-unsatisfiable, the three-
retirement burst) keep their existing names.
Owner 2026-11-02 「購入に関する問題以外は採掘せずに名前を付けて停止を採用」:
the mining cycle is only for purchase gaps (a supply the seen shelves sell
above the carried gold); any other unmet condition stops by its name.
Owner 2026-09-13 「鑑定待ちでも止めない」, 2026-11-03 (鑑定できない訪問なら今の
装備で出発): an identification wait this visit cannot finish is no such
condition (identification_wait); it is released first, and every other
condition still decides.  The recorded latch is that wait (the visit's ledger
counted nine identification-withdrawal attempts), so the named stop is pinned
with a Home transfer in flight, which the release leaves to its owner.

Recorded boards (fixtures: tests/extract_town_defined_end_1102_fixtures.py):

- n1-c life-098, Outpost 2026-11-01 23:50 (Magic-Eater Lv26, the D61 build).
  After every Home pass closed as home:route-claim-unfulfilled the dungeon
  fallback breakout:least-visited won and the progress seam rewrote it into
  travel back to Home (decisions 26086-26101), once a second until the
  loop-detected stop.  Departure failed home_candidate_resolved alone.
  The test attaches the visit to the established static-game policy helper
  (tests/test_unid_deposit_recorded.py, DECLARED RECONSTRUCTED boundary,
  DECLARED CONSTRUCTED replies); every key comes from the public chooser
  and goes through the production executor.
- n1-b life-283, Outpost 2026-10-31 23:34 (a new warrior waiting for the
  General Store's restock; no Recall, food, cure or teleport carried): the
  third retirement without progress stopped it as owner-retired-burst
  (keep-running hard_stop, the departure minimum failed).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from contextlib import redirect_stdout
import copy
import gzip
import io
import json
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from tests.support import item_use_route_wall
from unittest import mock

from hengbot import heroism_potion
from hengbot import cli, departure_rescues, me_capability, me_staff_sequence, town_end_mining
from hengbot.model import STORE_ALCHEMIST, STORE_HOME, STORE_TEMPLE, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.runtime_paths import runtime_path
from tests.support.recorded import EDIT, _policy
from hengbot.town_terminal import gather_town_end, town_end_key, verdict_town_end
from tests import test_n1c_town_wander_1101_recorded as _test_n1c_town_wander_1101_recorded


FIXTURES = Path(__file__).with_name("fixtures")
HOME_LOOP = FIXTURES / "town-defined-end-home-loop-2350.json.gz"
RETIRED_BURST = FIXTURES / "town-defined-end-retired-burst-2334.json.gz"
WANDER = ("breakout:", "stuck:wander", "boxed-breakout-travel")
SURVIVAL_STOP = "town:blocked:survival:"
# The stores the recorded visit had entered before the board (decision
# 26099 departure_block.town_ledger.store_visits).
VISITED_STORES = (7, 4, 2, 6, 5, 0)
HOME_PAGE_ROWS = 52


def _load(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def _wanders(reasons):
    return [reason for reason in reasons if any(label in reason for label in WANDER)]


class TownDefinedEndHomeLoopTest(_test_n1c_town_wander_1101_recorded.TownWanderRecordedTest):
    """The 23:50 Home loop board: the town fallback is never a wander."""

    test_recorded_loop = None
    test_errand_take_is_composed_at_the_entrance_and_the_visit_departs = None

    def setUp(self):
        super().setUp()
        item_use_route_wall.hold(self)  # wall, declared: tests/support/item_use_route_wall.py

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.recorded_case = _load(HOME_LOOP)

    def boundary(self):
        policy, raw = super(_test_n1c_town_wander_1101_recorded.TownWanderRecordedTest, self).boundary()
        # DECLARED RECONSTRUCTED from the life's 22:04 policy-state.json, as
        # in the D61 test of the same life (string record keys there).
        sequence = self.case["me_staff_sequence"]
        record = me_staff_sequence.state(policy)
        record.absorbed = dict(sequence["absorbed"])
        # The carried Stone to Mud kind at the count cap, so its Tower trip
        # (owner 2026-11-07: copies below the cap are absorbed) stays out.
        record.absorbed[me_capability.record_key("wand", 6)] = 99
        record.stage = sequence["stage"]
        record.powers_read = True
        return policy, raw

    def home_reply(self, following, page, body):
        """DECLARED CONSTRUCTED: the recorded Home page lists 52 of its 169
        stacks; a deposit lands beyond the listed page."""
        deposits = len(re.findall(r"d[a-zA-Z]", body))
        if len(page["items"]) + deposits > HOME_PAGE_ROWS:
            del page["items"][HOME_PAGE_ROWS - deposits:]
        return super().home_reply(following, page, body)

    def step(self, policy, raw):
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        policy.observe_store_screen(board.store is not None)
        key, reason = str(policy.choose_key(board)), policy.last_reason
        following = self.reply(raw, key)
        self.post(policy, raw, key, following)
        return following, key, reason

    def test_recorded_wander_loop(self):
        decisions = {row["decision_sequence"]: row for row in self.case["decisions"]}
        self.assertEqual(decisions[26098]["reason"], "home:route-claim-unfulfilled")
        self.assertEqual(decisions[26099]["reason"], "breakout:least-visited")
        self.assertEqual(decisions[26100]["reason"],
                         "town-progress-invariant:boxed-breakout-travel")
        self.assertEqual(decisions[26099]["departure_block"]["failed"],
                         ["home_candidate_resolved"])

    # DECLARED WALL (2026-11-11): the Heroism stock (heroism_potion, owner 2026-11-11) postdates this
    # recording; with it the character also files the Temple errand and keeps its carried potion, so
    # the recorded route is pinned with no stock wanted.
    @mock.patch.object(heroism_potion, "carry_target", lambda snapshot: 0)
    def test_town_fallback_never_wanders(self):
        policy, raw = self.boundary()
        # DECLARED RECONSTRUCTED: the visit's Home pass had closed as
        # home:route-claim-unfulfilled (decision 26098) and latched Home.
        policy._set_town_store_attempted(STORE_HOME, raw["turn"], "home:route-claim-unfulfilled")
        reasons = []
        for _ in range(4):
            raw, key, reason = self.step(policy, raw)
            reasons.append(reason)
            self.assertTrue(key, reasons)
        # The fallback's turn (the third decision) is the store router's
        # composed progress, not a wander for the seam to rewrite.
        self.assertFalse(_wanders(reasons), reasons)
        self.assertEqual(reasons[2], "town-progress-invariant:approach", reasons)

    def unanswered_board(self):
        """The 26099 board off the Home entrance, every owner exhausted."""
        policy, raw = self.boundary()
        policy._town_end_mining_path = runtime_path("town-end-mining.json")
        # DECLARED RECONSTRUCTED from the decision log at 26099: every store
        # of the visit entered, Home's pass closed with its candidate still
        # waiting, and nothing on Home's shelf left to take this visit.
        for store_type in VISITED_STORES:
            policy._set_town_store_attempted(store_type, raw["turn"], "home:route-claim-unfulfilled")
        policy._deferred_home_items.update(
            policy._item_signature(item) for item in policy._home_knowledge_items)
        policy._home_candidate_waiting = True
        key = town_end_key(policy, self.board(policy, raw))
        # The board is still on the Home entrance: the established step off
        # it comes first.
        self.assertEqual(policy.last_reason, "town:entrance-step-off:town:end-step-off")
        self.assertIn(key, "12346789")
        following = self.reply(raw, key)
        self.post(policy, raw, key, following)
        # DECLARED RECONSTRUCTED: the live latch persisted off the entrance
        # (departure_block at 26099 failed home_candidate_resolved there).
        policy._home_candidate_waiting = True
        return policy, following

    @staticmethod
    def board(policy, raw):
        return policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))

    def purchase_gap_board(self):
        """DECLARED CONSTRUCTED: the unanswered board with a purchase gap.

        Home's candidate is resolved, one Word of Recall is carried and the
        gold (100) is below the Recall price the visit's Alchemist page
        showed (239): Recall is short only because gold is.
        """
        policy, raw = self.unanswered_board()
        policy._home_candidate_waiting = False
        raw = copy.deepcopy(raw)
        raw["player"]["gold"] = 100
        recall = next(item for item in raw["inventory"] if item["tval"] == 70 and item["sval"] == 11)
        recall["count"] = 1
        return policy, raw

    @staticmethod
    def transfer_in_flight(policy):
        """DECLARED CONSTRUCTED: a Home transfer no release may take away."""
        policy._home_pending_item = policy._item_signature(policy._home_knowledge_items[0])

    def test_identification_wait_the_visit_cannot_finish_departs(self):
        policy, raw = self.unanswered_board()
        board = self.board(policy, raw)
        # Nothing but the wait is unmet, and no survival condition.
        material = gather_town_end(policy, board)
        self.assertEqual((material.survival_unmet, material.unmet),
                         ((), ("home_candidate_resolved",)))
        key = town_end_key(policy, board)
        self.assertEqual(policy.last_reason, "town:repetition-depart:recall")
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertTrue(key.startswith("r" + recall.slot), key)
        self.assertFalse(policy._home_candidate_waiting)
        self.assertEqual(verdict_town_end(gather_town_end(policy, board)), ("depart", ()))

    def test_purchase_gap_beside_an_identification_wait_mines_and_never_departs(self):
        policy, raw = self.purchase_gap_board()
        policy._home_candidate_waiting = True
        board = self.board(policy, raw)
        key = town_end_key(policy, board)
        # 「条件未達の出発は拒否する」: the wait goes, the unmet Recall stays.
        self.assertEqual((key, policy.last_reason), ("5", town_end_mining.START_REASON))
        self.assertIsNone(policy._visit_departure_committed)
        self.assertEqual(policy._town_end_mining_cycle.unmet, ("recall_departure_ready",))

    def test_non_purchase_condition_stops_by_name_without_mining(self):
        policy, raw = self.unanswered_board()
        self.transfer_in_flight(policy)
        board = self.board(policy, raw)
        # Owner 2026-11-02 「購入に関する問題以外は採掘せずに名前を付けて停止」.
        end = verdict_town_end(gather_town_end(policy, board))
        self.assertEqual((end.kind, end.conditions[0]), ("stop", "home_candidate_resolved"))
        self.assertIn("home_pending_item_clear", end.conditions)
        events = runtime_path("keep-running-events.jsonl")
        before = events.read_text(encoding="utf-8") if events.exists() else ""
        town_end_key(policy, board)
        self.assertEqual(policy.last_reason, "town:blocked:unmet:home_candidate_resolved")
        self.assertTrue(cli._policy_final_stop_required(policy), policy.last_reason)
        self.assertIsNone(policy._fundraising_mode)
        self.assertIsNone(policy._town_end_mining_cycle)
        self.assertEqual(events.read_text(encoding="utf-8") if events.exists() else "", before)

    def test_purchase_gap_starts_one_mining_cycle(self):
        policy, raw = self.purchase_gap_board()
        board = self.board(policy, raw)
        end = verdict_town_end(gather_town_end(policy, board))
        self.assertEqual(end, ("mine", ("recall_departure_ready",)))
        key = town_end_key(policy, board)
        # No departure with the condition unmet: one mining cycle opens in
        # the fundraising owners' preparation.
        self.assertEqual((key, policy.last_reason), ("5", town_end_mining.START_REASON))
        self.assertIsNone(policy._visit_departure_committed)
        self.assertEqual((policy._fundraising_mode, policy._planned_mining_runs), ("prepare", 1))
        self.assertEqual(policy._town_end_mining_cycle, town_end_mining.TownEndMiningCycle(
            ("recall_departure_ready",), 1, raw["turn"], "town", policy._town_visit_epoch))
        stored = json.loads(policy._town_end_mining_path.read_text(encoding="utf-8"))
        self.assertEqual((stored["unmet"], stored["stage"]), (["recall_departure_ready"], "town"))
        record = [json.loads(line) for line in runtime_path(
            "keep-running-events.jsonl").read_text(encoding="utf-8").splitlines()][-1]
        self.assertEqual((record["cause"], record["outcome"]), ("no-owner-answered", "mining_cycle"))
        self.assertEqual(record["closed_work"]["unmet"], ["recall_departure_ready"])

    def test_purchase_gap_beside_a_defect_stops_on_the_defect(self):
        policy, raw = self.purchase_gap_board()
        policy._home_candidate_waiting = True
        self.transfer_in_flight(policy)
        board = self.board(policy, raw)
        end = verdict_town_end(gather_town_end(policy, board))
        self.assertEqual((end.kind, end.conditions[0]), ("stop", "home_candidate_resolved"))
        self.assertIn("home_pending_item_clear", end.conditions)
        town_end_key(policy, board)
        self.assertEqual(policy.last_reason, "town:blocked:unmet:home_candidate_resolved")
        self.assertIsNone(policy._fundraising_mode)

    def test_cycle_survives_a_restart_and_retries_after_its_run(self):
        policy, raw = self.purchase_gap_board()
        board = self.board(policy, raw)
        town_end_key(policy, board)
        # A restarted process restores the open cycle from the record.
        restarted, _ = self.boundary()
        restarted._town_end_mining_path = policy._town_end_mining_path
        town_end_mining.carry(restarted, board, True)
        self.assertEqual(restarted._town_end_mining_cycle, policy._town_end_mining_cycle)
        self.assertEqual((restarted._fundraising_mode, restarted._planned_mining_runs),
                         ("prepare", 1))
        # DECLARED CONSTRUCTED: the cycle's run on Yeek Cave 1F and its return.
        policy._fundraising_mode = "mine"
        town_end_mining.finish_run(policy, board)
        self.assertIsNone(policy._fundraising_mode)
        self.assertEqual(policy._town_end_mining_cycle.stage, "returned")
        # The return's town floor change clears the visit's departure record
        # (policy_observation); the same unmet condition starts the next
        # cycle, with no cap.
        policy._visit_departure_recorded.clear()
        self.assertEqual(town_end_key(policy, board), "5")
        self.assertEqual(policy.last_reason, town_end_mining.START_REASON)
        self.assertEqual(policy._town_end_mining_cycle.cycles, 2)
        # While its set is open and no owner answers, the cycle that cannot
        # leave stops by name instead of opening another one.
        policy._visit_departure_recorded.clear()
        town_end_key(policy, board)
        self.assertTrue(policy.last_reason.startswith("town:blocked:"), policy.last_reason)
        self.assertTrue(cli._policy_final_stop_required(policy), policy.last_reason)


class TownDefinedEndRetiredBurstTest(unittest.TestCase):
    """The 23:34 burst board: a named stop when the survival minimum fails."""

    @classmethod
    def setUpClass(cls):
        cls.case = _load(RETIRED_BURST)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def boundary(self):
        policy = _policy(Path(tempfile.mkdtemp()), self.monrace)
        raw = copy.deepcopy(self.case["board"])
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        policy.prime(board)
        policy._skill_exp_cache = (0, 0, raw["player"]["level"], policy._town_visit_epoch)
        return policy, policy.with_known_skill_exp(board)

    def test_recorded_stop(self):
        reasons = [row["reason"] for row in self.case["decisions"]]
        self.assertEqual(reasons[-1], "town:blocked:owner-retired-burst")
        self.assertEqual(set(reasons[:-1]), {"town:wait-restock:general"})
        self.assertTrue(self.case["retirements"][-1].endswith("stopping"))

    def test_the_third_retirement_no_longer_stops_the_visit(self):
        """Town rebuild 3-5 (owner 2026-11-12): the recorded third retirement
        stopped this visit as owner-retired-burst; it is now forgiven, and the
        visit's stage deadlines (town_visit_plan.STAGE_DEADLINES) bound it."""
        policy, board = self.boundary()
        self.assertEqual(policy._visit_departure_minimum(board)[0]["failed"][0],
                         "recall_departure_ready")
        # DECLARED RECONSTRUCTED: the visit's two forgiven retirements
        # (bot-stderr "continuing" rows); the third is labelled here.
        cli._observe_owner_retired_progress(policy, board, "5")
        policy._owner_retired_no_progress_count = 2
        policy.last_reason = "town:blocked:owner-retired"
        args = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
        key = cli._handle_owner_retirement(args, board, "5", policy)
        self.assertEqual(policy._owner_retired_no_progress_count, 3)
        self.assertFalse(cli._policy_final_stop_required(policy))
        self.assertEqual(key, "5")

    def test_no_owner_stops_under_the_unmet_survival_leaf(self):
        policy, board = self.boundary()
        # The opening Q34 still buys its torches (decisions: wait-restock
        # general): no mining cycle can start.
        self.assertTrue(policy._opening_q34_holds_fundraising(board))
        end = verdict_town_end(gather_town_end(policy, board))
        self.assertEqual(end.kind, "stop")
        self.assertEqual(end.conditions[0], "recall_departure_ready")
        # Town rebuild stage 2 (owner 2026-11-12): the leaf's rescue walks to
        # a Recall supplier this visit has not tried before the named stop.
        with redirect_stdout(io.StringIO()):
            town_end_key(policy, board)
        self.assertEqual(policy.last_reason, "shop:travel")
        self.assertEqual(policy._departure_rescue_last, ("recall_departure_ready", "supplier-visit"))
        self.assertIn(policy._shopping_approach_store_type, (STORE_TEMPLE, STORE_ALCHEMIST))
        # Once every rescue is spent, the unmet minimum leaf stops by name.
        with mock.patch.dict(departure_rescues.ACTIONS, {name: (lambda *_args: None)
                                                    for name in departure_rescues.ACTIONS}):
            policy._decision_sequence += 5
            town_end_key(policy, board)
        self.assertEqual(policy.last_reason, SURVIVAL_STOP + end.conditions[0])
        self.assertTrue(cli._policy_final_stop_required(policy))
        self.assertIn("departure-minimum", cli._policy_final_stop_banner(policy.last_reason))


if __name__ == "__main__":
    unittest.main()
