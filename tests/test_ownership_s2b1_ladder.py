"""Stage S2b.1: the claim ladder, preemption and violations -- record-only.

``SOL-DESIGN-ownership-contract.md`` rev 10.1 ("Rev 10: S2b specified" and
"Rev 10.1").  Nothing here changes a key, a reason or a decision: the ladder is
read only by the declaration point (``policy._record_decision_claim``) and by
the offline reader (``ownership_metrics.ladder_numbers``).

The pins
--------
C1  ``CLAIM_LADDER`` against the source: its ``decide`` rungs are exactly the
    ``@claims``-marked producer calls inside ``_decide`` (plus the four named
    unmarked dispatcher calls), in ``_decide``'s order, every census family is
    placed with exactly one ordinary rung, and the rank rules of rev 10.1
    items 1-3 hold.  **Revert-proof**: swapping two rungs fails the order
    comparison (``LadderOrderTest.test_revert_proof_swapping_two_rungs``).
C2  the suspended stack (rev 10.1 items 5-6): preempt and resume under the
    same id; nesting A <- B <- C; a displacement is a violation and releases
    ``resume-displaced``; a changed goal releases ``resume-goal-changed``; a
    floor change completes a suspended floor-change ``Observe`` and releases
    the rest ``suspended-expired``; ``within`` does not count the time spent
    suspended; store-operation and transaction ``Observe`` claims are never
    suspended; a retarget is a violation.
C3  the 2026-09-25 live rows, frozen as
    ``tests/fixtures/ownership-claims-20260925-excerpt.jsonl.gz`` (the first
    7,525 claim rows of the sessions of that day, raw lines of
    ``jsonlog/ownership-claims.jsonl``), reclassified through the writer's own
    functions (rev 10.1 item 11).  The pinned numbers and the difference from
    the design's figures are written out above ``RankOnlyReclassificationTest``.
C4  neutrality: the S2a trajectory digests
    (``test_ownership_s2a_classification`` A1) and the S1/S2a.1 register
    on/off pins stay green; here, the named dungeon replay decides the same
    keys and reasons with the register on and off, and its rows carry the
    ladder's record.
C5  restored checkpoints: a register without ``_suspended`` /
    ``_suspended_closings`` and claims without the S2b.1 fields restore and
    decide; ``restore_checkpoint`` gives the stack its empty default.

Attributes S2b.1 adds or newly reads (C5 covers each):
    ``ClaimRegister._suspended``, ``ClaimRegister._suspended_closings``;
    ``Claim.rank``, ``.rung``, ``.suspended_sequence``, ``.suspended_turn``,
    ``.suspended_decisions``, ``.suspended_turns``, ``.trigger_monsters``,
    ``.last_perceived_turn`` (class defaults).  No new policy attribute is
    added or newly read (``non_discardable`` stays unset: see
    ``policy._record_decision_claim``).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare runs

import ast
import base64
import gzip
import json
import pickle
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path

from hengbot.claim_goal_typing import FLOOR_CHANGE
from hengbot.claim_ladder import (
    CLAIM_LADDER,
    FALLBACK_RANK,
    SECTION_DECIDE,
    SECTION_FALLBACK,
    SECTION_REWRITE,
    SECTION_TOWN,
    TOWN_ERRAND_FAMILIES,
    TOWN_RANK,
    decide_rungs,
    ladder_families,
    rung_of,
)
from hengbot.claim_register import (
    CLAIM_OWNER_ATTRIBUTE,
    ClaimOwner,
    ClaimRegister,
    claims,
    observe,
    reach,
)
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.ownership_metrics import (
    OWNERSHIP_CLAIMS_NAME,
    _claim_rows_by_session,
    _closure_of,
    _goal_kind,
    GOAL_KINDS_THAT_SPAN,
    gate_numbers,
    ladder_numbers,
    read_records,
    row_is_survival,
)
from hengbot.policy import HengbotPolicy
from hengbot.town_arbiter import _new_town_turn_arbiter, owner_families

from test_ownership_claims import LEGACY_CHECKPOINT, _Replay
from test_ownership_s2a1_closure import _fresh_policy, _town_board

import ownership_metrics_report


ROOT = Path(__file__).resolve().parents[1]
POLICY_SOURCE = ROOT / "src" / "hengbot" / "policy.py"
EXCERPT = ROOT / "tests" / "fixtures" / "ownership-claims-20260925-excerpt.jsonl.gz"

# Rev 10.1 item 1: the rungs that carried no marker before S2b.1.
NEWLY_MARKED = (
    ("_direction_key", ClaimOwner.COMBAT),
    ("_blocking_escape_melee_key", ClaimOwner.ESCAPE),
    ("_flee_step", ClaimOwner.ESCAPE),
    ("_hunt_step", ClaimOwner.HUNT),
    ("_fundraising_key", ClaimOwner.FUNDRAISING),
    ("_normal_loot_key", ClaimOwner.FLOOR_LOOT),
    ("_explore_step", ClaimOwner.EXPLORE),
)


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "self":
            return func.attr
        return f"{func.value.id}.{func.attr}"
    return None


def _decide_calls(ladder=CLAIM_LADDER) -> list[str]:
    """The rung calls inside ``_decide``, in source order.

    A call is a rung call when it is a ``self`` method carrying the
    ``@claims`` marker, or when the ladder names it as an unmarked rung.
    """
    unmarked = {
        rung.producer for rung in decide_rungs(ladder) if not rung.marked
    }
    tree = ast.parse(POLICY_SOURCE.read_text(encoding="utf-8"))
    decide = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_decide"
    )
    calls = []
    for node in ast.walk(decide):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name is None:
            continue
        method = getattr(HengbotPolicy, name, None) if "." not in name else None
        if (
            getattr(method, CLAIM_OWNER_ATTRIBUTE, None) is not None
            or name in unmarked
        ):
            calls.append((node.lineno, node.col_offset, name))
    return [name for _line, _col, name in sorted(calls)]


def _order_mismatch(ladder) -> list:
    expected = [rung.producer for rung in decide_rungs(ladder)]
    found = _decide_calls(ladder)
    return [
        (index, want, got)
        for index, (want, got) in enumerate(
            zip(expected + [None] * len(found), found + [None] * len(expected))
        )
        if want != got
    ]


# -- C1 ----------------------------------------------------------------------


class LadderOrderTest(unittest.TestCase):
    """C1: the ladder is the order ``_decide`` consults its producers in."""

    def test_the_decide_rungs_are_the_marked_calls_in_order(self):
        self.assertEqual(_order_mismatch(CLAIM_LADDER), [])
        self.assertEqual(len(decide_rungs()), 76)

    def test_revert_proof_swapping_two_rungs(self):
        rungs = list(CLAIM_LADDER)
        positions = [
            index for index, rung in enumerate(rungs)
            if rung.section == SECTION_DECIDE
        ]
        # the melee rung and the ordinary ranged rung below it
        first = next(
            index for index in positions
            if rungs[index].producer == "_direction_key"
            and rungs[index].family == "combat"
        )
        second = positions[positions.index(first) + 1]
        self.assertEqual(rungs[second].producer, "_ranged_attack_key")
        rungs[first], rungs[second] = rungs[second], rungs[first]
        self.assertNotEqual(_order_mismatch(tuple(rungs)), [])

    def test_the_six_rungs_carry_their_marker_and_it_is_annotation_only(self):
        for name, owner in NEWLY_MARKED:
            with self.subTest(producer=name):
                self.assertIs(
                    getattr(getattr(HengbotPolicy, name), CLAIM_OWNER_ATTRIBUTE),
                    owner,
                )
        def producer():
            return None
        self.assertIs(claims(ClaimOwner.COMBAT)(producer), producer)

    def test_every_census_family_is_placed_with_one_ordinary_rung(self):
        families = set(owner_families()) | {"unregistered"}
        self.assertEqual(ladder_families(), families)
        for family in sorted(families):
            with self.subTest(family=family):
                ordinary = [
                    rung for rung in CLAIM_LADDER
                    if rung.family == family and rung.ordinary
                ]
                self.assertEqual(len(ordinary), 1)

    def test_every_rung_reason_belongs_to_its_family(self):
        registry = _new_town_turn_arbiter().registry
        for rung in CLAIM_LADDER:
            census = registry.get(rung.family)
            for prefix in rung.reasons:
                with self.subTest(rung=rung.name, prefix=prefix):
                    self.assertIsNotNone(census)
                    self.assertTrue(
                        any(
                            prefix.startswith(known) or known.startswith(prefix)
                            for known in census.census_prefixes
                        )
                    )

    def test_the_rewrite_producers_exist_outside_decide(self):
        decide = set(_decide_calls())
        for rung in CLAIM_LADDER:
            if rung.section != SECTION_REWRITE:
                continue
            with self.subTest(producer=rung.producer):
                self.assertTrue(hasattr(HengbotPolicy, rung.producer))
                self.assertNotIn(rung.producer, decide)

    def test_the_rank_rules(self):
        """Rev 10.1 items 1-3."""
        rewrite = {
            rung.family: rung.rank
            for rung in CLAIM_LADDER if rung.section == SECTION_REWRITE
        }
        self.assertEqual(
            rewrite, {"detectors": 0, "town-plan": 1, "bookkeeping": 2}
        )
        dungeon = [
            rung for rung in decide_rungs() if not rung.shares_town_rank
        ]
        ranks = [rung.rank for rung in dungeon]
        self.assertEqual(ranks, list(range(3, 3 + len(dungeon))))
        self.assertEqual(TOWN_RANK, 3 + len(dungeon))
        for rung in CLAIM_LADDER:
            with self.subTest(rung=rung.name):
                if rung.section == SECTION_FALLBACK:
                    self.assertEqual(rung.rank, FALLBACK_RANK)
                elif rung.section == SECTION_TOWN or (
                    rung.section == SECTION_DECIDE
                    and rung.family in TOWN_ERRAND_FAMILIES
                    and not rung.owns_transaction
                ):
                    self.assertEqual(rung.rank, TOWN_RANK)
        # item 2: the transaction owner outranks every town errand and more
        owner = rung_of(
            "equipment-txn", "equipment-transaction:equip", non_discardable=True
        )
        self.assertTrue(owner.owns_transaction)
        self.assertEqual(owner.rank, 3)
        self.assertEqual(
            rung_of("equipment-txn", "equipment-transaction:equip").rank,
            TOWN_RANK,
        )
        # item 3: escape and survival sit at their _decide positions
        self.assertLess(rung_of("escape", "flee").rank, TOWN_RANK)
        self.assertLess(rung_of("survival", "survival:eat").rank, TOWN_RANK)

    def test_rungs_from_reasons(self):
        melee = rung_of("combat", "melee")
        self.assertEqual(melee.name, "_direction_key#2")
        self.assertLess(melee.rank, rung_of("floor-loot", "seek-loot").rank)
        self.assertLess(melee.rank, rung_of("fundraising", "fundraise:seek-loot").rank)
        self.assertLess(
            rung_of("combat", "ranged:fire-target").rank,
            rung_of("departure", "return:wait-recall").rank,
        )
        self.assertLess(
            rung_of("detectors", "breakout:seek-frontier").rank,
            rung_of("explore", "explore").rank,
        )
        self.assertEqual(rung_of("detectors", "town-progress-invariant:x").rank, 0)
        self.assertEqual(rung_of("departure", "town:wait-recall").rank, TOWN_RANK)
        self.assertEqual(
            rung_of("fundraising", "town:recall-stockout-mining").rank, TOWN_RANK
        )
        self.assertEqual(rung_of("nonexistent", "x").rank, FALLBACK_RANK)


# -- C2 ----------------------------------------------------------------------


class _Decisions:
    """Drive ``_record_decision_claim`` directly on one recorded town board."""

    def __init__(self):
        self.board = _town_board()
        self.policy = _fresh_policy(self.board)
        self.position = self.board.player.position

    def cell(self, offset: int) -> tuple[int, int]:
        return (self.position.y + offset, self.position.x + offset)

    def decide(self, reason, *, cell=None, board=None, key="k"):
        policy = self.policy
        board = board or self.board
        policy._decision_sequence += 1
        policy._decision_goal = None
        policy._decision_expectation = None
        policy.last_reason = reason
        if cell is not None:
            policy._decision_goal = (
                policy._claim_family_of(reason), reach(cell), None
            )
        policy._record_decision_claim(board, key)
        return dict(policy.decision_claim)

    @property
    def register(self) -> ClaimRegister:
        return self.policy._claim_register


class StackSemanticsTest(unittest.TestCase):
    """C2: rev 10.1 items 5-6."""

    def test_preempt_and_resume_under_the_same_id(self):
        run = _Decisions()
        walk = run.decide("fundraise:seek-treasure", cell=run.cell(3))
        swing = run.decide("melee")
        self.assertEqual(
            (swing["closed_claim"]["claim_id"], swing["closed_claim"]["state"],
             swing["closed_claim"]["closed_reason"]),
            (walk["claim_id"], "suspended", "preempted-by:combat"),
        )
        self.assertIsNone(swing["violation"])
        self.assertEqual(swing["suspended_depth"], 1)
        back = run.decide("fundraise:seek-treasure", cell=run.cell(3))
        self.assertEqual(back["claim_id"], walk["claim_id"])
        self.assertEqual(back["state"], "active")
        self.assertEqual(back["resumed"]["claim_id"], walk["claim_id"])
        # suspended on the swing's decision, resumed on the next one
        self.assertEqual(back["resumed"]["suspended_decisions"], 1)
        self.assertEqual(back["suspended_depth"], 0)
        self.assertIsNone(back["violation"])

    def test_nesting_a_b_c_unwinds_in_order(self):
        run = _Decisions()
        a = run.decide("seek-loot", cell=run.cell(3))
        b = run.decide("detected:prepare-choke", cell=run.cell(4))
        self.assertEqual(b["closed_claim"]["claim_id"], a["claim_id"])
        c = run.decide("summoner:ranged-kill")
        self.assertEqual(c["closed_claim"]["claim_id"], b["claim_id"])
        self.assertEqual(c["closed_claim"]["closed_reason"],
                         "preempted-by:combat")
        self.assertEqual(c["suspended_depth"], 2)
        self.assertEqual(
            [claim.claim_id for claim in run.register.suspended],
            [a["claim_id"], b["claim_id"]],
        )
        b_again = run.decide("detected:prepare-choke", cell=run.cell(4))
        self.assertEqual(b_again["claim_id"], b["claim_id"])
        self.assertEqual(b_again["suspended_depth"], 1)
        # positioning arrives at its cell (the producer's own arrival call)
        run.register.complete("choke-reached")
        a_again = run.decide("seek-loot", cell=run.cell(3))
        self.assertEqual(a_again["claim_id"], a["claim_id"])
        self.assertEqual(a_again["closed_claim"]["closed"], "complete")
        self.assertEqual(a_again["suspended_depth"], 0)
        self.assertIsNone(a_again["violation"])

    def test_a_higher_owner_nests_without_touching_the_stack(self):
        run = _Decisions()
        a = run.decide("seek-loot", cell=run.cell(3))
        run.decide("melee")
        nested = run.decide("ranged:fire-target")
        self.assertIsNone(nested["suspended_closed"])
        self.assertEqual(
            [claim.claim_id for claim in run.register.suspended], [a["claim_id"]]
        )

    def test_a_lower_owner_displaces_the_suspended_claim(self):
        run = _Decisions()
        a = run.decide("seek-loot", cell=run.cell(3))
        run.decide("melee")
        displaced = run.decide("explore", cell=run.cell(5))
        self.assertEqual(displaced["suspended_depth"], 0)
        (closing,) = displaced["suspended_closed"]
        self.assertEqual(
            (closing["claim_id"], closing["closed"], closing["closed_reason"]),
            (a["claim_id"], "release", "resume-displaced"),
        )
        self.assertEqual(
            {name: closing["violation"][name]
             for name in ("kind", "from", "to", "claim_id", "scope")},
            {"kind": "displaced", "from": "floor-loot", "to": "explore",
             "claim_id": a["claim_id"], "scope": "in-scope"},
        )
        self.assertNotEqual(displaced["claim_id"], a["claim_id"])

    def test_the_same_owner_with_another_goal_releases_it(self):
        run = _Decisions()
        a = run.decide("seek-loot", cell=run.cell(3))
        run.decide("melee")
        other = run.decide("seek-loot", cell=run.cell(6))
        (closing,) = other["suspended_closed"]
        self.assertEqual(
            (closing["claim_id"], closing["closed_reason"]),
            (a["claim_id"], "resume-goal-changed"),
        )
        self.assertNotIn("violation", closing)
        self.assertNotEqual(other["claim_id"], a["claim_id"])
        self.assertIsNone(other["resumed"])

    def test_a_floor_change_completes_the_recall_and_expires_the_rest(self):
        run = _Decisions()
        walk = run.decide("seek-loot", cell=run.cell(3))
        recall = run.decide("return:recall")
        self.assertEqual(recall["goal"]["source"], FLOOR_CHANGE)
        self.assertEqual(recall["closed_claim"]["claim_id"], walk["claim_id"])
        run.decide("melee")
        self.assertEqual(len(run.register.suspended), 2)
        floor = run.board.floor_key
        elsewhere = replace(
            run.board, floor_key=(floor[0], floor[1] + 1, floor[2])
        )
        after = run.decide("explore", cell=run.cell(5), board=elsewhere)
        closings = {
            entry["claim_id"]: (entry["closed"], entry["closed_reason"])
            for entry in after["suspended_closed"]
        }
        self.assertEqual(
            closings,
            {
                walk["claim_id"]: ("release", "suspended-expired"),
                recall["claim_id"]: ("complete", "floor-changed"),
            },
        )
        self.assertEqual(after["suspended_depth"], 0)
        self.assertIsNone(after["violation"])

    def test_a_suspended_reach_completes_when_its_cell_is_reached(self):
        run = _Decisions()
        here = (run.position.y, run.position.x)
        # A walk to the player's own cell: the exit would complete it on the
        # next board, so suspend it first, as the writer's preemption does.
        walk = run.decide("seek-loot", cell=here)
        self.assertEqual(walk["goal"]["cell"], list(here))
        run.register.suspend(
            "preempted-by:combat", sequence=run.policy._decision_sequence,
            turn=run.board.turn,
        )
        done = run.decide("melee")
        closings = {entry["claim_id"]: entry["closed_reason"]
                    for entry in done["suspended_closed"]}
        self.assertEqual(closings[walk["claim_id"]], "reached")

    def test_within_does_not_count_the_time_spent_suspended(self):
        run = _Decisions()
        recall = run.decide("return:recall")
        within = recall["goal"]["within"]
        run.decide("melee")
        later = replace(run.board, turn=run.board.turn + within + 100)
        back = run.decide("return:recall", board=later)
        self.assertEqual(back["claim_id"], recall["claim_id"])
        self.assertEqual(back["resumed"]["suspended_turns"], within + 100)
        again = run.decide("return:recall", board=later)
        # opened ``within + 100`` turns ago, but suspended for all of them
        self.assertEqual(again["claim_id"], recall["claim_id"])
        self.assertIsNone(again["closed_claim"])

    def test_store_operation_and_transaction_observe_are_never_suspended(self):
        for reason, family in (
            ("home:atomic-deposit", "home-visit"),
            ("equipment-transaction:takeoff", "equipment-txn"),
        ):
            for preemptor in ("melee", "emergency:teleport"):
                with self.subTest(held=reason, preemptor=preemptor):
                    run = _Decisions()
                    held = run.decide(reason)
                    self.assertEqual(held["goal"]["kind"], "Observe")
                    self.assertNotEqual(held["goal"].get("source"), FLOOR_CHANGE)
                    after = run.decide(preemptor)
                    self.assertIsNone(after["closed_claim"])
                    self.assertEqual(after["suspended_depth"], 0)
                    self.assertEqual(
                        {name: after["violation"][name]
                         for name in ("kind", "from", "claim_id", "scope")},
                        {"kind": "owner-change", "from": family,
                         "claim_id": held["claim_id"], "scope": "S3"},
                    )

    def test_a_retarget_is_a_violation(self):
        run = _Decisions()
        first = run.decide("seek-loot", cell=run.cell(3))
        second = run.decide("seek-loot", cell=run.cell(6))
        self.assertNotEqual(second["claim_id"], first["claim_id"])
        self.assertEqual(
            {name: second["violation"][name]
             for name in ("kind", "from", "to", "claim_id")},
            {"kind": "retarget", "from": "floor-loot", "to": "floor-loot",
             "claim_id": first["claim_id"]},
        )

    def test_trigger_monsters_are_pairs_from_the_board(self):
        run = _Decisions()
        hostile = [
            monster for monster in (
                *run.board.visible_monsters, *run.board.detected_monsters
            ) if monster.hostile
        ]
        row = run.decide("detected:prepare-choke", cell=run.cell(3))
        expected = sorted(
            [monster.index, monster.race_id] for monster in hostile
        )
        self.assertEqual(row["trigger_monsters"] or [], expected)
        self.assertEqual(
            row["last_perceived_turn"], run.board.turn if expected else None
        )
        # a family outside rev 10.1 item 9 records none
        self.assertIsNone(run.decide("seek-loot", cell=run.cell(4))[
            "trigger_monsters"])

    def test_the_rank_and_rung_are_on_every_row(self):
        run = _Decisions()
        row = run.decide("melee")
        self.assertEqual(
            (row["rank"], row["rung"]),
            (rung_of("combat", "melee").rank, "_direction_key#2"),
        )


class TriggerMonsterRegisterTest(unittest.TestCase):
    """Rev 10.1 item 9 at the register: pairs, and the last perceived turn."""

    def test_the_last_perceived_turn_moves_only_when_perceived(self):
        register = ClaimRegister()
        first = register.declare(
            ClaimOwner.POSITIONING, reach((1, 1)),
            trigger_monsters=((7, 120),), perceived_turn=100,
        )
        self.assertEqual(first.trigger_monsters, ((7, 120),))
        same = register.declare(
            ClaimOwner.POSITIONING, reach((1, 1)), perceived_turn=None
        )
        self.assertEqual(same.last_perceived_turn, 100)
        later = register.declare(
            ClaimOwner.POSITIONING, reach((1, 1)), perceived_turn=150
        )
        self.assertEqual(later.claim_id, first.claim_id)
        self.assertEqual(later.last_perceived_turn, 150)


# -- C3 ----------------------------------------------------------------------
#
# On the frozen excerpt (the first 7,525 claim rows of the 2026-09-25
# sessions).  The design (rev 10.1 item 8) measured "(a) = 66 on 7,525 rows;
# 41 become preemptions; of the 25 that remain, 23 are S3-family pairs and 2
# are detectors>explore".  Reproduced exactly on the first 6,709 rows, where
# (a) reaches 66 (it stays 66 up to row 7,108): the design's 41/23/2 is the
# **rank-only** verdict.  Two differences, both explained:
#
# * at 7,525 rows (a) is 71, not 66 (five later events: three more
#   floor-loot>combat, one store-router>detectors, one home-scan>store-router);
#   the design's row count and its (a) count come from different moments of
#   the growing file;
# * rev 10.1 item 6 (written in the same revision) says a store-operation or
#   transaction Observe claim is never suspended.  Six of the 41 are such
#   claims preempted by a higher rung -- store-router>detectors 3
#   (``shop:travel:await-entry``), home-visit>bookkeeping 1, home-visit>
#   town-plan 1 (``home:leave-after-one-operation``), home-scan>bookkeeping 1
#   (``home:request-knowledge-scan``) -- so the writer's own function counts
#   them as S3 violations: 35 preemptions, 29 S3 violations, 2 in-scope.

EXCERPT_ROWS = 7525
DESIGN_WINDOW = 6709
DESIGN_A = 66
EXCERPT_A = 71
RANK_ONLY_DESIGN_WINDOW = {"preemption": 41, "S3": 23, "in-scope": 2}
LADDER_DESIGN_WINDOW = {"preemption": 35, "S3": 29, "in-scope": 2}
LADDER_EXCERPT = {"preemption": 38, "S3": 31, "in-scope": 2}
# (b) on the same rows (the same owner replacing its open goal), scoped: the
# twelve S3 ones are departure's ``town:wait-recall`` retargets and the
# equipment / calibration transactions.
RETARGETS_DESIGN_WINDOW = {"in-scope": 2, "S3": 12}
ACCEPTANCE_II_PAIRS = ("fundraising>combat", "floor-loot>combat", "departure>combat")
IN_SCOPE_PAIRS = {"detectors>explore": 2}


def _excerpt():
    with gzip.open(EXCERPT, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _a_events(rows):
    """Exactly the events ``gate_numbers`` counts as (a)."""
    for session_rows in _claim_rows_by_session(rows):
        for previous, current in zip(session_rows, session_rows[1:]):
            if previous.get("claim_id") == current.get("claim_id"):
                continue
            if _goal_kind(previous) not in GOAL_KINDS_THAT_SPAN:
                continue
            if _closure_of(previous, current) is not None:
                continue
            if row_is_survival(previous) or row_is_survival(current):
                continue
            if previous.get("owner") != current.get("owner"):
                yield previous, current


def _ladder_split(ladder) -> dict:
    return {
        "preemption": ladder["preemptions"]["count"],
        "S3": ladder["violations"]["S3"]["count"],
        "in-scope": ladder["violations"]["in-scope"]["count"],
    }


class RankOnlyReclassificationTest(unittest.TestCase):
    """C3: the 2026-09-25 rows through the writer's functions."""

    rows = None

    @classmethod
    def setUpClass(cls):
        cls.rows = _excerpt()

    def test_the_excerpt_is_the_frozen_one(self):
        self.assertEqual(len(self.rows), EXCERPT_ROWS)
        self.assertTrue(all(
            "2026-09-25" in row["session"] for row in self.rows
        ))
        self.assertEqual(
            gate_numbers(self.rows)["dropped_by_other_owner"]["count"],
            EXCERPT_A,
        )
        window = self.rows[:DESIGN_WINDOW]
        self.assertEqual(
            gate_numbers(window)["dropped_by_other_owner"]["count"], DESIGN_A
        )

    def test_the_design_measurement_is_the_rank_only_verdict(self):
        from hengbot.claim_ladder import pair_scope

        split = Counter()
        for previous, current in _a_events(self.rows[:DESIGN_WINDOW]):
            held = rung_of(previous["owner"], previous["reason"])
            new = rung_of(current["owner"], current["reason"])
            if new.rank < held.rank:
                split["preemption"] += 1
            else:
                split[pair_scope(held, new)] += 1
        self.assertEqual(dict(split), RANK_ONLY_DESIGN_WINDOW)

    def test_the_ladder_reader_splits_preemptions_and_violations(self):
        window = ladder_numbers(self.rows[:DESIGN_WINDOW])
        self.assertEqual(_ladder_split(window), LADDER_DESIGN_WINDOW)
        self.assertEqual(window["violations"]["in-scope"]["pairs"], IN_SCOPE_PAIRS)
        self.assertEqual(
            {scope: window["retargets"][scope]["count"]
             for scope in ("in-scope", "S3")},
            RETARGETS_DESIGN_WINDOW,
        )
        whole = ladder_numbers(self.rows)
        self.assertEqual(_ladder_split(whole), LADDER_EXCERPT)
        self.assertEqual(
            whole["legacy_events"],
            EXCERPT_A + gate_numbers(self.rows)["retargets"]["count"],
        )

    def test_acceptance_ii_the_combat_takeovers_are_preemptions(self):
        ladder = ladder_numbers(self.rows)
        for pair in ACCEPTANCE_II_PAIRS:
            with self.subTest(pair=pair):
                self.assertGreater(ladder["preemptions"]["pairs"].get(pair, 0), 0)
                for scope in ("in-scope", "S3", "survival"):
                    self.assertNotIn(pair, ladder["violations"][scope]["pairs"])

    def test_the_report_prints_the_new_metric(self):
        lines = ownership_metrics_report.ladder_report(self.rows, 2.0)
        text = "\n".join(lines)
        self.assertIn("S2b.1 ladder", text)
        self.assertIn("violations, in-scope families (the S2b.2 gate)", text)
        self.assertIn("preemptions (suspended, informational)", text)
        self.assertIn("displacements", text)
        self.assertIn("suspended claims:", text)
        self.assertIn(
            f"per runtime hour {LADDER_EXCERPT['in-scope'] / 2.0:.3f}", text
        )


class FinalEndingTest(unittest.TestCase):
    """Rev 10.1 item 7: metric (c) counts one final ending per claim id."""

    def test_a_resumed_claim_ends_once(self):
        run = _Decisions()
        rows = []

        def record(reason, **kwargs):
            row = run.decide(reason, **kwargs)
            row.update(kind="claim", session="s", reason=reason)
            rows.append(row)

        record("seek-loot", cell=run.cell(3))
        record("melee")
        record("seek-loot", cell=run.cell(3))
        run.register.complete("loot-collected")
        record("explore", cell=run.cell(5))
        endings = gate_numbers(rows)["endings"]["floor-loot/Reach"]
        self.assertEqual(endings["complete"], 1)
        self.assertEqual(endings["suspended"], 0)
        self.assertEqual(sum(endings.values()), 1)
        ladder = ladder_numbers(rows)
        self.assertEqual(ladder["preemptions"]["pairs"], {"floor-loot>combat": 1})
        self.assertEqual(ladder["suspended"], {"resumed": 1})

    def test_a_claim_closed_while_suspended_ends_with_that_closing(self):
        run = _Decisions()
        rows = []

        def record(reason, **kwargs):
            row = run.decide(reason, **kwargs)
            row.update(kind="claim", session="s", reason=reason)
            rows.append(row)

        record("seek-loot", cell=run.cell(3))
        record("melee")
        record("explore", cell=run.cell(5))
        endings = gate_numbers(rows)["endings"]["floor-loot/Reach"]
        self.assertEqual(endings["release"], 1)
        self.assertEqual(sum(endings.values()), 1)
        ladder = ladder_numbers(rows)
        self.assertEqual(ladder["displacements"]["pairs"],
                         {"floor-loot>explore": 1})
        self.assertEqual(ladder["violations"]["in-scope"]["pairs"],
                         {"floor-loot>explore": 1})
        self.assertEqual(ladder["suspended"], {"resume-displaced": 1})


# -- C4 ----------------------------------------------------------------------


class NeutralityTest(unittest.TestCase):
    """C4: the ladder records; the replay decides the same with it on or off."""

    def test_the_dungeon_replay_decides_the_same_and_records_the_ladder(self):
        skill, boards = _Replay.dungeon_boards()
        with tempfile.TemporaryDirectory(prefix="s2b1-") as raw:
            root = Path(raw)
            (root / "on").mkdir()
            (root / "off").mkdir()
            on, _log = _Replay.run(
                root / "on", skill, boards, register=True, ledger=True
            )
            off, _log = _Replay.run(root / "off", skill, boards, register=False)
            claims = read_records(root / "on" / OWNERSHIP_CLAIMS_NAME)
        self.assertEqual(on, off)
        self.assertEqual(len(claims), len(boards))
        for record in claims:
            with self.subTest(sequence=record["decision_sequence"]):
                self.assertIsInstance(record["rank"], int)
                self.assertIsInstance(record["rung"], str)
                self.assertEqual(
                    record["rank"],
                    rung_of(record["owner"], record["reason"]).rank,
                )


# -- C5 ----------------------------------------------------------------------


class RestoredCheckpointTest(unittest.TestCase):
    """C5: registers and claims pickled before S2b.1."""

    NEW_CLAIM_FIELDS = (
        "rank", "rung", "suspended_sequence", "suspended_turn",
        "suspended_decisions", "suspended_turns", "trigger_monsters",
        "last_perceived_turn",
    )

    def _pre_s2b1_register(self, owner=ClaimOwner.FLOOR_LOOT, goal=None):
        register = ClaimRegister()
        claim = register.declare(owner, goal or reach((3, 4)))
        for name in self.NEW_CLAIM_FIELDS:
            object.__delattr__(claim, name)
        del register.__dict__["_suspended"]
        del register.__dict__["_suspended_closings"]
        return pickle.loads(pickle.dumps(register))

    def test_a_pre_s2b1_register_and_claim_unpickle(self):
        restored = self._pre_s2b1_register()
        claim = restored.current
        self.assertIsNone(claim.rank)
        self.assertIsNone(claim.rung)
        self.assertEqual(claim.suspended_decisions, 0)
        self.assertEqual(claim.trigger_monsters, ())
        self.assertIsNone(claim.last_perceived_turn)
        self.assertEqual(restored.suspended, ())
        self.assertEqual(restored.take_suspended_closings(), [])
        # the old claim can be suspended and resumed like a new one
        restored.suspend("preempted-by:combat", sequence=4, turn=40)
        self.assertEqual([c.claim_id for c in restored.suspended], [claim.claim_id])
        back = restored.resume(claim.claim_id, sequence=9, turn=90)
        self.assertEqual(
            (back.claim_id, back.suspended_decisions, back.suspended_turns),
            (claim.claim_id, 5, 50),
        )

    def test_a_pre_s2b1_register_in_a_policy_declares_and_preempts(self):
        run = _Decisions()
        restored = self._pre_s2b1_register(goal=reach(run.cell(3)))
        run.policy._claim_register = restored
        row = run.decide("melee")
        # the held claim has no recorded rung: its family's ordinary rung
        self.assertEqual(row["closed_claim"]["closed_reason"],
                         "preempted-by:combat")
        self.assertEqual(row["suspended_depth"], 1)

    def test_the_legacy_checkpoint_restores_an_empty_stack_and_decides(self):
        with gzip.open(LEGACY_CHECKPOINT, "rt", encoding="utf-8") as stream:
            capture = json.load(stream)
        producer = capture["sequence"][0]
        snapshot = pickle.loads(
            base64.b64decode(capture["snapshots_pickle_b64"][producer["snapshot_id"]])
        )
        state = pickle.loads(base64.b64decode(capture["producer_checkpoint_pickle_b64"]))
        register = ClaimRegister()
        claim = register.declare(ClaimOwner.STORE_ROUTER, reach((1, 1)))
        for name in self.NEW_CLAIM_FIELDS:
            object.__delattr__(claim, name)
        del register.__dict__["_suspended"]
        del register.__dict__["_suspended_closings"]
        state["_claim_register"] = register
        encoded = base64.b64encode(pickle.dumps(state)).decode("ascii")
        restored = restore_checkpoint(HengbotPolicy, encoded)
        self.assertEqual(restored._claim_register.__dict__["_suspended"], [])
        self.assertEqual(
            restored._claim_register.__dict__["_suspended_closings"], []
        )
        key = restored.choose_key(snapshot)
        self.assertEqual(
            (key, restored.last_reason),
            (producer["expected_key"], producer["expected_reason"]),
        )
        self.assertIn("rank", restored.decision_claim)
        self.assertIn("violation", restored.decision_claim)


if __name__ == "__main__":
    unittest.main()
