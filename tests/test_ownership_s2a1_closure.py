"""Stage S2a.1: goals are declared by their producer, typed, and closed.

``SOL-DESIGN-ownership-contract.md`` rev 9.1, "Rev 9: S2a.1 specified".  On
the live S1 ledger goals were *borrowed* (``_claim_goal_cell`` took whatever
committed cell sat in shared state, so ``town:wait-recall`` carried a store
trip's entrance) and almost nothing could close (``release`` and ``suspend``
had no caller, and a ``Terminal`` claim had no closing path at all), so the
S2b gate could not be read.  S2a.1 is recording only: every line it adds
inside a producer writes the per-decision goal slot or calls the claim
register, and no key, reason or decision changes.

The pins
--------
B1  typing: every census prefix of every family has a row of the checked-in
    table, and no decision row can carry a Reach cell its producer did not
    write (a stale ``_store_visit.goal`` + ``town:wait-recall`` declares the
    floor-change Observe, never that cell).  **Revert-proof**: the S1
    borrowing scan put back in place of ``_claim_goal`` makes it fail.
B2  closing, on recorded replays.  Pinned numbers below.  Two of the three
    captures the design names cannot give what it expects of them, and that
    is recorded rather than papered over (see ``ClosingPathsTest``): the
    restock window holds decision rows only (no board to replay) and the
    posted-effect captures are, by construction, effects that never arrived.
    The Observe completions of a Home operation and of a purchase are pinned
    on the one recorded lifetime that contains them,
    ``unaffordable-claim-tour-20260922`` (4,267 decisions: dungeon dives,
    purchases, sales, Home deposits and withdrawals), inside
    ``test_unaffordable_claim_tour_recorded`` so the lifetime is replayed
    once.  **Revert-proof**: without the closing calls the dungeon pin and
    the tour's early sale pin fail.
B3  the four gate numbers, one synthetic ledger each; (d) catches a
    multi-row Terminal claim whose position changes.
B4  neutrality: the S2a trajectory digests
    (``test_ownership_s2a_classification`` A1) stay green, and the
    posted-effect pin decisions are the recorded ones with the register on
    and off.
B5  survival: the constant is exactly the user's list, none of the ordinary
    owners is in it, and ``suspend`` is called for it alone.

Restored checkpoints: every attribute S2a.1 adds or newly reads is covered
(``RestoredCheckpointTest``).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare runs

import ast
import base64
import copy
import gzip
import json
import pickle
import tempfile
import unittest
from pathlib import Path

from hengbot.claim_goal_typing import (
    FLOOR_CHANGE,
    GOAL_TYPING,
    ORDINARY_OWNER_PREFIXES,
    SURVIVAL_REASON_PREFIXES,
    SURVIVAL_RETURN_TRIGGERS,
    goal_typing,
    is_survival,
)
from hengbot.claim_register import (
    ClaimOwner,
    ClaimRegister,
    reach,
    terminal,
)
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import Position, parse_snapshot
from hengbot.ownership_metrics import (
    ENDINGS,
    OWNERSHIP_CLAIMS_NAME,
    OWNERSHIP_METRICS_NAME,
    OwnershipMetricsLedger,
    gate_numbers,
    implicit_handoffs,
    read_records,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import (
    OwnerExpectationRegistry,
    StoreVisit,
    StoreVisitPhase,
)
from hengbot.town_arbiter import (
    _new_town_turn_arbiter,
    owner_families,
    reason_owner_family,
)

from test_ownership_claims import LEGACY_CHECKPOINT, _Replay
from test_ownership_s2a_classification import _reason_literals


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "hengbot"
FIXTURES = ROOT / "tests" / "fixtures"
POSTED = FIXTURES / "posted-effect-unobserved-20260923.jsonl.gz"
RESTOCK = FIXTURES / "incident-restock-rest-burn-window-20260825.jsonl.gz"

# The families the rev 9 review found missing from the table; all must have
# rows now (design rev 9.1 item 1).
REVIEW_FAMILIES = (
    "esp-threat", "detectors", "town-plan", "identification",
    "curse-enchant", "cross-town", "rumor", "quest-request", "home-errand",
    "equipment-opt", "misc",
)

# B5: design rev 9.1 item 3, verbatim list.
DESIGN_SURVIVAL_PREFIXES = (
    "emergency:", "unseen-recall:", "guardian:teleport-to-cover",
    "combat:disengage", "unseen:", "esp-threat:leave-",
)
DESIGN_SURVIVAL_TRIGGERS = {"esp-threat", "unseen-attacker", "guardian-reposition"}
DESIGN_ORDINARY_REASONS = (
    "flee", "flee:stairs", "summoner:retreat", "summoner:stairs",
    "threat:scroll", "threat:wait", "breeder-breakthrough:ascend",
    "combat:fruitless", "status-threat:retreat", "confused:wait",
    "town:recover", "town:seek-shelter",
)

# -- B2 pinned numbers -----------------------------------------------------
# tests/fixtures/loot-choke-oscillation-20260923.jsonl.gz, 24 boards.
# (row index, closed claim's owner, goal kind, closing event, label)
DUNGEON_CLOSINGS = [
    (1, "explore", "Reach", "complete", "explore-goal-complete"),
    (2, "explore", "Reach", "complete", "reached"),
    (5, "positioning", "Reach", "release", "choke-hostile-visible"),
]
DUNGEON_ENDINGS = {
    "explore/Reach": {"complete": 2},
    "positioning/Reach": {"release": 1, "open-at-end": 1},
}
# Before S2a.1 (157e5010, S1 reader): 3 implicit owner changes by owner.
DUNGEON_IMPLICIT_BEFORE = 3
# The S2a.1 reader of the same rows: every owner change is now closed.
DUNGEON_IMPLICIT_AFTER = 0

# tests/fixtures/posted-effect-unobserved-20260923.jsonl.gz, driven through
# the test_posted_effect_unobserved P2/P3 setups (recorded board, recorded
# pre-decision facts re-attached).
POSTED_HOME_CYCLE_CLOSINGS = [("store-router", "Reach", "complete", "reached")]
POSTED_LEAVE_CLOSINGS = [
    ("shop-buy", "Observe", "release", "store-visit:leave-unconfirmed")
]

# tests/fixtures/unaffordable-claim-tour-20260922.jsonl.gz: its full-lifetime
# pins are in test_unaffordable_claim_tour_recorded (S2A1_*).  The first sale
# confirmations (list indices 13 and 18) are cheap enough for the revert-proof.
TOUR_EARLY_SALES = (13, 18)


def _load(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _row(policy, snapshot, key, session, index) -> dict:
    """The claim ledger row of one decision, with the board position."""
    claim = dict(policy.decision_claim or {})
    claim.update(
        kind="claim",
        session=session,
        reason=policy.last_reason,
        key=None if key is None else str(key),
        position={
            "y": snapshot.player.position.y,
            "x": snapshot.player.position.x,
        },
        index=index,
    )
    return claim


def _closings(rows):
    return [
        (
            row["index"],
            row["closed_claim"]["owner"],
            row["closed_claim"]["goal_kind"],
            row["closed_claim"]["closed"] or row["closed_claim"]["state"],
            row["closed_claim"]["closed_reason"],
        )
        for row in rows
        if row.get("closed_claim")
    ]


def _endings_subset(gate, expected):
    return {
        name: {
            ending: gate["endings"].get(name, {}).get(ending, 0)
            for ending in counts
        }
        for name, counts in expected.items()
    }


def _dungeon_rows():
    skill, boards = _Replay.dungeon_boards()
    policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
    policy.consume_skill_knowledge(skill)
    rows = []
    for index, raw in enumerate(boards):
        board = parse_snapshot(raw, _Replay.knowledge())
        key = policy.choose_key(board)
        key = policy.validate_read_key(board, key)
        rows.append(_row(policy, board, key, "dungeon", index))
        policy.confirm_key_posted(key)
    return rows


def _town_board():
    """A recorded town board (outside the Home, 2026-09-23 18:15)."""
    record = next(
        record for record in _load(POSTED)
        if record["role"] == "decision-input"
        and record["decision"]["decision_sequence"] == 1568
    )
    return parse_snapshot(record["board"], _Replay.knowledge())


def _fresh_policy(board):
    policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
    policy.prime(board)
    return policy


# -- B1 ----------------------------------------------------------------------


class GoalTypingTableTest(unittest.TestCase):
    """B1: the table is a checked-in constant covering every census prefix."""

    def test_every_prefix_of_every_family_resolves_to_its_own_row(self):
        registry = _new_town_turn_arbiter().registry
        self.assertEqual(tuple(registry), owner_families())
        for family, entry in registry.items():
            for prefix in (*entry.census_prefixes, *entry.reason_prefixes):
                with self.subTest(family=family, prefix=prefix):
                    row = goal_typing(family, prefix)
                    self.assertIsNotNone(row, "a census prefix with no row")
                    # an exact row, not a shorter prefix standing in for it
                    self.assertTrue(
                        any(
                            candidate.family == family
                            and candidate.prefix == prefix
                            for candidate in GOAL_TYPING
                        )
                    )

    def test_the_families_the_review_found_missing_are_covered(self):
        typed = {row.family for row in GOAL_TYPING}
        for family in REVIEW_FAMILIES:
            with self.subTest(family=family):
                self.assertIn(family, typed)
        self.assertEqual(typed, set(owner_families()))

    def test_a_refinement_never_leaks_into_another_family(self):
        registry = _new_town_turn_arbiter().registry
        for row in GOAL_TYPING:
            census = registry[row.family].census_prefixes
            with self.subTest(family=row.family, prefix=row.prefix):
                self.assertTrue(row.prefix.startswith(census))
                if row.prefix not in census:
                    # a longer row is only reachable through its own family
                    self.assertEqual(reason_owner_family(row.prefix), row.family)
                self.assertIn(row.kind, ("Reach", "Observe", "Terminal"))

    def test_every_reason_the_package_can_emit_is_typed(self):
        for reason in sorted(_reason_literals()):
            with self.subTest(reason=reason):
                self.assertIsNotNone(
                    goal_typing(reason_owner_family(reason), reason)
                )

    def test_the_design_rows_have_the_design_kind(self):
        for reason, kind in (
            ("explore", "Reach"),
            ("seek-loot", "Reach"),
            ("fundraise:dig-to-treasure", "Reach"),
            ("fundraise:seek-treasure", "Reach"),
            ("fundraise:seek-loot", "Reach"),
            ("hunt", "Reach"),
            ("detected:prepare-choke", "Reach"),
            ("return:seek-upstairs", "Reach"),
            ("town:entrance-step-off:shop:approach", "Reach"),
            ("shop:travel", "Reach"),
            ("shop:approach", "Reach"),
            ("shop:one-shot-buy", "Observe"),
            ("home:atomic-withdraw", "Observe"),
            ("shop:batch-inscribe", "Observe"),
            ("home:request-knowledge-scan", "Observe"),
            ("equipment-transaction:takeoff", "Observe"),
            ("return:recall", "Observe"),
            ("town:wait-recall", "Observe"),
            ("town:recall-to-", "Observe"),
            ("melee", "Terminal"),
            ("periodic:game-save", "Terminal"),
            ("town:blocked:owner-retired", "Terminal"),
            ("", "Terminal"),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(
                    goal_typing(reason_owner_family(reason), reason).kind, kind
                )
        self.assertEqual(
            goal_typing("departure", "town:wait-recall").content, FLOOR_CHANGE
        )


class DeclaredGoalSlotTest(unittest.TestCase):
    """B1: a decision's goal comes only from what its producer wrote."""

    STALE = Position(20, 30)

    def _stale_shared_state(self, policy):
        """Every shared-state cell the S1 scan used to borrow from."""
        policy._store_visit = StoreVisit(
            owner="store-router", purpose="town-need", store_type=7,
            goal=self.STALE, phase=StoreVisitPhase.APPROACHING,
        )
        policy._dark_route_goal = self.STALE

    def _declare(self, policy, board, reason, key="5"):
        policy.last_reason = reason
        policy._record_decision_claim(board, key)
        return policy.decision_claim

    def test_a_stale_store_goal_cannot_type_a_recall_wait(self):
        board = _town_board()
        policy = _fresh_policy(board)
        self._stale_shared_state(policy)
        policy._decision_goal = None
        policy._decision_expectation = None
        claim = self._declare(policy, board, "town:wait-recall")
        self.assertEqual(claim["goal"]["kind"], "Observe")
        self.assertEqual(claim["goal"]["source"], FLOOR_CHANGE)
        self.assertNotIn("cell", claim["goal"])
        self.assertFalse(claim["goal_missing"])

    def test_a_reach_row_without_its_own_slot_is_terminal_and_missing(self):
        board = _town_board()
        policy = _fresh_policy(board)
        self._stale_shared_state(policy)
        policy._decision_goal = None
        claim = self._declare(policy, board, "shop:travel")
        self.assertEqual(
            claim["goal"], {"kind": "Terminal", "effect": "shop:travel"}
        )
        self.assertTrue(claim["goal_missing"])

    def test_a_slot_stamped_by_another_reason_is_not_inherited(self):
        board = _town_board()
        policy = _fresh_policy(board)
        policy.last_reason = "shop:approach"
        policy._declare_reach(Position(41, 131))
        # a later rewrite relabels the decision without writing a slot
        claim = self._declare(policy, board, "shop:travel")
        self.assertEqual(claim["goal"]["kind"], "Terminal")
        self.assertTrue(claim["goal_missing"])

    def test_the_producers_own_slot_is_the_goal(self):
        board = _town_board()
        policy = _fresh_policy(board)
        self._stale_shared_state(policy)
        policy.last_reason = "shop:travel"
        policy._declare_reach(Position(41, 131))
        claim = self._declare(policy, board, "shop:travel")
        self.assertEqual(claim["goal"], {"kind": "Reach", "cell": [41, 131]})
        self.assertFalse(claim["goal_missing"])

    def test_the_shared_state_scan_is_gone(self):
        self.assertFalse(hasattr(HengbotPolicy, "_claim_goal_cell"))

    def test_revert_proof_the_s1_scan_borrows_the_stale_cell(self):
        """Put the S1 scan back and the stale entrance reaches the row."""

        def s1_claim_goal(self, snapshot, key, owner, reason, standing):
            visit = getattr(self, "_store_visit", None)
            if visit is not None and isinstance(visit.goal, Position):
                return reach((visit.goal.y, visit.goal.x)), False
            dark = getattr(self, "_dark_route_goal", None)
            if isinstance(dark, Position):
                return reach((dark.y, dark.x)), False
            return terminal(reason or "policy:none"), False

        board = _town_board()
        original = HengbotPolicy._claim_goal
        HengbotPolicy._claim_goal = s1_claim_goal
        try:
            policy = _fresh_policy(board)
            self._stale_shared_state(policy)
            claim = self._declare(policy, board, "town:wait-recall")
        finally:
            HengbotPolicy._claim_goal = original
        self.assertEqual(
            claim["goal"],
            {"kind": "Reach", "cell": [self.STALE.y, self.STALE.x]},
        )
        self.assertIs(HengbotPolicy._claim_goal, original)


# -- B2 ----------------------------------------------------------------------


class ClosingPathsTest(unittest.TestCase):
    """B2: the named replays, with their closings pinned."""

    dungeon = None

    @classmethod
    def dungeon_rows(cls):
        if cls.dungeon is None:
            cls.dungeon = _dungeon_rows()
        return cls.dungeon

    def test_loot_choke_replay_closes_explore_and_positioning(self):
        rows = self.dungeon_rows()
        self.assertEqual(len(rows), 24)
        self.assertEqual(_closings(rows), DUNGEON_CLOSINGS)
        gate = gate_numbers(rows)
        self.assertEqual(_endings_subset(gate, DUNGEON_ENDINGS), DUNGEON_ENDINGS)
        self.assertEqual(gate["dropped_by_other_owner"]["count"], 0)
        self.assertEqual(gate["retargets"]["count"], 0)
        self.assertEqual(
            implicit_handoffs(rows)["implicit_handoffs"], DUNGEON_IMPLICIT_AFTER
        )
        # The replay has no seek-loot decision at all (S2a A4 pins its owners:
        # explore, positioning, combat), so its seek-loot closings are pinned
        # on the tour below.
        self.assertNotIn(
            "floor-loot", {row["owner"] for row in rows}
        )

    def test_revert_proof_without_the_closing_calls_the_dungeon_pin_fails(self):
        original = HengbotPolicy._claim_close
        HengbotPolicy._claim_close = lambda self, *args, **kwargs: None
        try:
            rows = _dungeon_rows()
        finally:
            HengbotPolicy._claim_close = original
        self.assertEqual(_closings(rows), [])
        gate = gate_numbers(rows)
        self.assertNotEqual(
            _endings_subset(gate, DUNGEON_ENDINGS), DUNGEON_ENDINGS
        )
        # the unclosed Reach claims are what (a) counts
        self.assertEqual(
            gate["dropped_by_other_owner"]["pairs"],
            {"explore>positioning": 1, "positioning>combat": 1},
        )
        self.assertEqual(implicit_handoffs(rows)["implicit_handoffs"], 2)

    def test_posted_effect_captures_close_what_they_can(self):
        """The captures are effects that never arrived; their closings.

        18:15 (P3 setup): the Home cycle's store trip reaches its entrance.
        20:10 (P2 setup): the leave confirmation that could never be answered
        ends with its visit (``leave-unconfirmed``) -- a release of the store
        operation's Observe claim, not a completion, because no effect was
        observed.  An Observe ``complete`` cannot occur on these boards.
        """
        from test_posted_effect_unobserved import (
            LEAVE_REPEAT, LEAVE_STORE_KEY, STORE_HOME,
            PostedEffectUnobservedTest,
        )

        PostedEffectUnobservedTest.setUpClass()
        pins = PostedEffectUnobservedTest(
            "test_p3_queued_home_take_refreshes_the_catalogue_it_needs"
        )
        policy, inside, outside = pins._home_cycle_policy()
        board, rows = inside, []
        for index in range(6):
            key = policy.choose_key(board)
            rows.append(_row(policy, board, key, "p3", index))
            board = outside if board is inside else inside
        self.assertEqual(
            [closing[1:] for closing in _closings(rows)],
            POSTED_HOME_CYCLE_CLOSINGS,
        )

        board = pins._board(LEAVE_REPEAT, 5429)
        policy = pins._policy(LEAVE_REPEAT, board, 5429)
        policy._shopping_approach_store_type = STORE_HOME
        policy._store_visit = pins._recorded_visit(
            LEAVE_REPEAT, 5429, composed_key=LEAVE_STORE_KEY
        )
        rows = []
        for index in range(10):
            key = policy.choose_key(board)
            rows.append(_row(policy, board, key, "p2", index))
            if policy._store_visit_last_closed is not None:
                break
            policy._decision_sequence += 1
        self.assertEqual(
            [closing[1:] for closing in _closings(rows)], POSTED_LEAVE_CLOSINGS
        )

    def test_the_named_restock_window_holds_no_board_to_replay(self):
        """Design rev 9.1 (ii) names it for buys; it cannot serve.

        The fixture is 29 decision *rows* (reason, key, store visit,
        position, player) with no board, and it contains no purchase -- its
        store work is one Home withdrawal and restock waits.  The purchase
        completions are pinned on the tour instead.
        """
        records = _load(RESTOCK)
        self.assertEqual(len(records), 29)
        self.assertFalse(
            [record for record in records if "board" in record or "role" in record]
        )
        self.assertFalse(
            [record for record in records
             if str(record["reason"]).startswith(("shop:one-shot-buy", "shop:buy"))]
        )

    # -- the recorded lifetime with purchases, sales and Home operations --

    @staticmethod
    def tour_rows(*, limit: int):
        """The first ``limit`` decisions of the tour lifetime, with claims."""
        import test_unaffordable_claim_tour_recorded as tour
        from hengbot.cli import _consume_response_sequence

        tour.UnaffordableClaimTourRecordedTest.setUpClass()
        replay = tour.UnaffordableClaimTourRecordedTest
        stop = limit
        rows = []
        with tempfile.TemporaryDirectory(prefix="s2a1-tour-") as raw:
            directory = Path(raw)
            policy, monrace = tour._live_like_policy(directory)
            cursor = 0
            for index in range(stop):
                count = replay.boundaries["input_rows"][index]
                segment = replay.lines[cursor:cursor + count]
                cursor += count
                _decoded, snapshots = _consume_response_sequence(
                    segment, policy, lambda _key: True, monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                snapshot = snapshots[-1]
                policy._experience_drain_known = tour._drain_unknown
                recorded_reason = replay.boundaries["recorded"][index][1]
                if recorded_reason == "periodic:game-save":
                    policy.request_game_save()
                elif recorded_reason == "periodic:character-dump":
                    policy.request_character_dump()
                key = policy.choose_key(snapshot)
                key = policy.validate_read_key(snapshot, key)
                rows.append(_row(policy, snapshot, key, "tour", index))
                # The recorded process ran the capture unscoped (see the
                # tour module); only the claim register is kept out of it,
                # as the live driver's observer scope now does.
                register = policy._claim_register
                policy._claim_register = copy.copy(register)
                tour._recorded_process_capture(policy, snapshot)
                policy._claim_register = register
                policy.confirm_key_posted(key)
        return rows

    def test_revert_proof_without_the_effect_confirmation_no_sale_completes(self):
        """The first two sale confirmations of the tour, with and without.

        The full-lifetime Observe pins live in
        test_unaffordable_claim_tour_recorded (``test_s2a1_observe_goals_
        complete_on_their_confirmed_effect``), on the replay that module
        already runs; this prefix is the cheap revert-proof of the same
        closing path.
        """
        limit = TOUR_EARLY_SALES[-1] + 1
        rows = self.tour_rows(limit=limit)
        completed = [
            row["index"] for row in rows
            if (row.get("closed_claim") or {}).get("closed_reason") == "sale-observed"
        ]
        self.assertEqual(completed, list(TOUR_EARLY_SALES))
        original = HengbotPolicy._complete_observed_effect
        HengbotPolicy._complete_observed_effect = lambda self, label: None
        try:
            reverted = self.tour_rows(limit=limit)
        finally:
            HengbotPolicy._complete_observed_effect = original
        self.assertEqual(
            [row["index"] for row in reverted
             if (row.get("closed_claim") or {}).get("closed_reason")
             == "sale-observed"],
            [],
        )
        # and the decisions themselves did not move
        self.assertEqual(
            [(row["key"], row["reason"]) for row in rows],
            [(row["key"], row["reason"]) for row in reverted],
        )


# -- B3 ----------------------------------------------------------------------


def _claim_row(claim_id, owner, kind, *, cell=None, closed=None,
               closed_claim=None, reason=None, position=(0, 0),
               goal_missing=False, survival=None, session="s"):
    if kind == "Reach":
        goal = {"kind": "Reach", "cell": list(cell or (9, 9))}
    elif kind == "Observe":
        goal = {"kind": "Observe", "expectation": ["floor"], "within": 350}
    else:
        goal = {"kind": "Terminal", "effect": reason or owner}
    row = {
        "kind": "claim", "session": session, "claim_id": claim_id,
        "owner": owner, "producer": owner, "goal": goal, "closed": closed,
        "closed_claim": closed_claim, "reason": reason or owner,
        "position": None if position is None
        else {"y": position[0], "x": position[1]},
        "goal_missing": goal_missing,
    }
    if survival is not None:
        row["survival"] = survival
    return row


class GateNumbersTest(unittest.TestCase):
    """B3: the four numbers on small constructed ledgers."""

    def test_a_counts_an_owner_change_that_left_a_goal_unclosed(self):
        rows = [
            _claim_row(1, "store-router", "Reach"),
            _claim_row(2, "home-visit", "Terminal"),            # (a) +1
            _claim_row(3, "positioning", "Reach"),              # Terminal before
            _claim_row(4, "combat", "Terminal", closed_claim={
                "claim_id": 3, "goal_kind": "Reach", "state": "active",
                "closed": "release", "closed_reason": "x"}),   # released
            _claim_row(5, "departure", "Observe"),
            _claim_row(6, "escape", "Terminal", reason="emergency:teleport",
                       closed_claim={"claim_id": 5, "goal_kind": "Observe",
                                     "state": "suspended", "closed": None}),
            _claim_row(7, "explore", "Reach"),
            _claim_row(8, "escape", "Terminal", reason="unseen:choke-wait"),
        ]
        gate = gate_numbers(rows)
        self.assertEqual(gate["dropped_by_other_owner"],
                         {"count": 1, "pairs": {"store-router>home-visit": 1}})
        # survival rows never count, whichever side they are on
        self.assertEqual(gate["retargets"]["count"], 0)

    def test_b_counts_the_same_owner_forgetting_its_cell(self):
        rows = [
            _claim_row(1, "positioning", "Reach", cell=(2, 102)),
            _claim_row(1, "positioning", "Reach", cell=(2, 102)),
            _claim_row(2, "positioning", "Reach", cell=(5, 90)),  # (b) +1
            _claim_row(3, "positioning", "Reach", cell=(6, 91), closed_claim={
                "claim_id": 2, "goal_kind": "Reach", "state": "complete",
                "closed": "complete", "closed_reason": "reached"}),
        ]
        gate = gate_numbers(rows)
        self.assertEqual(gate["retargets"],
                         {"count": 1, "by_owner": {"positioning": 1}})
        self.assertEqual(gate["dropped_by_other_owner"]["count"], 0)

    def test_c_names_how_every_reach_and_observe_claim_ended(self):
        rows = [
            _claim_row(1, "floor-loot", "Reach"),
            _claim_row(2, "floor-loot", "Reach", closed_claim={
                "claim_id": 1, "goal_kind": "Reach", "state": "complete",
                "closed": "complete", "closed_reason": "loot-collected"}),
            _claim_row(3, "floor-loot", "Reach", closed_claim={
                "claim_id": 2, "goal_kind": "Reach", "state": "active",
                "closed": "release", "closed_reason": "loot-deferred"}),
            _claim_row(3, "floor-loot", "Reach", closed="retired"),
            _claim_row(4, "shop-buy", "Observe"),
            _claim_row(5, "escape", "Terminal", reason="emergency:phase",
                       closed_claim={"claim_id": 4, "goal_kind": "Observe",
                                     "state": "suspended", "closed": None}),
            _claim_row(6, "shop-buy", "Observe"),
            _claim_row(7, "store-router", "Reach", goal_missing=True),
            _claim_row(8, "store-router", "Terminal", goal_missing=True),
        ]
        gate = gate_numbers(rows)
        self.assertEqual(
            gate["endings"],
            {
                "floor-loot/Reach": dict.fromkeys(ENDINGS, 0) | {
                    "complete": 1, "release": 1, "retired": 1},
                "shop-buy/Observe": dict.fromkeys(ENDINGS, 0) | {
                    "suspended": 1, "abandoned": 1},
                "store-router/Reach": dict.fromkeys(ENDINGS, 0) | {
                    "abandoned": 1},
            },
        )
        self.assertEqual(gate["goal_missing"], {"store-router": 2})
        # a claim the last row still holds did not end inside the ledger
        tail = gate_numbers(rows[:1])
        self.assertEqual(tail["endings"]["floor-loot/Reach"]["open-at-end"], 1)

    def test_d_catches_a_multi_row_terminal_claim_that_moves(self):
        rows = [
            _claim_row(1, "fundraising", "Terminal", position=(5, 5),
                       reason="fundraise:dig-to-treasure"),
            _claim_row(1, "fundraising", "Terminal", position=(5, 6),
                       reason="fundraise:dig-to-treasure"),
            _claim_row(1, "fundraising", "Terminal", position=(5, 7),
                       reason="fundraise:dig-to-treasure"),
            _claim_row(2, "idle", "Terminal", position=(5, 7), reason="wait"),
            _claim_row(2, "idle", "Terminal", position=(5, 7), reason="wait"),
            _claim_row(3, "explore", "Terminal", position=None),
            _claim_row(3, "explore", "Terminal", position=None),
        ]
        gate = gate_numbers(rows)
        self.assertEqual(
            gate["mistyped_terminal"],
            {"count": 1, "by_owner": {"fundraising": 1}, "position_unknown": 1},
        )

    def test_a_terminal_claim_is_closed_when_it_is_posted(self):
        rows = [
            _claim_row(1, "combat", "Terminal", reason="melee"),
            _claim_row(2, "positioning", "Reach"),
        ]
        self.assertEqual(implicit_handoffs(rows)["implicit_handoffs"], 0)
        self.assertEqual(gate_numbers(rows)["dropped_by_other_owner"]["count"], 0)

    def test_the_report_prints_the_four_numbers(self):
        import ownership_metrics_report

        rows = [
            _claim_row(1, "store-router", "Reach"),
            _claim_row(2, "home-visit", "Terminal"),
        ]
        text = "\n".join(ownership_metrics_report.gate_report(rows, 1.0))
        self.assertIn("(a) owner changes with the previous Reach/Observe claim not closed", text)
        self.assertIn("store-router>home-visit", text)
        self.assertIn("(b) same owner replacing its unclosed Reach/Observe goal", text)
        self.assertIn("(c) how Reach/Observe claims ended", text)
        self.assertIn("store-router/Reach", text)
        self.assertIn("(d) multi-row Terminal claims whose position changed", text)

    def test_the_ledger_records_position_goal_missing_and_survival(self):
        with tempfile.TemporaryDirectory(prefix="s2a1-ledger-") as raw:
            root = Path(raw)
            ledger = OwnershipMetricsLedger(
                root / OWNERSHIP_METRICS_NAME, progress_interval_seconds=1e9
            )
            ledger.note_session_start({"time": "2026-09-24T06:00:00+0900"}, pid=1)
            ledger.note_decision({
                "reason": "shop:travel", "position": {"y": 3, "x": 4},
                "claim": {"claim_id": 1, "owner": "store-router",
                          "goal": {"kind": "Terminal", "effect": "shop:travel"},
                          "goal_missing": True, "survival": False,
                          "closed_reason": None},
            })
            record = read_records(root / OWNERSHIP_CLAIMS_NAME)[0]
        self.assertEqual(record["position"], {"y": 3, "x": 4})
        self.assertIs(record["goal_missing"], True)
        self.assertIs(record["survival"], False)


# -- B4 ----------------------------------------------------------------------


class NeutralityTest(unittest.TestCase):
    """B4: the register on or off, the decisions are the same."""

    def test_the_dungeon_replay_decides_identically_with_and_without_claims(self):
        skill, boards = _Replay.dungeon_boards()
        with tempfile.TemporaryDirectory(prefix="s2a1-off-") as off, \
                tempfile.TemporaryDirectory(prefix="s2a1-on-") as on:
            without, _ = _Replay.run(Path(off), skill, boards, register=False)
            with_, _ = _Replay.run(Path(on), skill, boards, register=True)
        self.assertEqual(
            [(str(key), reason) for key, reason in without],
            [(str(key), reason) for key, reason in with_],
        )

    def test_the_slot_and_the_closings_are_record_only(self):
        """No producer reads the slot: blanking it changes no decision."""
        original = HengbotPolicy._declare_reach
        HengbotPolicy._declare_reach = lambda self, cell: None
        try:
            skill, boards = _Replay.dungeon_boards()
            with tempfile.TemporaryDirectory(prefix="s2a1-noslot-") as raw:
                blank, _ = _Replay.run(Path(raw), skill, boards, register=True)
        finally:
            HengbotPolicy._declare_reach = original
        rows = ClosingPathsTest.dungeon_rows()
        self.assertEqual(
            [(str(key), reason) for key, reason in blank],
            [(row["key"], row["reason"]) for row in rows],
        )


# -- B5 ----------------------------------------------------------------------


class SurvivalConstantTest(unittest.TestCase):
    """B5: survival is exactly the user's list, and only it suspends."""

    def test_the_constant_is_the_design_list(self):
        self.assertEqual(SURVIVAL_REASON_PREFIXES, DESIGN_SURVIVAL_PREFIXES)
        self.assertEqual(set(SURVIVAL_RETURN_TRIGGERS), DESIGN_SURVIVAL_TRIGGERS)
        self.assertTrue(is_survival("return:recall", "emergency-low-hp"))
        self.assertTrue(is_survival("return:seek-upstairs", "esp-threat"))
        self.assertFalse(is_survival("return:recall", "pack-full"))
        self.assertFalse(is_survival("return:recall", None))
        self.assertTrue(is_survival("esp-threat:leave-stairs"))

    def test_no_ordinary_owner_is_survival(self):
        for reason in DESIGN_ORDINARY_REASONS:
            with self.subTest(reason=reason):
                self.assertFalse(is_survival(reason, "emergency-low-hp"))
        for prefix in ORDINARY_OWNER_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertFalse(is_survival(prefix))

    def test_suspend_has_one_caller_behind_the_survival_constant(self):
        callers = []
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for function in ast.walk(tree):
                if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(function):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "suspend"
                    ):
                        callers.append((path.name, function.name))
        self.assertEqual(callers, [("policy.py", "_record_decision_claim")])

    def _standing_reach(self, policy, board):
        register = policy._claim_register
        register.declare(
            ClaimOwner.FLOOR_LOOT, reach((1, 1)), floor=board.floor_key
        )
        return register.current

    def test_survival_suspends_the_standing_goal_and_ordinary_does_not(self):
        board = _town_board()
        for reason, suspended in (
            ("emergency:teleport", True),
            ("combat:disengage-step", True),
            ("flee", False),
            ("threat:scroll", False),
        ):
            with self.subTest(reason=reason):
                policy = _fresh_policy(board)
                standing = self._standing_reach(policy, board)
                policy.last_reason = reason
                policy._record_decision_claim(board, "r")
                closed = policy.decision_claim["closed_claim"]
                if suspended:
                    self.assertEqual(closed["claim_id"], standing.claim_id)
                    self.assertEqual(closed["state"], "suspended")
                    self.assertEqual(closed["closed_reason"], "survival-preemption")
                    self.assertTrue(policy.decision_claim["survival"])
                else:
                    self.assertIsNone(closed)
                    self.assertFalse(policy.decision_claim["survival"])


# -- restored checkpoints ----------------------------------------------------


class RestoredCheckpointTest(unittest.TestCase):
    """Every attribute S2a.1 adds or newly reads survives an older pickle."""

    NEW_POLICY_ATTRIBUTES = (
        "_decision_goal", "_decision_expectation", "_hunt_step_target",
    )

    def test_a_pre_s2a1_claim_goal_register_and_registry_unpickle(self):
        register = ClaimRegister()
        claim = register.declare(ClaimOwner.EXPLORE, reach((3, 4)))
        # Reproduce the pre-S2a.1 state: none of the new fields was pickled.
        for name in ("floor", "closed_reason", "survival"):
            object.__delattr__(claim, name)
        object.__delattr__(claim.goal, "source")
        del register.__dict__["_closing"]
        registry = OwnerExpectationRegistry()
        del registry.__dict__["_pops"]

        restored_register = pickle.loads(pickle.dumps(register))
        restored_registry = pickle.loads(pickle.dumps(registry))
        restored = restored_register.current
        self.assertIsNone(restored.floor)
        self.assertIsNone(restored.closed_reason)
        self.assertFalse(restored.survival)
        self.assertIsNone(restored.goal.source)
        self.assertTrue(restored.is_open)
        self.assertIsNone(restored_register.take_closing())
        restored_register.complete("reached")
        self.assertEqual(restored_register.take_closing().closed_reason, "reached")
        self.assertEqual(restored_registry.drain_pops(), [])

    def test_the_legacy_checkpoint_restores_the_new_slots_and_decides(self):
        with gzip.open(LEGACY_CHECKPOINT, "rt", encoding="utf-8") as stream:
            capture = json.load(stream)
        producer = capture["sequence"][0]
        snapshot = pickle.loads(
            base64.b64decode(capture["snapshots_pickle_b64"][producer["snapshot_id"]])
        )
        state = pickle.loads(base64.b64decode(capture["producer_checkpoint_pickle_b64"]))
        for name in self.NEW_POLICY_ATTRIBUTES:
            self.assertNotIn(name, state)
        registry = state.get("_owner_expectations")
        if registry is not None:
            self.assertNotIn("_pops", registry.__dict__)

        restored = restore_checkpoint(
            HengbotPolicy, capture["producer_checkpoint_pickle_b64"]
        )
        for name in self.NEW_POLICY_ATTRIBUTES:
            self.assertIsNone(restored.__dict__[name])
        self.assertIsNone(restored._claim_register.__dict__["_closing"])
        if restored._owner_expectations is not None:
            self.assertEqual(restored._owner_expectations.__dict__["_pops"], [])
        self.assertEqual(
            (restored.choose_key(snapshot), restored.last_reason),
            (producer["expected_key"], producer["expected_reason"]),
        )
        self.assertIn("goal_missing", restored.decision_claim)
        self.assertIn("survival", restored.decision_claim)

    def test_an_s1_register_inside_a_checkpoint_declares_and_closes(self):
        """A restored S1-era register (claims without the new fields)."""
        with gzip.open(LEGACY_CHECKPOINT, "rt", encoding="utf-8") as stream:
            capture = json.load(stream)
        producer = capture["sequence"][0]
        snapshot = pickle.loads(
            base64.b64decode(capture["snapshots_pickle_b64"][producer["snapshot_id"]])
        )
        state = pickle.loads(base64.b64decode(capture["producer_checkpoint_pickle_b64"]))
        register = ClaimRegister()
        claim = register.declare(
            ClaimOwner.STORE_ROUTER,
            reach((snapshot.player.position.y, snapshot.player.position.x)),
        )
        for name in ("floor", "closed_reason", "survival"):
            object.__delattr__(claim, name)
        del register.__dict__["_closing"]
        state["_claim_register"] = register
        encoded = base64.b64encode(pickle.dumps(state)).decode("ascii")

        restored = restore_checkpoint(HengbotPolicy, encoded)
        key = restored.choose_key(snapshot)
        self.assertEqual(
            (key, restored.last_reason),
            (producer["expected_key"], producer["expected_reason"]),
        )
        # the S1 claim's cell is where the board stands: it closes, reached
        self.assertEqual(
            restored.decision_claim["closed_claim"]["closed_reason"], "reached"
        )


if __name__ == "__main__":
    unittest.main()
