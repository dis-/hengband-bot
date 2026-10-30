"""D30: the recorded 2026-10-30 Home-withdraw loops at the town pack floor.

Nine viewing captures (n1-a 420, 422, 427, 428, 430, n1-b 252, 258, 273,
n1-c 013) stopped on loop-detected after repeating home:queue-*-withdraw or
home:leave-for-pending-withdraw, shop:approach / shop:travel:await-entry and
town:blocked:repetition.  Each had 19 or 20 of 23 pack slots used.  #47
(29e4b6e90) made the outside composer refuse every Home take that would leave
fewer than MIN_TERMINAL_FREE_PACK_SLOTS free (store_item_key ->
town_pack_budget.permits), but the owners that bind a take from the open Home
page and leave for it (the digger queue, the catalogue-shortage queue, the
pending-withdraw hand-off, a filed Home errand) did not ask that question.
The take was bound, Home was left, the composer refused it, Home was
re-entered and the same take was bound again.  A bound take also kept the
pack-headroom owner from starting (may_begin needs no pending take), so the
room it would have made never appeared.

Each case starts on the recorded Home page with the recorded catalogue and
town errand plan.  The Home and its entrance are a constructed engine
(declared below); every decision goes through the public chooser and the
production executor.  Fixture: tests/extract_town_withdraw_pack_budget_fixture.py.
"""
import tests  # noqa: F401 -- runtime-file isolation

import copy
import gzip
import hashlib
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from hengbot.policy_types import TownErrandPlan
from tests import test_input_executor as harness
from tests.support.headroom_home import HeadroomHomeGame
from tests.test_esp_threat_rest_recorded import _policy


FIXTURE = Path(__file__).with_name("fixtures") / "town-withdraw-pack-budget-20261030.json.gz"
FIXTURE_SHA256 = "181c73690dbf3f845b867868227a77851048497cb39dfbee4000cb65462f7637"
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
HOME_TRAVEL_TRIGGER = "\x15"  # TRAVEL_MACRO_TRIGGERS["\x1b`n(."]
OTHER_TRAVEL_TRIGGERS = "\x0b\x0c\x0e\x0f\x10\x11\x12"


# The recorded loops ended in these (town:blocked:owner-retired in a replay).
STOPS = ("town:blocked:owner-retired", "town:blocked:repetition")


class HomeEntranceGame(HeadroomHomeGame):
    """DECLARED CONSTRUCTED: Home plus the steps around its entrance.

    Walking onto the shop grid enters it (cmd-store.cpp via move_player);
    travel to Home lands on it.  Travel to another store ends the case: the
    loop under test is the Home re-entry, not the town route.
    """
    entrance = position = left_for = None

    def _consume(self, keys):
        for key in keys:
            if self.inside or self.pending is not None or self.modal is not None:
                super()._consume(key)
            elif key in DIRECTIONS:
                dy, dx = DIRECTIONS[key]
                self.position = (self.position[0] + dy, self.position[1] + dx)
                if self.position == self.entrance:
                    self.inside = True
                    self.entries += 1
                self.turn += 1
            elif key == HOME_TRAVEL_TRIGGER:
                self.position, self.inside = self.entrance, True
                self.entries += 1
            elif key in OTHER_TRAVEL_TRIGGERS:
                self.left_for = key
            else:
                super()._consume(key)

    def _state(self):
        state = super()._state()
        state["player"] = dict(state["player"], y=self.position[0], x=self.position[1])
        return state


class TownWithdrawPackBudgetRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == FIXTURE_SHA256
        cls.cases = {case["id"].split("/2026")[0]: case
                     for case in json.loads(gzip.decompress(data))}

    def answer(self, policy, row):
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        _consume_response_sequence([json.dumps(row)], policy, lambda key: True, {},
                                   knowledge_ledger_path=Path(self.directory.name) / "k.jsonl")

    def boundary(self, case):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        policy = _policy(Path(self.directory.name), {})
        if case["knowledge"] is not None:
            self.answer(policy, case["knowledge"])
        board = parse_snapshot(copy.deepcopy(case["page"]))
        policy.prime(board)
        policy._home_page_size = case["page"]["store"]["page_size"]
        policy._fundraising_mode = case["fundraising_mode"]
        # DECLARED CONSTRUCTED: the skill census, as in the other town replays.
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        # DECLARED RECONSTRUCTED: the capture's town errand plan (the Home stop
        # the loop held); its pass count restarts with this replay.
        plan = case["plan"]
        policy._town_errand_plan = TownErrandPlan(
            stops=list(plan["stops"]),
            need_categories={int(k): tuple(v) for k, v in plan["need_categories"].items()},
            index=plan["index"], completed_this_visit=list(plan["completed_this_visit"]),
            requester_families={int(k): frozenset(v)
                                for k, v in plan["requester_families"].items()})
        return policy

    def drive(self, name, limit=14, *, recorded_pending=False):
        """Return the reasons and the Home entry states of a bounded drive."""
        case = self.cases[name]
        policy = self.boundary(case)
        if recorded_pending:
            # DECLARED RECONSTRUCTED: the take the capture's policy-state still
            # held at the stop, bound while the pack had room for it.
            policy._home_pending_item = tuple(case["pending"]["item"])
            policy._home_pending_quantity = case["pending"]["quantity"]
            policy._home_withdrawal_queued = True
        page = case["page"]
        shelf = ([dict(item) for item in case["knowledge"]["knowledge"]["items"]]
                 if case["knowledge"] is not None
                 else [{k: v for k, v in item.items() if k != "letter"}
                       for item in page["store"]["items"]])
        game = HomeEntranceGame(
            pack=copy.deepcopy(page["inventory"]),
            equipment={item["slot"]: item for item in copy.deepcopy(page["equipment"])},
            pages=[shelf], inside=True, state_template=copy.deepcopy(case["outside"]),
            home_limit=page["store"]["capacity"])
        game.entrance = game.position = (page["player"]["y"], page["player"]["x"])
        game.turn = page["turn"]
        _, _, executor = self.make(game)
        executor.drain = lambda: [game._state()]
        result = executor.observe_boundary(deadline=time.monotonic() + 5)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                  request_budget=2, policy=policy)
        reasons, entry_states = [], []
        for _ in range(limit):
            current = parse_snapshot(result.board)
            key = policy.choose_key(current)
            reasons.append(policy.last_reason)
            self.assertTrue(key, reasons)
            if current.store is not None:
                entry_states.append(json.dumps(
                    (game.pack, game._items(), policy.last_reason), sort_keys=True))
            if policy.last_reason.startswith(STOPS):
                break
            _send_new_decision_key(
                port, json.dumps(result.board), key, None, set(),
                in_store=current.store is not None, snapshot=current,
                decision={"sequence": policy._decision_sequence,
                          "reason": policy.last_reason, "key": key})
            result = port.last_result
            self.assertEqual(result.outcome, "completed", (reasons, result.reason))
            policy.confirm_key_posted(key)
            if game.left_for is not None:
                break
            if "request-knowledge-scan" in policy.last_reason:
                # DECLARED CONSTRUCTED: the ~9 answer from the engine's shelf.
                row = copy.deepcopy(case["outside"])
                row.update(game._state(), type="knowledge",
                           knowledge={"category": "home", "menu_key": "9",
                                      "items": copy.deepcopy(game._items())})
                self.answer(policy, row)
        return reasons, entry_states, game

    def assert_no_unchanged_reentry(self, reasons, entry_states):
        self.assertFalse(any(reason.startswith(STOPS) for reason in reasons), reasons)
        # The loop: Home re-entered with the pack and the shelf unchanged, and
        # the same Home decision made again.
        self.assertEqual(len(entry_states), len(set(entry_states)), reasons)

    def test_recorded_loops_began_at_the_pack_floor(self):
        for name, reason in (("n1-a/life-420", "home:queue-digging-tool-withdraw"),
                             ("n1-b/life-252", "home:queue-catalogue-shortage"),
                             ("n1-a/life-445", "home:queue-catalogue-shortage")):
            with self.subTest(case=name):
                recorded = self.cases[name]["recorded"]
                self.assertEqual(recorded["reason"], reason)
                self.assertEqual(recorded["inventory"], {"used": 19, "free": 4})
                self.assertTrue(any(last.startswith(("home:leave-for-pending-withdraw",
                                                     "home:queue-", "town:blocked:"))
                                    for last in recorded["last_reasons"]))

    def test_life_420_frees_room_then_takes_the_stored_digger(self):
        reasons, entry_states, game = self.drive("n1-a/life-420")
        self.assert_no_unchanged_reentry(reasons, entry_states)
        self.assertIn("home:atomic-deposit", reasons)
        self.assertIn("home:atomic-withdraw", reasons)
        self.assertTrue(any(item["tval"] == 20 for item in game.pack))  # TV_DIGGING

    def test_life_420_does_not_leave_home_for_a_take_the_pack_cannot_hold(self):
        # The loop's second phase: the digger was still bound with four free
        # slots (town:blocked:repetition, await-entry, leave-for-pending).
        reasons, entry_states, game = self.drive("n1-a/life-420", recorded_pending=True)
        self.assert_no_unchanged_reentry(reasons, entry_states)
        self.assertIn("home:atomic-withdraw", reasons)
        self.assertTrue(any(item["tval"] == 20 for item in game.pack))  # TV_DIGGING

    def test_life_252_does_not_bind_the_detection_scrolls_it_cannot_carry(self):
        reasons, entry_states, game = self.drive("n1-b/life-252")
        self.assert_no_unchanged_reentry(reasons, entry_states)
        self.assertNotIn("home:queue-catalogue-shortage", reasons)
        self.assertNotIn("home:leave-for-pending-withdraw", reasons)
        self.assertIsNotNone(game.left_for, reasons)

    def test_life_445_does_not_bind_the_digger_it_cannot_carry(self):
        reasons, entry_states, game = self.drive("n1-a/life-445")
        self.assert_no_unchanged_reentry(reasons, entry_states)
        self.assertNotIn("home:queue-digging-tool-withdraw", reasons)
        self.assertIsNotNone(game.left_for, reasons)


if __name__ == "__main__":
    import unittest
    unittest.main()
