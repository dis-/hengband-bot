"""Town owner-retired-burst visits of 2026-11-02 (04:47).

Recorded boards (fixtures: tests/extract_home_loops_0446_fixtures.py).  The
tests attach each board to the established static-game policy helper
(tests/test_unid_deposit_recorded.py, DECLARED RECONSTRUCTED: the arrival
board primes it and the visit's observed pages and answers are consumed
through the production response consumer); every key comes from the public
chooser and goes through the production executor, and the driver's own
retirement entrance (cli._handle_owner_retirement, --owner-retired-log-only
as on the viewing bots) settles each decision.

- n1-b life-291, Outpost 04:47 (Lv26 warrior, bot-ff4196953, a restarted
  process).  Home holds a known Elven Robe waiting for *Identify* and no
  *Identify* source is carried.  The catalogued take
  (_bind_catalogued_home_identification_withdrawal) needs a carried source,
  so no Home producer could act, but the Home catalogue claim
  (_has_actionable_incomplete_home_item) still counted the robe: every Home
  pass closed as home:route-claim-unfulfilled until the pass bound blocked
  Home for the visit.  The no-safe-destination fundraising set then found
  its Treasure Detection on Home's shelf behind that block: the depth gate
  held the visit until the burst (decisions 5, 9-18).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

from hengbot import cli
from hengbot.model import parse_snapshot
from hengbot.policy_constants import STORE_HOME
import tests.test_unid_deposit_recorded as recorded


FIXTURES = Path(__file__).with_name("fixtures")
FUNDRAISE_PLAN = FIXTURES / "home-loops-0446-fundraise-plan.json.gz"
BURST = "town:blocked:owner-retired-burst"


def _load(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class BurstVisitRecordedTest(recorded.UnidentifiedDepositRecordedTest):
    """One recorded burst visit driven through the chooser and the driver."""

    fixture_path = None

    # The inherited life-427 scenarios belong to their own fixture.
    test_recorded_stop = None
    test_waiting_equipment_is_shelved_and_the_staff_bought = None
    test_shelved_equipment_is_taken_back_and_identified_with_a_source = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.case = _load(cls.fixture_path)

    def setUp(self):
        super().setUp()
        self.unprogressed = []
        # The replies answer a later entry with the page that visit observed.
        for row in self.case["replies"]:
            self.pages.setdefault(row["store"]["store_type"], copy.deepcopy(row["store"]))

    def post(self, policy, raw, key, following):
        if key.startswith("~9") and raw.get("store") is not None:
            # The open Home page asks the same ~9 list (recorded live screens).
            live = FIXTURES / "live-screens"
            menu, viewer = (json.loads((live / name).read_text(encoding="utf-8"))["result"]
                            for name in ("27-knowledge-menu-after-viewer-esc-20260915.json",
                                         "26-knowledge-viewer-stuck-20260915-0534.json"))
            return self.execute(policy, raw, key, following, [menu, viewer, menu],
                                [raw] * 3, ["~", "9", "\x1b", "\x1b"])
        return super().post(policy, raw, key, following)

    def home_items(self):
        return [{k: v for k, v in item.items() if k != "letter"}
                for item in self.pages[STORE_HOME]["items"]]

    def run_visit(self, policy, raw, *, limit, done):
        """Drive the visit; the driver settles each decision's retirements."""
        args = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
        reasons = []
        for _ in range(limit):
            # DECLARED CONSTRUCTED: the bookkeeping fillers (save, dump) are
            # outside this harness's screens.
            policy._periodic_dump_requested = policy._periodic_save_requested = False
            board = policy.with_known_skill_exp(
                parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            # As the driver: the visit as it stood before the decision.
            emit_visit = copy.copy(policy._store_visit)
            policy.observe_store_screen(board.store is not None)
            key = policy.validate_read_key(board, policy.choose_key(board))
            key = cli._handle_owner_retirement(args, board, key, policy, emit_visit)
            reasons.append(policy.last_reason)
            self.unprogressed.append(policy._owner_retired_no_progress_count)
            if done(policy, board, key):
                return raw, reasons
            self.assertFalse(policy.last_reason.startswith("town:blocked:"), reasons[-12:])
            self.assertTrue(key, reasons[-12:])
            following = self.reply(raw, key)
            self.post(policy, raw, key, following)
            raw = following
            if key.startswith("~9"):
                # DECLARED CONSTRUCTED: the ~9 Home list of the current shelf.
                answer = copy.deepcopy(self.case["home_answer"])
                answer["turn"] = raw["turn"]
                answer["knowledge"]["items"] = self.home_items()
                self.consume(policy, answer)
        self.fail((self.events, reasons[-16:]))


class FundraisePlanRecordedTest(BurstVisitRecordedTest):
    """n1-b 04:47: no catalogue claim on Home without an identification source."""

    fixture_path = FUNDRAISE_PLAN

    def test_recorded_stop(self):
        reasons = [row["reason"] for row in self.case["decisions"]]
        self.assertEqual(reasons[5], "home:route-claim-unfulfilled")
        self.assertEqual(reasons[8], "periodic:character-dump")
        self.assertEqual(reasons[9], "town:entrance-step-off:fundraise:fallback-exhausted-plan")
        self.assertEqual(reasons[10], "town:blocked:depth-gate:destination-20:missing-free_action")
        self.assertEqual(reasons[-1], BURST)
        self.assertEqual(self.case["decisions"][9]["procurement_requirements"][-1]["item"],
                         "Treasure Detection scrolls")
        # Home's shelf held the five Treasure Detection scrolls the set needed.
        shelf = self.case["replies"][0]["store"]["items"]
        self.assertEqual(sum(item["count"] for item in shelf
                             if (item["tval"], item["sval"]) == (70, 26)), 5)

    def test_robe_without_a_source_claims_no_home_pass(self):
        policy, raw = self.boundary()
        raw, reasons = self.run_visit(
            policy, raw, limit=20,
            done=lambda policy, board, key: policy._fundraising_mode == "mine")
        # The Home page closes once with its scan; no pass is unfulfilled and
        # Home is never blocked for the visit.
        self.assertNotIn("home:route-claim-unfulfilled", reasons)
        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
        # The fundraising set takes its Treasure Detection from Home's shelf.
        self.assertIn("fundraising:no-safe-destination:depth-gate:destination-20:"
                      "missing-free_action",
                      [reason.removeprefix("town:entrance-step-off:") for reason in reasons])
        withdrawn = [name for kind, name in self.events if kind == "withdraw"]
        self.assertEqual(withdrawn, ["財宝感知の巻物"], self.events)
        self.assertFalse([reason for reason in reasons if "fallback-exhausted" in reason], reasons)


if __name__ == "__main__":
    import unittest
    unittest.main()
