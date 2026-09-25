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

Round 3 (design rev 9.3): R1 ``ReadOnlySatisfactionTest``, R2
``FarTargetCaptureTest`` and the tour's next-row pin, R3/R4
``SurvivalTriggerStartOnlyTest``, R5 ``LastKnownCellTest``, R6
``HomeEffectSourceTest``, R7 ``TeleportAdoptionTest``.

Round 4: F1 ``ReservedChestCellTest``, F2 ``OneStepNoteTest``, F3
``CaptureRobustnessTest``, F4 ``CachedUpstairsTargetTest``.

Restored checkpoints: every attribute S2a.1 adds or newly reads is covered
(``RestoredCheckpointTest``).

Round 2 (design rev 9.2, the two reviews of 1ae6c198)
-----------------------------------------------------
T1/T2  every Reach reason site writes its slot, or its row is retyped
       (``GoalTypingTableTest.test_every_reach_reason_site_writes_its_slot``).
C      both slots carry the writer's family; another owner's slot is not used
       (``owner-mismatch``) -- ``DeclaredGoalSlotTest``; the B1 revert-proof
       now restores the shared-state scan *inside* the real ``_claim_goal``.
M      a chase is a claim on a monster identity (``MovingTargetTest``).
O, E   the read-only satisfaction test, the three pop paths, expiry, and the
       floor change outside the tour (``ObserveClosingTest``).
U      closings name their owners and sources (``ClosingOwnershipTest``).
S      survival reads the trigger this return began with
       (``SurvivalTriggerTest``).
P      a suspended claim does not continue (``SuspendedClaimTest``).
D      (d) excludes goal_missing rows, printed apart (``GoalMissingMetricTest``).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare runs

import ast
import base64
import re
import copy
import gzip
import json
import pickle
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.claim_goal_typing import (
    FLOOR_CHANGE,
    HOME_EFFECT_OWNERS,
    HOME_EFFECT_SOURCES,
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
    observe,
    reach,
    reach_monster,
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
# Rev 9.3 removed ``guardian-reposition``: it never starts a return.
DESIGN_SURVIVAL_TRIGGERS = {"esp-threat", "unseen-attacker"}
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

    # A reason site writes its Reach slot through one of these (or through
    # the store router / travel / teleport helpers, which declare inside).
    SLOT_WRITERS = (
        "_declare_", "_adopt_decision_goal", "_shopping_approach_key(",
        "_stage_shopping_approach_key(", "_town_travel_key(",
        "_commit_boxed_town_breakout_key(",
    )

    def test_every_reach_reason_site_writes_its_slot(self):
        """Rev 9.2 (T1/T2): no Reach row is left without a slot writer."""
        assign = re.compile(r'self\.last_reason\s*=\s*(f?)"([^"]*)"')
        unwritten = []
        for path in sorted(PACKAGE.glob("policy*.py")):
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                match = assign.search(line)
                if not match:
                    continue
                literal = match.group(2)
                if match.group(1):
                    literal = literal.split("{")[0]
                row = goal_typing(reason_owner_family(literal), literal)
                if row is None or row.kind != "Reach":
                    continue
                window = "\n".join(lines[max(0, index - 3):index + 5])
                if not any(writer in window for writer in self.SLOT_WRITERS):
                    unwritten.append(f"{path.name}:{index + 1} {literal}")
        self.assertEqual(unwritten, [])

    def test_the_rev92_rows_have_the_design_kind(self):
        for reason, kind in (
            ("calibration:restore-travel", "Reach"),
            ("survival:shop-travel", "Reach"),
            ("survival:mana-home-travel", "Reach"),
            ("equipment-transaction:acquire-home-catalog", "Reach"),
            ("shop:observe-and-leave", "Terminal"),
            ("wilderness:global-travel", "Reach"),
            ("quest-strategy:approach-throw-point", "Reach"),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(
                    goal_typing(reason_owner_family(reason), reason).kind, kind
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
    """B1: a decision's goal comes only from what its own owner wrote."""

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

    def _assert_no_row_carries_a_borrowed_cell(self):
        """The pin: stale shared goals reach no row, of either kind."""
        board = _town_board()
        for reason, kind in (("town:wait-recall", "Observe"),
                             ("shop:travel", "Terminal")):
            policy = _fresh_policy(board)
            self._stale_shared_state(policy)
            policy._decision_goal = None
            policy._decision_expectation = None
            claim = self._declare(policy, board, reason)
            self.assertEqual(claim["goal"]["kind"], kind, reason)
            self.assertNotIn("cell", claim["goal"], reason)

    def test_no_row_carries_a_cell_its_producer_did_not_write(self):
        self._assert_no_row_carries_a_borrowed_cell()

    def test_a_stale_store_goal_cannot_type_a_recall_wait(self):
        board = _town_board()
        policy = _fresh_policy(board)
        self._stale_shared_state(policy)
        policy._decision_goal = None
        policy._decision_expectation = None
        claim = self._declare(policy, board, "town:wait-recall")
        self.assertEqual(claim["goal"]["kind"], "Observe")
        self.assertEqual(claim["goal"]["source"], FLOOR_CHANGE)
        self.assertFalse(claim["goal_missing"])
        self.assertIsNone(claim["goal_note"])

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
        self.assertEqual(claim["goal_note"], "no-slot")

    def test_a_slot_of_another_owner_is_not_used(self):
        """Rev 9.2 (C): the slot's family must be the row's owner."""
        board = _town_board()
        policy = _fresh_policy(board)
        policy.last_reason = "shop:approach"            # store-router writes
        policy._declare_reach(Position(41, 131))
        # a later rewrite hands the decision to another owner's Reach row
        claim = self._declare(policy, board, "town:seek-shelter")
        self.assertEqual(claim["owner"], "survival")
        self.assertEqual(claim["goal"]["kind"], "Terminal")
        self.assertTrue(claim["goal_missing"])
        self.assertEqual(claim["goal_note"], "owner-mismatch")

    def test_a_same_owner_rewrite_keeps_the_producers_slot(self):
        board = _town_board()
        policy = _fresh_policy(board)
        policy.last_reason = "shop:approach"
        policy._declare_reach(Position(41, 131))
        claim = self._declare(policy, board, "shop:travel")
        self.assertEqual(claim["goal"], {"kind": "Reach", "cell": [41, 131]})
        self.assertIsNone(claim["goal_note"])

    def test_a_shared_helper_stamps_the_errand_it_runs(self):
        """The router stamps ``travel_reason``'s family, not a stale reason.

        policy_calibration's restore walk calls the router without setting
        a reason; the slot names calibration, so a row still carrying the
        previous decision's reason of another owner cannot use it.
        """
        board = _town_board()
        policy = _fresh_policy(board)
        policy.last_reason = "periodic:game-save"        # stale, bookkeeping
        policy._declare_reach(
            Position(41, 131), family=policy._claim_family_of("calibration:restore-travel")
        )
        claim = self._declare(policy, board, "calibration:restore-travel")
        self.assertEqual(claim["goal"], {"kind": "Reach", "cell": [41, 131]})
        policy = _fresh_policy(board)
        policy._declare_reach(
            Position(41, 131), family=policy._claim_family_of("calibration:restore-travel")
        )
        claim = self._declare(policy, board, "shop:approach")
        self.assertEqual(claim["goal_note"], "owner-mismatch")

    def test_an_expectation_of_another_owner_is_not_used(self):
        """Rev 9.2 (C): a town-plan expectation does not type an equipment row."""
        board = _town_board()
        policy = _fresh_policy(board)
        policy.last_reason = "town:blocked:equipment-transaction:withdraw"
        policy._post_owner_expectation(
            board, "town:blocked:equipment-transaction:withdraw",
            "inventory", "equipment",
        )
        claim = self._declare(policy, board, "equipment-transaction:takeoff")
        self.assertEqual(claim["owner"], "equipment-txn")
        self.assertEqual(claim["goal"]["kind"], "Observe")
        self.assertEqual(claim["goal"]["source"], "transaction")
        self.assertEqual(claim["goal_note"], "owner-mismatch")
        # and the owner's own posted expectation is used
        policy = _fresh_policy(board)
        policy.last_reason = "equipment-transaction:takeoff"
        policy._post_owner_expectation(
            board, "equipment-transaction", "inventory", "equipment"
        )
        claim = self._declare(policy, board, "equipment-transaction:takeoff")
        self.assertEqual(claim["goal"]["source"], "equipment-transaction")
        self.assertIsNone(claim["goal_note"])

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

    def test_revert_proof_the_scan_inside_the_real_claim_goal_is_caught(self):
        """Restore the S1 scan inside the production path; the pin fails.

        The real ``_claim_goal`` runs; the revert only puts the deleted
        shared-state scan back as its slot source (stamped with the row's
        owner, as the scan never asked whose cell it was).
        """

        def s1_scan(policy):
            visit = getattr(policy, "_store_visit", None)
            if visit is not None and isinstance(visit.goal, Position):
                return visit.goal
            dark = getattr(policy, "_dark_route_goal", None)
            return dark if isinstance(dark, Position) else None

        original = HengbotPolicy._claim_goal

        def reverted(self, snapshot, key, owner, reason, standing):
            cell = s1_scan(self)
            if cell is not None:
                self._decision_goal = (owner.value, reach((cell.y, cell.x)))
            return original(self, snapshot, key, owner, reason, standing)

        HengbotPolicy._claim_goal = reverted
        try:
            with self.assertRaises(AssertionError):
                self._assert_no_row_carries_a_borrowed_cell()
        finally:
            HengbotPolicy._claim_goal = original
        self.assertIs(HengbotPolicy._claim_goal, original)
        self._assert_no_row_carries_a_borrowed_cell()


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
        # S2b.1 (design rev 10.1): with no closing call left, the explore
        # walk is still open when positioning takes the decision, and
        # positioning ranks above explore -- a ladder preemption, which does
        # not go through ``_claim_close``.  It is the only closing left.
        self.assertEqual(
            _closings(rows),
            [(2, "explore", "Reach", "suspended", "preempted-by:positioning")],
        )
        # the closings are record-only: the decisions did not move
        self.assertEqual(
            [(row["key"], row["reason"]) for row in rows],
            [(row["key"], row["reason"]) for row in self.dungeon_rows()],
        )
        gate = gate_numbers(rows)
        self.assertNotEqual(
            _endings_subset(gate, DUNGEON_ENDINGS), DUNGEON_ENDINGS
        )
        # the unclosed Reach claims are what (a) counts; S2b.1: the explore
        # walk positioning took over is suspended (a preemption, above), so
        # only positioning>combat is left unclosed
        self.assertEqual(
            gate["dropped_by_other_owner"]["pairs"],
            {"positioning>combat": 1},
        )
        self.assertEqual(implicit_handoffs(rows)["implicit_handoffs"], 1)

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
        HengbotPolicy._complete_observed_effect = (
            lambda self, label, **scope: None
        )
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


# -- rev 9.2 -----------------------------------------------------------------


def _dungeon_board(index):
    _skill, boards = _Replay.dungeon_boards()
    return parse_snapshot(boards[index], _Replay.knowledge())


def _standing(policy, owner, goal, board, **fields):
    """Put one declared claim in the register, as the previous row left it."""
    register = policy._claim_register
    register.declare(
        owner, goal, floor=board.floor_key,
        opened_sequence=fields.get("opened_sequence", policy._decision_sequence),
        opened_turn=fields.get("opened_turn", board.turn),
    )
    register.take_closing()
    return register.current


def _exit(policy, board, reason, key="5"):
    policy.last_reason = reason
    policy._record_decision_claim(board, key)
    return policy.decision_claim


class MovingTargetTest(unittest.TestCase):
    """Rev 9.2 (M): a chase is a claim on a monster, not on its cell."""

    ADJACENT = (74, 111)   # visible and adjacent on dungeon board 5

    def test_the_goal_is_the_identity_and_continues_while_it_is_unchanged(self):
        board = _dungeon_board(5)
        far = next(
            (monster.index, monster.race_id)
            for monster in board.detected_monsters
            if board.player.position.distance_to(monster.position) > 1
        )
        policy = _fresh_policy(board)
        claims = []
        for _ in range(2):
            policy.last_reason = "hunt"
            policy._declare_monster(far)
            claims.append(_exit(policy, board, "hunt", "1"))
        self.assertEqual(claims[0]["goal"], {"kind": "Reach", "monster": list(far)})
        self.assertEqual(claims[0]["claim_id"], claims[1]["claim_id"])
        self.assertIsNone(claims[1]["closed_claim"])
        self.assertGreater(claims[0]["distance"], 1)
        # off the board it was perceived on, the chase is released
        policy._decision_goal = None
        claim = _exit(policy, _dungeon_board(0), "explore", "4")
        if far not in {
            (monster.index, monster.race_id)
            for monster in (*_dungeon_board(0).visible_monsters,
                            *_dungeon_board(0).detected_monsters)
        }:
            self.assertEqual(claim["closed_claim"]["closed_reason"], "target-lost")

    def test_arrival_completes_for_whichever_chaser_holds_it(self):
        for owner in (ClaimOwner.HUNT, ClaimOwner.DEPARTURE, ClaimOwner.SURVIVAL):
            with self.subTest(owner=owner.value):
                board = _dungeon_board(5)
                policy = _fresh_policy(board)
                _standing(policy, owner, reach_monster(*self.ADJACENT), board)
                claim = _exit(policy, board, "melee", "1")
                self.assertEqual(claim["closed_claim"]["closed"], "complete")
                self.assertEqual(
                    claim["closed_claim"]["closed_reason"], "target-adjacent"
                )

    def test_the_melee_switch_closes_the_chase_in_its_own_branch(self):
        """The producer's arrival branch: melee begins on the chased monster."""
        skill, boards = _Replay.dungeon_boards()
        policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
        policy.consume_skill_knowledge(skill)
        for raw in boards[:5]:
            board = parse_snapshot(raw, _Replay.knowledge())
            policy.confirm_key_posted(
                policy.validate_read_key(board, policy.choose_key(board))
            )
        board = parse_snapshot(boards[5], _Replay.knowledge())
        _standing(policy, ClaimOwner.DEPARTURE, reach_monster(*self.ADJACENT), board)
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("1", "melee"))
        self.assertEqual(
            policy.decision_claim["closed_claim"]["closed_reason"],
            "closed-to-melee",
        )

    def test_a_monster_that_left_perception_releases(self):
        board = _dungeon_board(5)
        policy = _fresh_policy(board)
        _standing(policy, ClaimOwner.HUNT, reach_monster(9999, 1), board)
        claim = _exit(policy, board, "explore")
        self.assertEqual(claim["closed_claim"]["closed"], "release")
        self.assertEqual(claim["closed_claim"]["closed_reason"], "target-lost")


class ObserveClosingTest(unittest.TestCase):
    """Rev 9.2 (O, E) and the registry's pop paths, outside the tour."""

    def _posted(self, policy, board_posted, owner="expect-x", changes=("position",), core=None):
        core = core or policy._owner_progress_core(board_posted)
        policy._owner_expectations.post(owner, core, *changes)
        return observe(changes, 10, source=owner)

    def test_a_satisfied_expectation_completes_without_a_pop(self):
        before, after = _dungeon_board(0), _dungeon_board(1)
        policy = _fresh_policy(after)
        goal = self._posted(policy, before)
        _standing(policy, ClaimOwner.EQUIPMENT_TXN, goal, after)
        claim = _exit(policy, after, "melee", "1")
        self.assertEqual(claim["closed_claim"]["closed_reason"], "expectation-satisfied")
        # read-only: the registry still holds it, nobody popped it
        self.assertIsNotNone(policy._owner_expectations.pending("expect-x"))
        self.assertEqual(policy._owner_expectations.drain_pops(), [])

    def test_revert_proof_without_the_read_only_test_nothing_completes(self):
        before, after = _dungeon_board(0), _dungeon_board(1)
        original = OwnerExpectationRegistry.verdict
        OwnerExpectationRegistry.verdict = lambda self, owner, core: None
        try:
            policy = _fresh_policy(after)
            goal = self._posted(policy, before)
            _standing(policy, ClaimOwner.EQUIPMENT_TXN, goal, after)
            claim = _exit(policy, after, "melee", "1")
        finally:
            OwnerExpectationRegistry.verdict = original
        self.assertIsNone(claim["closed_claim"])

    def test_the_satisfied_pop_completes_and_the_other_pops_do_not(self):
        before, after = _dungeon_board(0), _dungeon_board(1)
        for why, expected in (("satisfied", "expectation-satisfied"),
                              ("expired", None), ("floor", None)):
            with self.subTest(pop=why):
                policy = _fresh_policy(after)
                core = policy._owner_progress_core(before)
                if why == "expired":
                    core = replace(core, decision_sequence=core.decision_sequence - 10)
                if why == "floor":
                    core = replace(core, floor=(9, 9, 9))
                changes = ("position",) if why == "satisfied" else ("hp",)
                goal = self._posted(policy, before, changes=changes, core=core)
                _standing(policy, ClaimOwner.EQUIPMENT_TXN, goal, after)
                policy._owner_may_select(after, "expect-x")
                claim = _exit(policy, after, "melee", "1")
                closed = claim["closed_claim"]
                self.assertEqual(
                    None if closed is None else closed["closed_reason"], expected
                )

    def test_an_observe_older_than_within_expires(self):
        board = _dungeon_board(1)
        policy = _fresh_policy(board)
        policy._decision_sequence = 30
        _standing(policy, ClaimOwner.SHOP_BUY,
                  observe(("store-operation",), 8, source="store-operation"),
                  board, opened_sequence=22)
        claim = _exit(policy, board, "explore")
        self.assertEqual(claim["closed_claim"]["closed"], "expired")
        policy = _fresh_policy(board)
        policy._decision_sequence = 30
        _standing(policy, ClaimOwner.SHOP_BUY,
                  observe(("store-operation",), 8, source="store-operation"),
                  board, opened_sequence=23)
        self.assertIsNone(_exit(policy, board, "explore")["closed_claim"])

    def test_a_floor_change_completes_and_a_long_wait_expires(self):
        board = _dungeon_board(1)
        floor_goal = observe(("floor",), 350, source=FLOOR_CHANGE)
        policy = _fresh_policy(board)
        policy._claim_register.declare(
            ClaimOwner.DEPARTURE, floor_goal, floor=(0, 0, 0),
            opened_turn=board.turn,
        )
        claim = _exit(policy, board, "explore")
        self.assertEqual(claim["closed_claim"]["closed_reason"], "floor-changed")
        for age, closed in ((351, "expired"), (350, None)):
            with self.subTest(age=age):
                policy = _fresh_policy(board)
                _standing(policy, ClaimOwner.DEPARTURE, floor_goal, board,
                          opened_turn=board.turn - age)
                finished = _exit(policy, board, "explore")["closed_claim"]
                self.assertEqual(
                    None if finished is None else finished["closed"], closed
                )

    def test_expired_is_its_own_ending(self):
        rows = [
            _claim_row(1, "shop-buy", "Observe"),
            _claim_row(2, "explore", "Terminal", closed_claim={
                "claim_id": 1, "goal_kind": "Observe", "state": "active",
                "closed": "expired", "closed_reason": "within-exceeded"}),
        ]
        gate = gate_numbers(rows)
        self.assertEqual(gate["endings"]["shop-buy/Observe"]["expired"], 1)
        self.assertEqual(gate["endings"]["shop-buy/Observe"]["abandoned"], 0)
        self.assertEqual(gate["dropped_by_other_owner"]["count"], 0)


class ClosingOwnershipTest(unittest.TestCase):
    """Rev 9.2 (U): a closing names the owner (and source) it closes."""

    def test_a_confirmation_cannot_complete_another_owners_claim(self):
        board = _town_board()
        for owner, closed in ((ClaimOwner.DEPARTURE, None),
                              (ClaimOwner.SHOP_BUY, "complete")):
            with self.subTest(owner=owner.value):
                policy = _fresh_policy(board)
                _standing(policy, owner,
                          observe(("store-operation",), 8, source="store-operation"),
                          board)
                policy._complete_observed_effect(
                    "purchase-observed",
                    owners=(ClaimOwner.SHOP_BUY,),
                    sources=("store-operation",),
                )
                self.assertEqual(policy._claim_register.current.closed, closed)

    def test_a_source_mismatch_closes_nothing(self):
        board = _town_board()
        policy = _fresh_policy(board)
        _standing(policy, ClaimOwner.SHOP_BUY,
                  observe(("floor",), 350, source=FLOOR_CHANGE), board)
        policy._complete_observed_effect(
            "purchase-observed", owners=(ClaimOwner.SHOP_BUY,),
            sources=("store-operation",),
        )
        self.assertIsNone(policy._claim_register.current.closed)

    def test_a_release_names_its_owners(self):
        board = _town_board()
        cell = Position(3, 4)
        for owner, closed in ((ClaimOwner.POSITIONING, None),
                              (ClaimOwner.FLOOR_LOOT, "release")):
            with self.subTest(owner=owner.value):
                policy = _fresh_policy(board)
                _standing(policy, owner, reach((3, 4)), board)
                policy._release_claim_goal(
                    "loot-deferred", cell,
                    owners=("floor-loot", "fundraising", "departure"),
                )
                self.assertEqual(policy._claim_register.current.closed, closed)

    def test_every_closing_call_names_its_owners(self):
        missing = []
        for path in sorted(PACKAGE.glob("policy*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {
                        "_release_claim_goal", "_complete_claim_goal",
                        "_complete_observed_effect", "_claim_close",
                    }
                    and not any(k.arg == "owners" for k in node.keywords)
                ):
                    missing.append(f"{path.name}:{node.lineno}")
        self.assertEqual(missing, [])


class SurvivalTriggerTest(unittest.TestCase):
    """Rev 9.2 (S): survival reads the trigger *this* return began with."""

    def test_a_stale_last_trigger_does_not_make_a_return_survival(self):
        board = _dungeon_board(1)
        policy = _fresh_policy(board)
        policy._last_return_trigger = "esp-threat"     # a return long ago
        policy._note_return_start(None)                # this return: no trigger
        policy._returning_to_town = True
        self.assertFalse(_exit(policy, board, "return:seek-upstairs", "4")["survival"])

    def test_the_trigger_of_this_return_is_kept_and_cleared_at_its_end(self):
        board = _dungeon_board(1)
        policy = _fresh_policy(board)
        policy._note_return_start("emergency-low-hp")
        policy._returning_to_town = True
        self.assertTrue(_exit(policy, board, "return:seek-upstairs", "4")["survival"])
        policy._note_return_start(None)                # re-asserted latch
        self.assertEqual(policy._survival_return_trigger, "emergency-low-hp")
        policy._returning_to_town = False
        policy._note_return_end()
        self.assertFalse(_exit(policy, board, "return:seek-upstairs", "4")["survival"])

    def test_every_return_start_and_end_is_recorded(self):
        """Structural: each latch write is paired with its record-only note,
        and the returns that start without a trigger record ``None``."""
        unpaired, triggers = [], {}
        for path in sorted(PACKAGE.glob("policy*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for function in ast.walk(tree):
                if not isinstance(function, ast.FunctionDef):
                    continue
                for parent in ast.walk(function):
                    body = getattr(parent, "body", None)
                    if not isinstance(body, list):
                        continue
                    for index, stmt in enumerate(body):
                        if not (
                            isinstance(stmt, ast.Assign)
                            and len(stmt.targets) == 1
                            and isinstance(stmt.targets[0], ast.Attribute)
                            and stmt.targets[0].attr == "_returning_to_town"
                            and isinstance(stmt.value, ast.Constant)
                        ):
                            continue
                        if function.name == "__init__":
                            continue
                        where = f"{path.name}:{function.name}:{stmt.lineno}"
                        if stmt.value.value is True:
                            before = body[index - 1] if index else None
                            call = getattr(before, "value", None)
                            if not (
                                isinstance(call, ast.Call)
                                and getattr(call.func, "attr", "") == "_note_return_start"
                            ):
                                unpaired.append(where)
                            else:
                                triggers[where] = ast.unparse(call.args[0])
                        else:
                            after = body[index + 1] if index + 1 < len(body) else None
                            call = getattr(after, "value", None)
                            if not (
                                isinstance(call, ast.Call)
                                and getattr(call.func, "attr", "") == "_note_return_end"
                            ):
                                unpaired.append(where)
        self.assertEqual(unpaired, [])
        self.assertEqual(len(triggers), 30)
        for where, trigger in triggers.items():
            if (
                where.startswith("policy_fundraising.py:")
                or ":_victory_loot_key:" in where
            ):
                with self.subTest(site=where):
                    self.assertEqual(trigger, "None")
        breeder_walkout = [
            where for where in triggers
            if where.startswith("policy.py:_decide:")
            and triggers[where] == "None"
        ]
        self.assertTrue(breeder_walkout)


class SuspendedClaimTest(unittest.TestCase):
    """Rev 9.2 (P): a declaration after a suspension opens a new claim."""

    def test_a_suspended_claim_does_not_continue(self):
        register = ClaimRegister()
        first = register.declare(ClaimOwner.FLOOR_LOOT, reach((1, 2)))
        register.suspend("survival-preemption")
        again = register.declare(ClaimOwner.FLOOR_LOOT, reach((1, 2)))
        self.assertNotEqual(again.claim_id, first.claim_id)
        self.assertEqual(again.state.value, "active")


class GoalMissingMetricTest(unittest.TestCase):
    """Rev 9.2 (D): (d) excludes goal_missing rows; they print on their own."""

    ROWS = [
        _claim_row(1, "store-router", "Terminal", position=(5, 5),
                   reason="shop:travel", goal_missing=True),
        _claim_row(1, "store-router", "Terminal", position=(5, 6),
                   reason="shop:travel", goal_missing=True),
        _claim_row(1, "store-router", "Terminal", position=(5, 7),
                   reason="shop:travel", goal_missing=True),
    ]

    def test_d_excludes_goal_missing_rows_and_counts_them_apart(self):
        rows = [dict(row, goal_note="owner-mismatch") for row in self.ROWS]
        gate = gate_numbers(rows)
        self.assertEqual(gate["mistyped_terminal"]["count"], 0)
        self.assertEqual(gate["goal_missing"], {"store-router": 3})
        self.assertEqual(gate["goal_missing_by_reason"], {"owner-mismatch": 3})
        self.assertEqual(gate["owner_mismatch"], {"store-router": 3})

    def test_revert_proof_without_the_exclusion_d_counts_it(self):
        rows = [dict(row, goal_missing=False) for row in self.ROWS]
        self.assertEqual(gate_numbers(rows)["mistyped_terminal"]["count"], 1)

    def test_the_report_prints_goal_missing_and_owner_mismatch_lines(self):
        import ownership_metrics_report

        rows = [dict(row, goal_note="owner-mismatch") for row in self.ROWS]
        text = "\n".join(ownership_metrics_report.gate_report(rows, 1.0))
        self.assertIn("goal_missing rows (Reach declared Terminal)", text)
        self.assertIn("owner-mismatch=3", text)
        self.assertIn("owner-mismatch rows (a slot of another owner, not used)", text)


# -- rev 9.3 -----------------------------------------------------------------


class ReadOnlySatisfactionTest(unittest.TestCase):
    """Rev 9.3 (R1): the exit's Observe test leaves the arbiter untouched."""

    def _arbiter_state_after_exit(self):
        before_board, board = _dungeon_board(0), _dungeon_board(1)
        policy = _fresh_policy(board)
        policy._owner_expectations.post(
            "expect-x", policy._progress_core_of(before_board), "hp"
        )
        _standing(policy, ClaimOwner.EQUIPMENT_TXN,
                  observe(("hp",), 10, source="expect-x"), board)
        arbiter = policy._town_turn_arbiter
        arbiter._snapshot_turn = board.turn - 12345
        arbiter._snapshot_recalling = True
        arbiter._recall_wait_started_turn = 7
        before = pickle.dumps(arbiter.__dict__)
        policy._claim_exit_completion(board, policy._claim_register.current, [])
        return before, pickle.dumps(arbiter.__dict__)

    def test_the_arbiter_is_byte_identical_around_the_exit_test(self):
        before, after = self._arbiter_state_after_exit()
        self.assertEqual(before, after)

    def test_revert_proof_the_noting_core_would_rewrite_the_arbiter(self):
        original = HengbotPolicy._progress_core_of

        def noting(self, snapshot):
            # round 2's core: it told the arbiter about the board first
            self._town_turn_arbiter.note_snapshot(
                turn=snapshot.turn, recalling=snapshot.player.recalling
            )
            return original(self, snapshot)

        HengbotPolicy._progress_core_of = noting
        try:
            before, after = self._arbiter_state_after_exit()
        finally:
            HengbotPolicy._progress_core_of = original
        self.assertNotEqual(before, after)


class FarTargetCaptureTest(unittest.TestCase):
    """Rev 9.3 (R2): an armed path helper hands over the target it chose."""

    def test_an_armed_capture_receives_the_target_and_is_removed(self):
        board = _town_board()
        policy = _fresh_policy(board)

        def far(grid):
            return board.player.position.distance_to(grid.position) >= 3

        route = policy._nearest_goal_route(board, far)
        self.assertIsNotNone(route)
        policy._claim_target_capture = []
        step = policy._nearest_goal_step(board, far)
        self.assertEqual(policy._take_claim_target(), route.target)
        self.assertEqual(step, route.first_step)
        target = route.target
        self.assertNotIn("_claim_target_capture", policy.__dict__)
        self.assertIsNotNone(step)
        self.assertNotEqual(step, target)

    def test_an_unarmed_helper_writes_nothing(self):
        board = _dungeon_board(0)
        policy = _fresh_policy(board)
        state = dict(policy.__dict__)
        policy._nearest_goal_step(board, lambda grid: grid.has_up_stairs)
        policy._nearest_position_step(board, {board.player.position})
        policy._secret_wall_search_step(board)
        self.assertEqual(set(policy.__dict__), set(state))
        self.assertIsNone(policy._take_claim_target())

    def test_a_replaced_helper_declares_no_goal(self):
        board = _dungeon_board(0)
        policy = _fresh_policy(board)
        policy._claim_target_capture = []
        self.assertIsNone(policy._take_claim_target())


class SurvivalTriggerStartOnlyTest(unittest.TestCase):
    """Rev 9.3 (R3, R4): the trigger is the one the running return began with."""

    def test_an_emergency_during_an_ordinary_return_does_not_make_it_survival(self):
        board = _dungeon_board(1)
        policy = _fresh_policy(board)
        policy._note_return_start(None)                 # an ordinary return
        policy._returning_to_town = True
        policy._note_return_start("emergency-lethal-swarm")  # emergency during it
        policy._returning_to_town = True
        self.assertIsNone(policy._survival_return_trigger)
        self.assertFalse(_exit(policy, board, "return:seek-upstairs", "4")["survival"])
        # the emergency's own rows are survival by prefix
        self.assertTrue(_exit(policy, board, "emergency:teleport", "r")["survival"])

    def test_revert_proof_a_running_return_rewritten_by_a_named_trigger(self):
        board = _dungeon_board(1)
        policy = _fresh_policy(board)
        policy._note_return_start(None)
        policy._returning_to_town = True
        # what round 2 did: a named trigger overwrote the running return's
        policy._survival_return_trigger = "emergency-lethal-swarm"
        self.assertTrue(_exit(policy, board, "return:seek-upstairs", "4")["survival"])

    def test_guardian_reposition_is_not_a_survival_trigger(self):
        self.assertFalse(is_survival("return:seek-upstairs", "guardian-reposition"))
        self.assertNotIn("guardian-reposition", SURVIVAL_RETURN_TRIGGERS)


class LastKnownCellTest(unittest.TestCase):
    """Rev 9.3 (R5): a lost town monster's identity claim ends; the walk to
    its last-known cell is a separate Reach claim noted ``last-known``."""

    def test_the_last_known_walk_is_its_own_claim(self):
        board = _town_board()
        self.assertFalse([m for m in board.visible_monsters if not m.pet])
        policy = _fresh_policy(board)
        target = next(
            grid.position for grid in sorted(
                board.grids.values(),
                key=lambda grid: (
                    board.player.position.distance_to(grid.position),
                    grid.position.y, grid.position.x,
                ),
            )
            if grid.passable and not grid.is_store
            and board.player.position.distance_to(grid.position) >= 4
        )
        _standing(policy, ClaimOwner.SURVIVAL, reach_monster(99, 1), board)
        policy._town_hunt_target = target
        key = policy._town_kill_mob_key(board)
        self.assertIsNotNone(key)
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")
        claim = _exit(policy, board, "town:kill-mob-approach", key)
        self.assertEqual(claim["closed_claim"]["closed_reason"], "target-lost")
        self.assertEqual(claim["goal"], {"kind": "Reach", "cell": [target.y, target.x]})
        self.assertEqual(claim["goal_note"], "last-known")
        self.assertFalse(claim["goal_missing"])


class HomeEffectSourceTest(unittest.TestCase):
    """Rev 9.3 (R6): a withdraw/deposit confirmation completes only a
    withdraw/deposit claim, never a Home leave's."""

    def test_a_home_leave_is_not_completed_by_a_withdraw_confirmation(self):
        board = _town_board()
        for source, closed in (
            ("home:store-context-exit", None),
            ("home:route-claim-unfulfilled", None),
            ("store-operation", "complete"),
            ("home-errand:identify", "complete"),
        ):
            with self.subTest(source=source):
                policy = _fresh_policy(board)
                _standing(policy, ClaimOwner.HOME_VISIT,
                          observe(("store_type",), 10, source=source), board)
                policy._complete_observed_effect(
                    "home-withdraw-observed",
                    owners=HOME_EFFECT_OWNERS, sources=HOME_EFFECT_SOURCES,
                )
                self.assertEqual(policy._claim_register.current.closed, closed)


class TeleportAdoptionTest(unittest.TestCase):
    """Rev 9.3 (R7): a caller adopts only the teleport helper's own walk."""

    def test_the_step_off_path_adopts_no_earlier_slot(self):
        board = _town_board()
        policy = _fresh_policy(board)
        policy.last_reason = "shop:approach"            # an earlier producer
        policy._declare_reach(Position(41, 131))
        # the teleport helper took its step-off path and wrote no slot
        policy.last_reason = "town:cross-town-walk-in-return"
        policy._adopt_decision_goal()
        claim = _exit(policy, board, "town:cross-town-walk-in-return")
        self.assertEqual(claim["owner"], "cross-town")
        self.assertTrue(claim["goal_missing"])
        self.assertEqual(claim["goal_note"], "owner-mismatch")

    def test_the_teleport_walk_itself_is_adopted(self):
        board = _town_board()
        policy = _fresh_policy(board)
        policy.last_reason = "town:teleport"
        policy._declare_reach(Position(41, 131), note="teleport-walk")
        policy.last_reason = "town:cross-town-walk-in-return"
        policy._adopt_decision_goal()
        claim = _exit(policy, board, "town:cross-town-walk-in-return")
        self.assertEqual(claim["goal"], {"kind": "Reach", "cell": [41, 131]})
        self.assertIsNone(claim["goal_note"])


# -- round 4 -----------------------------------------------------------------


def _declaration_after(reason_literal):
    """The declaration calls that follow ``self.last_reason = <literal>``."""
    found = []
    for path in sorted(PACKAGE.glob("policy*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for parent in ast.walk(tree):
            body = getattr(parent, "body", None)
            if not isinstance(body, list):
                continue
            for index, stmt in enumerate(body[:-1]):
                if not (
                    isinstance(stmt, ast.Assign)
                    and isinstance(stmt.targets[0], ast.Attribute)
                    and stmt.targets[0].attr == "last_reason"
                ):
                    continue
                value = stmt.value
                text = (
                    value.value if isinstance(value, ast.Constant)
                    else ast.unparse(value)
                )
                if text != reason_literal:
                    continue
                call = getattr(body[index + 1], "value", None)
                if isinstance(call, ast.Call):
                    found.append(ast.unparse(call))
    return found


class ReservedChestCellTest(unittest.TestCase):
    """Round 4 (F1): the chest walk names the reserved cell."""

    def test_the_reserved_cell_is_declared_not_the_first_step(self):
        self.assertEqual(
            _declaration_after("chest:return-reserved-position"),
            ["self._declare_reach(target)"],
        )


class OneStepNoteTest(unittest.TestCase):
    """Round 4 (F2): one-step walks are noted and counted apart in (c)."""

    ONE_STEP_REASONS = (
        "emergency:seek-upstairs", "fundraise:seek-upstairs",
        "fundraise:seek-upstairs-wander", "threat:avoid-engagement",
        "threat:paralyzer-avoid", "threat:reposition", "status-threat:retreat",
        "town:wait-recall-step-off", "bounty:step-off", "chest:step-off",
    )

    def test_the_one_step_sites_carry_the_note(self):
        for reason in self.ONE_STEP_REASONS:
            with self.subTest(reason=reason):
                calls = _declaration_after(reason)
                self.assertTrue(
                    any("note=CLAIM_GOAL_NOTE_ONE_STEP" in call for call in calls),
                    calls,
                )
        # the mixed reasons keep their far-target site un-noted
        for reason in ("emergency:seek-upstairs", "fundraise:seek-upstairs"):
            with self.subTest(far_target=reason):
                self.assertTrue(
                    any("_target" in call and "note=" not in call
                        for call in _declaration_after(reason)),
                )

    def test_the_note_reaches_the_row(self):
        board = _dungeon_board(1)
        policy = _fresh_policy(board)
        policy.last_reason = "threat:avoid-engagement"
        policy._declare_reach(Position(3, 98), note="one-step")
        claim = _exit(policy, board, "threat:avoid-engagement", "1")
        self.assertEqual(claim["goal_note"], "one-step")
        self.assertFalse(claim["goal_missing"])

    def test_c_breaks_reach_endings_down_by_the_note(self):
        rows = [
            dict(_claim_row(1, "escape", "Reach", reason="emergency:seek-upstairs"),
                 goal_note="one-step"),
            _claim_row(2, "escape", "Reach", reason="emergency:seek-upstairs",
                       closed_claim={"claim_id": 1, "goal_kind": "Reach",
                                     "state": "complete", "closed": "complete",
                                     "closed_reason": "reached"}),
            _claim_row(3, "idle", "Terminal", reason="wait"),
        ]
        endings = gate_numbers(rows)["endings"]
        self.assertEqual(endings["escape/Reach:one-step"]["complete"], 1)
        self.assertEqual(endings["escape/Reach"]["abandoned"], 1)


class CaptureRobustnessTest(unittest.TestCase):
    """Round 4 (F3): no capture outlives its call or its decision."""

    def test_a_raising_helper_leaves_no_capture(self):
        board = _town_board()
        policy = _fresh_policy(board)

        def boom(*_args, **_kwargs):
            raise RuntimeError("helper failed")

        policy._nearest_goal_step = boom
        with self.assertRaises(RuntimeError):
            policy._fixed_quest_exit_key(board, 1)
        self.assertNotIn("_claim_target_capture", policy.__dict__)

    def test_a_leftover_capture_is_cleared_at_the_decision_boundary(self):
        board = _town_board()
        policy = _fresh_policy(board)
        policy._claim_target_capture = [Position(1, 1)]
        policy.choose_key(board)
        self.assertNotIn("_claim_target_capture", policy.__dict__)

    def test_a_restored_checkpoint_carries_no_capture(self):
        board = _town_board()
        policy = _fresh_policy(board)
        state = dict(policy.__dict__)
        state["_claim_target_capture"] = [Position(1, 1)]
        state.pop("_town_turn_arbiter", None)
        encoded = base64.b64encode(pickle.dumps(state)).decode("ascii")
        restored = restore_checkpoint(HengbotPolicy, encoded)
        self.assertNotIn("_claim_target_capture", restored.__dict__)


class CachedUpstairsTargetTest(unittest.TestCase):
    """Round 4 (F4): a second read of the cached up-stairs step still
    declares its target."""

    def test_the_second_call_in_a_decision_declares_the_target(self):
        from test_policy_town import ReturnToTownTest

        helper = ReturnToTownTest()
        snapshot = helper._exit_owner_snapshot(10)
        policy = helper._prepare_exit_owner_policy(snapshot)
        policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "return:seek-upstairs")
        self.assertEqual(
            policy.decision_claim["goal"], {"kind": "Reach", "cell": [10, 14]}
        )
        # the same decision asks again: the step comes from the cache
        policy._decision_goal = None
        policy._return_to_town_key(snapshot, [])
        self.assertEqual(policy.last_reason, "return:seek-upstairs")
        self.assertEqual(policy._decision_goal[1], reach((10, 14)))

    def test_revert_proof_without_the_cached_target_the_second_call_declares_none(self):
        from test_policy_town import ReturnToTownTest
        from hengbot import policy_town

        helper = ReturnToTownTest()
        snapshot = helper._exit_owner_snapshot(10)
        policy = helper._prepare_exit_owner_policy(snapshot)
        policy.choose_key(snapshot)
        policy._escape_state.ledger.pop(policy_town.CLAIM_UPSTAIRS_TARGET_KEY)
        policy._decision_goal = None
        policy._return_to_town_key(snapshot, [])
        self.assertIsNone(policy._decision_goal)


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

    RECORD_ONLY_HOOKS = (
        "_declare_goal", "_adopt_decision_goal", "_declare_expectation",
        "_claim_close", "_note_return_start", "_note_return_end",
    )

    def _blanked(self, run):
        """Run with every S2a.1 record-only hook replaced by a no-op."""
        originals = {name: getattr(HengbotPolicy, name) for name in self.RECORD_ONLY_HOOKS}
        for name in self.RECORD_ONLY_HOOKS:
            setattr(HengbotPolicy, name, lambda self, *args, **kwargs: None)
        try:
            return run()
        finally:
            for name, method in originals.items():
                setattr(HengbotPolicy, name, method)

    def test_the_slots_and_the_closings_are_record_only(self):
        """No producer reads a slot or a closing: blanking them all changes
        no decision, on the dungeon replay and on the tour's town prefix
        (sales, a floor change, Home work)."""
        rows = ClosingPathsTest.dungeon_rows()
        blank = self._blanked(_dungeon_rows)
        self.assertEqual(
            [(row["key"], row["reason"]) for row in blank],
            [(row["key"], row["reason"]) for row in rows],
        )
        self.assertFalse([row for row in blank if row.get("closed_claim")])
        limit = 41
        town = ClosingPathsTest.tour_rows(limit=limit)
        blank_town = self._blanked(lambda: ClosingPathsTest.tour_rows(limit=limit))
        self.assertEqual(
            [(row["key"], row["reason"]) for row in blank_town],
            [(row["key"], row["reason"]) for row in town],
        )
        self.assertTrue([row for row in town if row.get("closed_claim")])
        for name in self.RECORD_ONLY_HOOKS:
            self.assertNotEqual(
                getattr(HengbotPolicy, name).__name__, "<lambda>", name
            )


# -- B5 ----------------------------------------------------------------------


class SurvivalConstantTest(unittest.TestCase):
    """B5: survival is exactly the user's list, and it always suspends.

    S2b.1 (design rev 10 item 2): a strictly higher rung of the ladder
    suspends too (``test_ownership_s2b1_ladder``); ``suspend`` still has one
    caller.
    """

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
        """Survival suspends as ``survival-preemption``; ordinary owners do not.

        S2b.1 (design rev 10 item 2) changed the second half: an ordinary
        owner ranked strictly above the holder now preempts too, recorded as
        ``preempted-by:<family>`` and not as survival, and an ordinary owner
        ranked below it suspends nothing (a violation, recorded on the row).
        """
        board = _town_board()
        for reason, closed_reason in (
            ("emergency:teleport", "survival-preemption"),
            ("combat:disengage-step", "survival-preemption"),
            ("flee", "preempted-by:escape"),
            ("threat:scroll", "preempted-by:escape"),
            ("explore", None),
        ):
            with self.subTest(reason=reason):
                policy = _fresh_policy(board)
                standing = self._standing_reach(policy, board)
                policy.last_reason = reason
                policy._record_decision_claim(board, "r")
                closed = policy.decision_claim["closed_claim"]
                survival = closed_reason == "survival-preemption"
                self.assertEqual(policy.decision_claim["survival"], survival)
                if closed_reason is not None:
                    self.assertEqual(closed["claim_id"], standing.claim_id)
                    self.assertEqual(closed["state"], "suspended")
                    self.assertEqual(closed["closed_reason"], closed_reason)
                    self.assertIsNone(policy.decision_claim["violation"])
                else:
                    self.assertIsNone(closed)
                    self.assertEqual(
                        policy.decision_claim["violation"]["claim_id"],
                        standing.claim_id,
                    )


# -- restored checkpoints ----------------------------------------------------


class RestoredCheckpointTest(unittest.TestCase):
    """Every attribute S2a.1 adds or newly reads survives an older pickle."""

    NEW_POLICY_ATTRIBUTES = (
        "_decision_goal", "_decision_expectation", "_hunt_step_target",
        "_survival_return_trigger",
    )

    def test_a_pre_s2a1_claim_goal_register_and_registry_unpickle(self):
        register = ClaimRegister()
        claim = register.declare(ClaimOwner.EXPLORE, reach((3, 4)))
        # Reproduce the pre-S2a.1 state: none of the new fields was pickled.
        for name in ("floor", "closed_reason", "survival", "opened_turn"):
            object.__delattr__(claim, name)
        for name in ("source", "monster", "place"):
            object.__delattr__(claim.goal, name)
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
        self.assertIsNone(restored.goal.monster)
        self.assertIsNone(restored.goal.place)
        self.assertIsNone(restored.opened_turn)
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
        self.assertIn("goal_note", restored.decision_claim)
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
        for name in ("floor", "closed_reason", "survival", "opened_turn"):
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
