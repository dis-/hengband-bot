"""Two town owner-retired-burst visits of 2026-11-02 04:35 and 04:47.

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
- n1-a life-464, Outpost 04:35 (Lv38, bot-3aec0670c).  The Home junk sweep
  (#95 slice 1b-2, one ware per Home entry) took the three empty capture
  balls and destroyed each outside; every destroy was observed
  (home-full-destroy-observed).  The burst counter credits only the evidenced
  completion of an admitted execution, but it admitted the states "ready",
  "posted" and "awaiting" while ClaimRegister declares a sent command as
  "acting", and every destroy shared one work id: no destroy was credited
  and the three Home re-entries' retirements made the burst
  (decisions 3438-3455).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import re
from types import SimpleNamespace

from hengbot import cli
from hengbot.model import TVAL_CAPTURE, parse_snapshot
from hengbot.policy_constants import STORE_HOME
import tests.test_unid_deposit_recorded as recorded
from recorded_consumable_policy import pre_consumable_table_replay


FIXTURES = Path(__file__).with_name("fixtures")
FUNDRAISE_PLAN = FIXTURES / "home-loops-0446-fundraise-plan.json.gz"
JUNK_SWEEP = FIXTURES / "home-loops-0446-junk-sweep.json.gz"
BURST = "town:blocked:owner-retired-burst"
PAGE_ROWS = 52


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


class JunkSweepRecordedTest(BurstVisitRecordedTest):
    """n1-a 04:35: the Home junk sweep's observed destroys are progress."""

    fixture_path = JUNK_SWEEP

    def setUp(self):
        super().setUp()
        # DECLARED CONSTRUCTED: the Home shelf is the board's ~9 answer,
        # served in pages of 52 (this Home's recorded page size).
        self.shelf = [{k: v for k, v in item.items() if k != "slot"}
                      for item in self.case["home_answer"]["knowledge"]["items"]]
        self.pages[STORE_HOME] = self.home_page()

    def post(self, policy, raw, key, following):
        here = (raw["player"]["y"], raw["player"]["x"])
        body = key[1:]
        pages = len(body) - len(body.lstrip(" "))
        if (policy.last_reason.startswith("home-errand:")
                or not (key.startswith("5") and raw.get("store") is None
                        and self.cells.get(here) == STORE_HOME and pages)):
            # The Home errand posts its entry and tail as one atomic command.
            return super().post(policy, raw, key, following)
        # DECLARED CONSTRUCTED: the entry turns N pages (store.cpp ' ') before
        # its take, then the base entry screens on that page.
        inside = [dict(copy.deepcopy(raw), store=self.home_page(page))
                  for page in range(pages + 1)]
        screens = [self.shelf_screen(state) for state in inside]
        expected = ["5", *" " * pages]
        for command, letter, quantity in re.findall(r"([dp])([a-zA-Z])(?:(\d+\r))?", body):
            screens.append(recorded.executor_harness.prompt_screen(
                "(アイテム:a-z, ESCで中断) どのアイテムを取りますか? "))
            expected += [command, letter]
            if quantity:
                screens.append(recorded.executor_harness.prompt_screen("いくつですか (1-99): 1"))
                expected.append(quantity)
            screens.append(screens[pages])
        expected.append("\x1b")
        states = inside + [inside[-1]] * (len(screens) - len(inside))
        return self.execute(policy, raw, key, following, screens, states, expected)

    def home_page(self, number=0):
        page = copy.deepcopy(self.case["replies"][0]["store"])
        items = copy.deepcopy(self.shelf[number * PAGE_ROWS:(number + 1) * PAGE_ROWS])
        for index, item in enumerate(items):
            item["letter"] = recorded.LETTERS[index]
        page.update(page_top=number * PAGE_ROWS, stock_num=len(self.shelf), items=items)
        return page

    def home_items(self):
        return copy.deepcopy(self.shelf)

    def home_reply(self, following, page, body):
        """DECLARED CONSTRUCTED: store.cpp Home deposit (d) and take (p) on
        page N (N spaces)."""
        pages = len(body) - len(body.lstrip(" "))
        for command, letter, quantity in re.findall(r"([dp])([a-zA-Z])(?:(\d+)\r)?", body):
            if command == "d":
                item = next(it for it in following["inventory"] if it["slot"] == letter)
                count = int(quantity or item["count"])
                moved = dict(item, count=count)
                moved.pop("slot")
                item["count"] -= count
                following["inventory"] = [it for it in following["inventory"] if it["count"]]
                self.shelf.append(moved)
                self.events.append(("deposit", moved["name"]))
            else:
                ware = self.shelf[pages * PAGE_ROWS + recorded.LETTERS.index(letter)]
                count = int(quantity or 1)
                following["inventory"].append(dict(ware, count=count))
                ware["count"] -= count
                self.shelf = [item for item in self.shelf if item["count"]]
                self.events.append(("withdraw", ware["name"]))
            self.relabel(following["inventory"])
        self.pages[STORE_HOME] = self.home_page()

    def reply(self, raw, key):
        destroy = re.fullmatch(r"0(\d+)k([a-z])", key)
        here = (raw["player"]["y"], raw["player"]["x"])
        if (key.startswith("5 ") and raw.get("store") is None
                and self.cells.get(here) == STORE_HOME):
            # The base reply reads an unpaged entry body only.
            following = copy.deepcopy(raw)
            following["turn"] += 10
            following["messages"] = []
            self.home_reply(following, None, key[1:])
            return following
        if destroy is None:
            return super().reply(raw, key)
        # DECLARED CONSTRUCTED: the forced destroy (0<count>k<item>).
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        target = next(it for it in following["inventory"] if it["slot"] == destroy.group(2))
        target["count"] -= int(destroy.group(1))
        following["inventory"] = [it for it in following["inventory"] if it["count"]]
        self.relabel(following["inventory"])
        self.events.append(("destroy", target["name"]))
        return following

    def test_recorded_stop(self):
        decisions = {row["decision_sequence"]: row for row in self.case["decisions"]}
        self.assertEqual(decisions[3426]["reason"], "town:recall-stockout-mining")
        self.assertEqual(decisions[3426]["fundraising"]["planned_runs"], 1)
        sweep = [decisions[sequence]["reason"] for sequence in (3439, 3440, 3447, 3448, 3452, 3453)]
        self.assertEqual(sweep, ["home-errand:atomic-withdraw:full-home-discard",
                                 "home:junk-sweep:unwanted-kind"] * 3)
        # Each observed destroy closed its claim, yet the arbiter's three
        # retirements (3442, 3449, 3455) found no credited progress.
        self.assertEqual({decisions[sequence]["claim"]["closed_claim"]["closed_reason"]
                          for sequence in (3441, 3449, 3454)}, {"home-full-destroy-observed"})
        self.assertEqual(decisions[3455]["reason"], BURST)
        balls = [item for item in self.case["home_answer"]["knowledge"]["items"]
                 if item["tval"] == TVAL_CAPTURE]
        self.assertEqual(len(balls), 3)

    # declared wall: the subject is the capture-ball sweep; under the owner's
    # 2026-11-02 table the Home's 「捨てる」 potions and scrolls are swept too,
    # which this visit interpreter (Home pages, shop pages) does not model.
    @pre_consumable_table_replay
    def test_each_observed_destroy_is_credited_progress(self):
        policy, raw = self.boundary()
        # DECLARED RECONSTRUCTED from decision 3426 (town:recall-stockout-
        # mining): the visit's one-run mining preparation, as
        # _start_unobtainable_recall_stockout_mining opened it.
        policy._fundraising_mode = "prepare"
        policy._planned_mining_runs = 1
        policy._mining_runs_completed = 0
        policy._recall_stockout_mining_plan = True
        destroyed = lambda: [name for kind, name in self.events if kind == "destroy"]
        raw, reasons = self.run_visit(
            policy, raw, limit=60,
            done=lambda policy, board, key: len(destroyed()) == 3
            and policy.last_reason == "shop:travel")
        # One ball per Home entry (#95 slice 1b-2), each destroyed outside;
        # the visit goes on to its next store instead of the burst.
        self.assertEqual(destroyed(), ["モンスター・ボール (空)"] * 3, self.events)
        self.assertEqual(reasons.count("home:junk-sweep:unwanted-kind"), 3, reasons)
        self.assertNotIn(BURST, reasons)
        self.assertLess(max(self.unprogressed), cli.OWNER_RETIRED_LOG_ONLY_LIMIT, reasons)


if __name__ == "__main__":
    import unittest
    unittest.main()
