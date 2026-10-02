"""Recorded pin: a routed Home arrival is not held by its own finished route.

Live stop 2026-10-02 06:16:20 (``loop-detected``, the 7th stop of this shape
since 2026-10-01 22:24; the other six named ``overweight-home-unreachable``).
Bot process 06:14:06 (commit c4677d7a, ``--enforce-crossarea-fundraising``,
S3.3 switch off), frozen by tests/extract_overweight_home_hold_fixture.py:

- 0..2: ``~f``, ``~9`` Home scan, ``shop:travel`` to Home (Home is the only
  supplier of the ``weight-overload`` need: carried 1752 > limit 1750).
- 3: inside Home, ESC ``home:route-claim-unfulfilled``.  The record names
  the cause: every Home producer entry (``_release_staged_store_operation``,
  ``_home_rearm_key``, ``_open_home_deposit_key``) deferred to holder
  ``store-router`` claim 3, the Reach route to the Home entrance (45, 123)
  that this very board shows arrived (the claim closed ``reached`` at the
  same decision's exit).  ``_home_sequence_has_holder`` (live23, cross-area
  enforcement) counted any open errand during a Home visit as a holder; the
  early arrival completion that S3.3 ON runs before town producers ask
  (``choose_key``) does not run with S3.3 off.
- 4..10: the other stops, then the Home latch leaves the weight claim with
  no route; 11..: ``town:blocked:no-actionable-claim-owner`` / ``probe``
  until the loop detector stopped the bot.

Fix 1: the cross-area Home hold reads the board's observed arrival (the same
evidence ``_claim_exit_completion`` closes a cell Reach on) and does not
count that finished route as a holder.  Fix 2 (review P1): a Home pass
that left the overload without a failed deposit (deferred / never posted) is
re-armed and routed Home again while Home's own pass/approach/visit bound
remains; with the bound exhausted the unowned wait is the user's 2026-09-03
failed-deposit stop, ``town:blocked:overweight-home-unreachable``.  Fix 3
(review P2): the departure recall scroll (user 2026-09-20) is required
whether or not the recall target still awaits its safe-landing switch, so
Home retention keeps 10 recall scrolls as the departure board does.

Walls (declared): ``WALL_PRE_FIX_HOLD`` replays index 3 with the pre-fix
hold (no arrival board), reproducing the live key, so that the later
recorded boards are the effect of the same keys; ``STEP_OFF_WALL`` index 10:
the step-off tie between equally unvisited cells is broken by visit history
this capture does not contain (replay '1', live '3', same reason); the live
key is posted.  No board after a changed key is used (R4).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS, STORE_HOME

from test_esp_threat_rest_recorded import EDIT, _policy
from xbow_pref_walls import shelf_wall_on_replay
from extraction_calibration import install_extraction_calibration

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "overweight-home-hold-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "overweight-home-hold-20261002.boundaries.json"
CALIBRATION = FIXTURES / "overweight-home-hold-20261002.character-calibration.json"
SHA256 = {
    FIXTURE: "19373cf512f436f24eda6d5a8459269b3c6b3122540aedec8e426a1f293c16bd",
    BOUNDARIES: "254746265f8fea1712d690bd8c8fa593f96fab3aa4d82957f0c16370f1c517d0",
    CALIBRATION: "0b64f6942910ac432bda1e2c29a7347447d8842de63059628e6eb6f923e6c86e",
}
HOME = 3
WALL_PRE_FIX_HOLD = 3
STEP_OFF_WALL = 10
STOP = 11


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class OverweightHomeHoldRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
        cls.boundaries = boundaries
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            lines = stream.read().splitlines(keepends=True)
        assert len(lines) == sum(boundaries["input_rows"])
        cls.segments = []
        start = 0
        for count in boundaries["input_rows"]:
            cls.segments.append(lines[start:start + count])
            start += count
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _replay(self, last, *, walls=False, inspect=None, prepare=None):
        """Replay the frozen process through ``last`` on one policy."""
        rows = []
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, self.monrace)
            policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
            install_extraction_calibration(policy)
            policy._crossarea_fundraising_enforced = True  # live argv
            for index in range(last + 1):
                _decoded, snapshots = _consume_response_sequence(
                    self.segments[index], policy, lambda _key: True, self.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                board = snapshots[-1]
                if prepare is not None:
                    prepare(index, policy, board)
                if walls and index == WALL_PRE_FIX_HOLD:
                    # create=True: the pre-fix source has no such seam.
                    with patch.object(HengbotPolicy, "_home_hold_board",
                                      lambda _self: None, create=True):
                        key = policy.choose_key(board)
                else:
                    key = policy.choose_key(board)
                rows.append((str(key), policy.last_reason))
                if inspect is not None:
                    inspect(index, policy, board)
                posted = key
                if walls and index == STEP_OFF_WALL:
                    self.assertEqual(policy.last_reason, self.recorded[index]["reason"])
                    posted = self.recorded[index]["key"]
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain(
                        {"outcome": "released", "posted": str(posted)})
        return rows

    def _live(self, index):
        row = self.recorded[index]
        return row["key"], row["reason"]

    # ------------------------------------------------------------ recorded
    def test_recorded_home_pass_was_held_by_the_arrived_route(self):
        self.assertEqual(self._live(HOME), ("\x1b", "home:route-claim-unfulfilled"))
        self.assertEqual(self.recorded[HOME]["position"], [45, 123])
        claim = self.boundaries["home_claim"]
        self.assertEqual((claim["owner"], claim["reason"]),
                         ("home-visit", "home:route-claim-unfulfilled"))
        self.assertEqual(
            [(row["holder_family"], row["holder_claim_id"], row["deferred_family"],
              row["deferred_reason"], row["token_would_admit"])
             for row in claim["errand_deferred"]],
            [("store-router", 3, "home-visit", "entry:_release_staged_store_operation", False),
             ("store-router", 3, "equipment-txn", "entry:_home_rearm_key", False),
             ("store-router", 3, "home-visit", "entry:_open_home_deposit_key", False)],
        )
        self.assertEqual(self.boundaries["home_closed_claim"], {
            "claim_id": 3, "owner": "store-router", "goal_kind": "Reach",
            "closed_reason": "reached"})
        self.assertEqual(self._live(STOP), ("5", "town:blocked:no-actionable-claim-owner"))
        block = self.boundaries["stop_departure_block"]
        self.assertEqual(block["failed"], ["inventory_weight_ready"])
        self.assertEqual(block["town_claims"], ["weight-overload"])
        self.assertEqual(block["town_ledger"]["unsatisfied_passes"], {"7": 2})

    # ------------------------------------------------------------ fix 1
    def test_routed_home_arrival_deposits_the_minimal_overload(self):
        seen = {}

        def inspect(index, policy, board):
            if index != HOME:
                return
            seen["weight"] = (policy._inventory_weight(board),
                              policy._inventory_weight_limit(board))
            seen["reservations"] = [
                (item.slot, item.count, policy._retention_reservation(board, item))
                for item in board.inventory]
            seen["ammo_target"] = policy._ammo_procurement_target(
                board, for_retention=True)
            seen["candidates"] = [item.slot for item in
                                  policy._weight_deposit_candidates(board)]
            seen["closed"] = (policy.decision_claim or {}).get("closed_claim")
            seen["board"] = board
            seen["policy"] = policy

        rows = self._replay(HOME, inspect=inspect)
        for index in range(HOME):
            self.assertEqual(rows[index], self._live(index), index)
        # First changed key versus live (ESC route-claim-unfulfilled): stop here.
        self.assertEqual(rows[HOME], ("dk\x1b", "home:weight-overload-deposit"))
        self.assertEqual(seen["weight"], (1752, 1750))
        board, policy = seen["board"], seen["policy"]
        deposited = next(item for item in board.inventory if item.slot == "k")
        self.assertEqual((deposited.count, deposited.weight, deposited.is_digging_tool),
                         (1, 150, True))
        # Required supplies stay carried (09-03 #1): every reserved stack.
        self.assertEqual(seen["reservations"], [
            ("a", 6, 6), ("b", 10, 10), ("c", 3, 3), ("d", 15, 15), ("e", 10, 10),
            ("f", 6, 6), ("g", 1, 0), ("h", 2, 2), ("i", 2, 0), ("j", 1, 0),
            ("k", 1, 0), ("l", 63, 63)])
        # Retention surplus clears the overload, so the 10-01 iron-shot
        # deposit keeps all shots (fits 99) and offers none.
        self.assertEqual(seen["ammo_target"], 99)
        self.assertEqual(seen["candidates"], ["k", "j", "i"])
        remaining = replace(board, store=None, inventory=tuple(
            item for item in board.inventory if item.slot != "k"))
        self.assertEqual(policy._inventory_weight(remaining), 1602)
        self.assertFalse(policy._inventory_overweight(remaining))
        self.assertEqual(policy._total_identify_staff_charges(remaining), 31)
        self.assertTrue(policy._identify_staff_ready(remaining))
        # The arrived route still closes on its own evidence.
        self.assertEqual((seen["closed"]["claim_id"], seen["closed"]["owner"],
                          seen["closed"]["closed_reason"]),
                         (3, "store-router", "reached"))

    def test_pre_fix_hold_reproduces_the_live_home_pass(self):
        rows = self._replay(HOME, walls=True)
        self.assertEqual(rows, [self._live(index) for index in range(HOME + 1)])

    # ------------------------------------------------------------ fix 2
    def _stop_board_state(self, state):
        def inspect(index, policy, board):
            if index == STOP:
                state["attempted"] = STORE_HOME in policy._town_store_attempted
                state["overweight"] = policy._inventory_overweight(board)
                state["blocked"] = policy._town_blocked_reason
        return inspect

    @shelf_wall_on_replay  # declared wall: no 2026-10-02 crossbow swap (tests/xbow_pref_walls.py)
    def test_unposted_home_deposit_routes_home_again(self):
        """Deferred, never-posted Home work within its bound: travel Home."""
        state = {}
        rows = self._replay(STOP, walls=True, inspect=self._stop_board_state(state))
        for index in range(STEP_OFF_WALL):
            self.assertEqual(rows[index], self._live(index), index)
        self.assertEqual(rows[STEP_OFF_WALL][1], self._live(STEP_OFF_WALL)[1])
        # First changed key versus live (5 no-actionable-claim-owner): stop here.
        self.assertEqual(rows[STOP], ("`n(.", "shop:travel"))
        self.assertEqual(state, {"attempted": False, "overweight": True,
                                 "blocked": None})

    @shelf_wall_on_replay  # declared wall: no 2026-10-02 crossbow swap (tests/xbow_pref_walls.py)
    def test_exhausted_home_bound_ends_in_the_named_overweight_stop(self):
        """Counterfactual bound on the same board: the genuine-failure stop."""
        for counter in ("unsatisfied_passes", "approach_fails"):
            with self.subTest(counter=counter):
                state = {}

                def prepare(index, policy, board, counter=counter):
                    if index == STOP:
                        ledger = policy._town_visit_ledger
                        self.assertEqual(ledger.unsatisfied_passes[STORE_HOME], 2)
                        getattr(ledger, counter)[STORE_HOME] = (
                            policy._town_store_visit_limit(STORE_HOME))

                rows = self._replay(STOP, walls=True, prepare=prepare,
                                    inspect=self._stop_board_state(state))
                self.assertEqual(rows[STOP],
                                 ("5", "town:blocked:overweight-home-unreachable"))
                self.assertIn(rows[STOP][1], POLICY_FINAL_STOP_REASONS)
                self.assertEqual(state, {"attempted": True, "overweight": True,
                                         "blocked": "overweight-home-unreachable"})

    # ------------------------------------------------------------ fix 3
    @shelf_wall_on_replay  # declared wall: no 2026-10-02 crossbow swap (tests/xbow_pref_walls.py)
    def test_recall_reservation_inside_home_matches_departure_board(self):
        seen = {}

        def inspect(index, policy, board):
            if index in (HOME, STOP):
                recall = next(item for item in board.inventory if item.is_recall_scroll)
                seen[index] = (
                    board.store is not None,
                    policy._supply_ledger(board, policy._planned_depth())[
                        "recall"].required_departure,
                    policy._retention_reservation(board, recall),
                )

        self._replay(STOP, walls=True, inspect=inspect)
        # Inside Home before the safe-landing switch; outside after it.
        self.assertEqual(seen, {HOME: (True, 10, 10), STOP: (False, 10, 10)})


if __name__ == "__main__":
    unittest.main()
