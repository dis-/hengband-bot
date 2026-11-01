"""Town defined end: no owner answers -> depart or a named stop (2026-11-02).

Owner 2026-11-02 「決まった終わり方だけにする」: on a town board on which no
owner answers, the visit (1) departs when every departure condition holds,
(2) gives up unmet conditions outside the departure minimum by name and
departs, or (3) stops under town:blocked:survival:<leaf> when a minimum leaf
is unmet.  The dungeon wander fallbacks (breakout:least-visited,
stuck:wander) and the boxed-breakout store travel are not used in town; the
existing visit-closing stops (departure-unsatisfiable, the three-
retirement burst) keep their existing names.

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

import copy
import gzip
import json
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from hengbot import cli, me_capability, me_staff_sequence
from hengbot.model import STORE_HOME, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.runtime_paths import runtime_path
from tests.test_esp_threat_rest_recorded import EDIT, _policy
from tests.test_n1c_town_wander_1101_recorded import TownWanderRecordedTest


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


class TownDefinedEndHomeLoopTest(TownWanderRecordedTest):
    """The 23:50 Home loop board: the town fallback is never a wander."""

    test_recorded_loop = None
    test_errand_take_is_composed_at_the_entrance_and_the_visit_departs = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.recorded_case = _load(HOME_LOOP)

    def boundary(self):
        policy, raw = super(TownWanderRecordedTest, self).boundary()
        # DECLARED RECONSTRUCTED from the life's 22:04 policy-state.json, as
        # in the D61 test of the same life (string record keys there).
        sequence = self.case["me_staff_sequence"]
        record = me_staff_sequence.state(policy)
        record.absorbed = dict(sequence["absorbed"])
        record.absorbed[me_capability.record_key("wand", 6)] = 1
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

    def test_no_owner_drops_the_home_candidate_and_departs(self):
        from hengbot.town_terminal import gather_town_end, town_end_key, verdict_town_end
        policy, raw = self.boundary()
        # DECLARED RECONSTRUCTED from the decision log at 26099: every store
        # of the visit entered, Home's pass closed with its candidate still
        # waiting, and nothing on Home's shelf left to take this visit.
        for store_type in VISITED_STORES:
            policy._set_town_store_attempted(store_type, raw["turn"], "home:route-claim-unfulfilled")
        policy._deferred_home_items.update(
            policy._item_signature(item) for item in policy._home_knowledge_items)
        policy._home_candidate_waiting = True
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        end = verdict_town_end(gather_town_end(policy, board))
        self.assertEqual(end, ("drop-and-depart", ("home_candidate_resolved",)))
        key = town_end_key(policy, board)
        # The board is still on the Home entrance: the established step off
        # it comes first, then the forced departure reads the recall exactly
        # as the departure owner does.
        self.assertEqual(policy.last_reason, "town:entrance-step-off:town:end-step-off")
        self.assertIn(key, "12346789")
        following = self.reply(raw, key)
        self.post(policy, raw, key, following)
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(following), policy._monrace_knowledge))
        # DECLARED RECONSTRUCTED: the live latch persisted off the entrance
        # (departure_block at 26099 failed home_candidate_resolved there).
        policy._home_candidate_waiting = True
        key = town_end_key(policy, board)
        self.assertEqual(policy.last_reason, "town:repetition-depart:recall")
        self.assertEqual(policy._visit_departure_committed, "no-owner-answered")
        self.assertTrue(key.startswith("r"), key)
        record = [json.loads(line) for line in runtime_path(
            "keep-running-events.jsonl").read_text(encoding="utf-8").splitlines()][-1]
        self.assertEqual((record["cause"], record["outcome"]),
                         ("no-owner-answered", "forced_departure"))
        self.assertEqual(record["closed_work"]["dropped_conditions"],
                         ["home_candidate_resolved"])


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

    def test_burst_ends_by_its_named_stop(self):
        policy, board = self.boundary()
        # The departure minimum fails (no Recall carried): the burst cannot
        # depart and keeps its own named stop.
        self.assertEqual(policy._visit_departure_minimum(board)[0]["failed"][0],
                         "recall_departure_ready")
        # DECLARED RECONSTRUCTED: the visit's two forgiven retirements
        # (bot-stderr "continuing" rows); the third is labelled here.
        cli._observe_owner_retired_progress(policy, board, "5")
        policy._owner_retired_no_progress_count = cli.OWNER_RETIRED_LOG_ONLY_LIMIT - 1
        policy.last_reason = "town:blocked:owner-retired"
        args = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
        key = cli._handle_owner_retirement(args, board, "5", policy)
        self.assertEqual(policy.last_reason, "town:blocked:owner-retired-burst")
        self.assertTrue(cli._policy_final_stop_required(policy))
        self.assertEqual(key, "5")

    def test_no_owner_stops_under_the_unmet_survival_leaf(self):
        from hengbot.town_terminal import gather_town_end, town_end_key, verdict_town_end
        policy, board = self.boundary()
        end = verdict_town_end(gather_town_end(policy, board))
        self.assertEqual(end.kind, "stop")
        self.assertEqual(end.conditions[0], "recall_departure_ready")
        town_end_key(policy, board)
        self.assertEqual(policy.last_reason, SURVIVAL_STOP + end.conditions[0])
        self.assertTrue(cli._policy_final_stop_required(policy))
        self.assertIn("departure-minimum", cli._policy_final_stop_banner(policy.last_reason))


if __name__ == "__main__":
    unittest.main()
