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
    ``.last_perceived_turn`` (class defaults); round 2 adds the policy's
    per-decision slot ``_decision_triggers`` (reset at every ``choose_key``
    entry, ``getattr`` in the writer, ``restore_checkpoint`` default).
    ``non_discardable`` stays unset: see ``policy._record_decision_claim``.

Round 2 (the two reviews of a5c744e5)
-------------------------------------
F1  ``BoundedStackTest``: a push is by a strictly higher rank only; survival
    that does not outrank the holder replaces it (``survival-displaced``,
    exempt); a same-owner same-goal claim resumes from anywhere in the stack.
    The reviewers' alternation stays at depth <= 1 and resumes its escape
    claim; a seeded 600-decision sequence keeps the stack strictly ordered.
    **Revert-proof**: the round-1 rules grow the alternation past depth 6;
    a top-only resume leaves the buried claim buried.
F2  ``SameOwnerGoalChangeTest``: a same-owner goal change is a retarget
    violation, or on a survival decision the survival exemption; a continuing
    claim takes its decision's survival flag.
F3  ``TriggerSetTest``: the look-ahead set of design 5.4.1 from the producer's
    own selection, on the recorded 06:00 boards whose other perceived
    hostiles are left out.
F4  the order test compares (producer, family) per call site; swapping the
    families of two call sites of one producer fails.
F5  ``PickupCensusTest``: ``pickup`` / ``trigger-autodestroy`` are floor-loot.
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
from hengbot.model import parse_snapshot
from hengbot.policy_constants import SWARM_LOOKAHEAD
from hengbot.town_arbiter import (
    _new_town_turn_arbiter,
    owner_families,
    reason_owner_family,
)

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


def _literal_family(node) -> str | None:
    """The census family of a reason literal (or an f-string's head)."""
    text = None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
    elif (
        isinstance(node, ast.JoinedStr)
        and node.values
        and isinstance(node.values[0], ast.Constant)
    ):
        text = node.values[0].value
    if text is None:
        return None
    family = reason_owner_family(text)
    return None if family == "unregistered" else family


def _reason_families(statement):
    for node in ast.walk(statement):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Attribute) and target.attr == "last_reason"
            for target in node.targets
        ):
            family = _literal_family(node.value)
            if family is not None:
                yield family


def _call_site_family(call, parents, marker):
    """The family a ``_decide`` call site produces, read from the source.

    In order: a reason literal passed to the call (``seek_reason=...``, a
    travel reason); for ``x = self.f(...)``, the first reason literal set in
    the body of the ``if`` statements right after it that test ``x``; for
    ``return self.f(...)``, a reason literal set by the statement just before
    it; otherwise the producer's ``@claims`` marker.
    """
    for argument in [*call.args, *(keyword.value for keyword in call.keywords)]:
        family = _literal_family(argument)
        if family is not None:
            return family
    child = call
    statement = block = index = None
    while child in parents:
        parent = parents[child]
        found = False
        for field in ("body", "orelse", "finalbody"):
            candidate = getattr(parent, field, None)
            if isinstance(candidate, list) and child in candidate:
                statement, block, index = child, candidate, candidate.index(child)
                found = True
                break
        if found:
            break
        child = parent
    if (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    ):
        bound = statement.targets[0].id
        for sibling in block[index + 1:]:
            if not isinstance(sibling, ast.If) or bound not in {
                node.id for node in ast.walk(sibling.test)
                if isinstance(node, ast.Name)
            }:
                break
            for inner in sibling.body:
                for family in _reason_families(inner):
                    return family
    if isinstance(statement, ast.Return) and index:
        for family in _reason_families(block[index - 1]):
            return family
    return marker


def _decide_calls(ladder=CLAIM_LADDER) -> list[tuple[str, str | None]]:
    """The rung calls inside ``_decide``, in source order, with the family
    each call site produces.

    A call is a rung call when it is a ``self`` method carrying the
    ``@claims`` marker, or when the ladder names it as an unmarked rung (an
    unmarked dispatcher has no marker; its family is ``None`` unless the
    source shows one).
    """
    unmarked = {
        rung.producer for rung in decide_rungs(ladder) if not rung.marked
    }
    tree = ast.parse(POLICY_SOURCE.read_text(encoding="utf-8"))
    decide = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_decide"
    )
    parents = {
        child: node
        for node in ast.walk(decide)
        for child in ast.iter_child_nodes(node)
    }
    calls = []
    for node in ast.walk(decide):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name is None:
            continue
        method = getattr(HengbotPolicy, name, None) if "." not in name else None
        owner = getattr(method, CLAIM_OWNER_ATTRIBUTE, None)
        if owner is not None or name in unmarked:
            family = _call_site_family(
                node, parents, owner.value if owner is not None else None
            )
            calls.append((node.lineno, node.col_offset, name, family))
    return [(name, family) for _line, _col, name, family in sorted(calls)]


def _order_mismatch(ladder) -> list:
    """(producer, family) per call site against the ladder's decide rungs.

    An unmarked rung whose call site shows no family compares by producer.
    """
    expected = [(rung.producer, rung.family) for rung in decide_rungs(ladder)]
    found = _decide_calls(ladder)
    mismatch = []
    for index in range(max(len(expected), len(found))):
        want = expected[index] if index < len(expected) else None
        got = found[index] if index < len(found) else None
        if want is None or got is None:
            mismatch.append((index, want, got))
        elif want[0] != got[0] or (got[1] is not None and want[1] != got[1]):
            mismatch.append((index, want, got))
    return mismatch


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

    def test_revert_proof_swapping_families_between_call_sites(self):
        """Round 2 (F4): the same producer's call sites are told apart by
        the family each produces (``_flee_step`` x4, ``_hunt_step`` x3,
        ``_explore_step`` x2, ``_direction_key`` x2)."""
        for producer in (
            "_flee_step", "_hunt_step", "_explore_step", "_direction_key",
        ):
            with self.subTest(producer=producer):
                rungs = list(CLAIM_LADDER)
                sites = [
                    index for index, rung in enumerate(rungs)
                    if rung.producer == producer
                    and rung.section == SECTION_DECIDE
                ]
                first = sites[0]
                second = next(
                    index for index in sites[1:]
                    if rungs[index].family != rungs[first].family
                )
                a, b = rungs[first], rungs[second]
                rungs[first] = replace(a, family=b.family)
                rungs[second] = replace(b, family=a.family)
                self.assertNotEqual(_order_mismatch(tuple(rungs)), [])

    def test_every_marked_call_site_family_is_read_from_the_source(self):
        """No marked rung passes the order test on its producer alone."""
        for (name, family), rung in zip(_decide_calls(), decide_rungs()):
            with self.subTest(rung=rung.name):
                if rung.marked:
                    self.assertIsNotNone(family)

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
        policy._decision_triggers = None
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


# -- round 2 -----------------------------------------------------------------


def _old_owner_change(*, held_rank, held_goal_kind, held_goal_source,
                      held_survival, new_rank, new_survival):
    """The round-1 verdict: survival preempted regardless of rank."""
    from hengbot.claim_ladder import (
        PREEMPTION, VIOLATION, never_suspended,
    )

    if never_suspended(held_goal_kind, held_goal_source):
        return VIOLATION
    if new_survival and not held_survival:
        return PREEMPTION
    if new_rank < held_rank:
        return PREEMPTION
    return VIOLATION


def _top_only_resumable(stack, owner, goal, non_discardable=False):
    """The round-1 resolve: only the top of the stack could resume."""
    if (
        stack
        and stack[-1].owner == owner
        and stack[-1].goal == goal
        and stack[-1].non_discardable == non_discardable
    ):
        return len(stack) - 1
    return None


def _stack_ranks(register) -> list[int]:
    return [claim.rank for claim in register.suspended]


def _assert_bounded(case, register, current_rank=None):
    """Every push was by a strictly higher rank: bottom to top, the ranks
    strictly fall, so the depth can never exceed the number of ranks."""
    ranks = _stack_ranks(register)
    case.assertEqual(ranks, sorted(set(ranks), reverse=True))
    case.assertLessEqual(len(ranks), len({rung.rank for rung in CLAIM_LADDER}))


class BoundedStackTest(unittest.TestCase):
    """Round 2, F1: a push is by a strictly higher rank; survival that is
    not strictly higher replaces; a buried claim of the same owner and goal
    resumes."""

    ALTERNATION = (
        ("combat:disengage-seek-upstairs", 3),  # escape, survival, Reach
        ("detected:prepare-choke", 4),          # positioning, ranks higher
    )

    def _alternate(self, run, rounds=6):
        rows = []
        for _round in range(rounds):
            for reason, offset in self.ALTERNATION:
                rows.append(run.decide(reason, cell=run.cell(offset)))
        return rows

    def test_the_reviewers_alternation_stays_bounded_and_resumes(self):
        run = _Decisions()
        rows = self._alternate(run)
        depths = [row["suspended_depth"] for row in rows]
        self.assertLessEqual(max(depths), 1)
        _assert_bounded(self, run.register)
        escape = [row for row in rows if row["owner"] == "escape"]
        # one escape claim, suspended by positioning and resumed each round
        self.assertEqual({row["claim_id"] for row in escape},
                         {escape[0]["claim_id"]})
        self.assertEqual(sum(1 for row in escape if row["resumed"]), 5)
        positioning = [row for row in rows if row["owner"] == "positioning"]
        for row in positioning:
            self.assertEqual(row["closed_claim"]["closed_reason"],
                             "preempted-by:positioning")
        for row in escape[1:]:
            # survival does not outrank positioning: it replaces it
            self.assertEqual(
                (row["closed_claim"]["owner"], row["closed_claim"]["closed"],
                 row["closed_claim"]["closed_reason"]),
                ("positioning", "release", "survival-displaced"),
            )
            self.assertIsNone(row["violation"])

    def test_revert_proof_round_one_survival_rule_grows_the_stack(self):
        from unittest.mock import patch

        run = _Decisions()
        with patch("hengbot.policy.claim_owner_change", _old_owner_change), \
                patch("hengbot.policy.claim_resumable_index",
                      _top_only_resumable), \
                patch("hengbot.policy.claim_nests_over",
                      lambda *, top_rank, new_rank: True):
            rows = self._alternate(run)
        self.assertGreater(max(row["suspended_depth"] for row in rows), 6)

    def test_a_buried_claim_of_the_same_owner_and_goal_resumes(self):
        run = _Decisions()
        walk = run.decide("threat:avoid-engagement", cell=run.cell(3))
        exit_walk = run.decide("survival:seek-exit", cell=run.cell(4))
        self.assertEqual(exit_walk["closed_claim"]["claim_id"], walk["claim_id"])
        run.decide("melee")
        self.assertEqual(
            [claim.claim_id for claim in run.register.suspended],
            [walk["claim_id"], exit_walk["claim_id"]],
        )
        # positioning comes back to the same cell from a rung that outranks
        # the exit walk above it: the buried claim resumes, the exit walk
        # stays suspended above it
        back = run.decide("threat:reposition", cell=run.cell(3))
        self.assertEqual(back["claim_id"], walk["claim_id"])
        self.assertEqual(back["resumed"]["claim_id"], walk["claim_id"])
        self.assertIsNone(back["suspended_closed"])
        self.assertEqual(
            [claim.claim_id for claim in run.register.suspended],
            [exit_walk["claim_id"]],
        )
        _assert_bounded(self, run.register)
        self.assertLess(run.register.current.rank, _stack_ranks(run.register)[-1])

    def test_revert_proof_top_only_resume_leaves_it_buried(self):
        from unittest.mock import patch

        run = _Decisions()
        walk = run.decide("threat:avoid-engagement", cell=run.cell(3))
        run.decide("survival:seek-exit", cell=run.cell(4))
        run.decide("melee")
        with patch("hengbot.policy.claim_resumable_index", _top_only_resumable):
            back = run.decide("threat:reposition", cell=run.cell(3))
        self.assertNotEqual(back["claim_id"], walk["claim_id"])
        self.assertIsNone(back["resumed"])

    def test_the_stack_stays_bounded_on_any_sequence(self):
        import random

        reasons = (
            ("seek-loot", 3), ("melee", None), ("detected:prepare-choke", 4),
            ("combat:disengage-seek-upstairs", 5), ("emergency:seek-upstairs", 6),
            ("explore", 7), ("return:recall", None), ("threat:reposition", 3),
            ("survival:seek-exit", 4), ("fundraise:seek-treasure", 5),
            ("ranged:fire-target", None), ("esp-threat:hunt-strong", 6),
            ("threat:avoid-engagement", 7), ("breakout:seek-frontier", 3),
        )
        chooser = random.Random(20260925)
        run = _Decisions()
        for _step in range(600):
            reason, offset = chooser.choice(reasons)
            run.decide(
                reason, cell=None if offset is None else run.cell(offset)
            )
            _assert_bounded(self, run.register)
            current = run.register.current
            if run.register.suspended and current is not None and (
                current.is_open
            ):
                self.assertLess(current.rank, _stack_ranks(run.register)[-1])


class SameOwnerGoalChangeTest(unittest.TestCase):
    """Round 2, F2: a same-owner goal change is a retarget violation, or on
    a survival decision the survival exemption -- never a preemption
    followed by ``resume-goal-changed`` on the same row."""

    def _assert_survival_displaced(self, row, held):
        self.assertEqual(
            (row["closed_claim"]["claim_id"], row["closed_claim"]["closed"],
             row["closed_claim"]["closed_reason"]),
            (held["claim_id"], "release", "survival-displaced"),
        )
        self.assertIsNone(row["violation"])
        self.assertIsNone(row["suspended_closed"])
        self.assertEqual(row["suspended_depth"], 0)
        self.assertTrue(row["survival"])

    def test_an_escape_walk_turning_to_an_emergency_goal(self):
        for first in ("breeder-breakthrough:seek-upstairs", "emergency:seek-upstairs"):
            with self.subTest(held=first):
                run = _Decisions()
                held = run.decide(first, cell=run.cell(3))
                self.assertEqual(held["owner"], "escape")
                row = run.decide("emergency:seek-upstairs", cell=run.cell(5))
                self._assert_survival_displaced(row, held)
                self.assertNotEqual(row["claim_id"], held["claim_id"])

    def test_a_return_walk_turning_to_an_esp_threat_leave(self):
        run = _Decisions()
        run.policy._survival_return_trigger = None
        held = run.decide("return:seek-upstairs", cell=run.cell(3))
        self.assertFalse(held["survival"])
        row = run.decide("esp-threat:leave-stairs")
        self.assertEqual((row["owner"], row["goal"]["kind"]),
                         ("departure", "Observe"))
        self._assert_survival_displaced(row, held)

    def test_without_survival_it_is_a_retarget_violation(self):
        run = _Decisions()
        held = run.decide("breeder-breakthrough:seek-upstairs", cell=run.cell(3))
        row = run.decide("breeder-breakthrough:seek-upstairs", cell=run.cell(5))
        self.assertEqual(row["violation"]["kind"], "retarget")
        self.assertIsNone(row["closed_claim"])
        self.assertEqual(row["violation"]["claim_id"], held["claim_id"])

    def test_a_continuing_claim_takes_the_survival_flag_of_its_decision(self):
        run = _Decisions()
        run.policy._survival_return_trigger = None
        held = run.decide("return:seek-upstairs", cell=run.cell(3))
        run.policy._survival_return_trigger = "esp-threat"
        row = run.decide("return:seek-upstairs", cell=run.cell(3))
        self.assertEqual(row["claim_id"], held["claim_id"])
        self.assertTrue(row["survival"])
        self.assertTrue(run.register.current.survival)
        self.assertIsNone(row["closed_claim"])


class TriggerSetTest(unittest.TestCase):
    """Round 2, F3/F4: the design 5.4.1 trigger set, from the producer's own
    selection, on a recorded board with hostiles inside and outside it."""

    rows = None

    @classmethod
    def setUpClass(cls):
        skill, raws = _Replay.dungeon_boards()
        policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
        policy.consume_skill_knowledge(skill)
        cls.rows = []
        for raw in raws:
            board = parse_snapshot(raw, _Replay.knowledge())
            key = policy.choose_key(board)
            key = policy.validate_read_key(board, key)
            cls.rows.append((board, policy.last_reason, dict(policy.decision_claim)))
            policy.confirm_key_posted(key)

    def test_the_look_ahead_set_and_nothing_else(self):
        opened = [
            (board, claim) for board, reason, claim in self.rows
            if reason == "detected:prepare-choke"
        ]
        self.assertTrue(opened)
        first_ids = {}
        for board, claim in opened:
            first_ids.setdefault(claim["claim_id"], (board, claim))
        self.assertEqual(len(first_ids), 2)
        for board, claim in first_ids.values():
            hostile = [
                monster for monster in (
                    *board.visible_monsters, *board.detected_monsters
                ) if monster.hostile
            ]
            look_ahead = sorted(
                [monster.index, monster.race_id] for monster in hostile
                if monster.perception == "detected"
                and not monster.asleep
                and monster.distance <= SWARM_LOOKAHEAD
                and monster.max_ranged_damage <= 0
            )
            outside = sorted(
                [monster.index, monster.race_id] for monster in hostile
            )
            self.assertEqual(claim["trigger_monsters"], look_ahead)
            # the board has perceived hostiles outside the set
            self.assertLess(len(look_ahead), len(outside))
            self.assertEqual(claim["last_perceived_turn"], board.turn)

    def test_a_continuing_claim_keeps_its_set_and_tracks_perception(self):
        by_id = {}
        for board, reason, claim in self.rows:
            if reason != "detected:prepare-choke":
                continue
            by_id.setdefault(claim["claim_id"], []).append((board, claim))
        for rows in by_id.values():
            sets = {tuple(map(tuple, claim["trigger_monsters"])) for _b, claim in rows}
            self.assertEqual(len(sets), 1)
            for board, claim in rows:
                wanted = {tuple(pair) for pair in claim["trigger_monsters"]}
                perceived = any(
                    (monster.index, monster.race_id) in wanted
                    for monster in (*board.visible_monsters, *board.detected_monsters)
                )
                if perceived:
                    self.assertEqual(claim["last_perceived_turn"], board.turn)

    def test_a_hunt_records_its_own_target_only(self):
        from hengbot.claim_register import reach_monster

        run = _Decisions()
        policy = run.policy
        policy._decision_sequence += 1
        policy._decision_goal = ("hunt", reach_monster(9, 99), None)
        policy._decision_expectation = None
        policy._decision_triggers = None
        policy.last_reason = "hunt"
        policy._record_decision_claim(run.board, "k")
        self.assertEqual(policy.decision_claim["trigger_monsters"], [[9, 99]])

    def test_an_undeclared_producer_records_none(self):
        run = _Decisions()
        # positioning without a declared selection: no invented set
        self.assertIsNone(
            run.decide("detected:prepare-choke", cell=run.cell(3))[
                "trigger_monsters"]
        )
        # and a family outside rev 10.1 item 9 records none, declared or not
        run.policy._decision_triggers = ("floor-loot", ((1, 2),))
        self.assertEqual(
            run.policy._claim_trigger_monsters(
                ClaimOwner.FLOOR_LOOT, reach(run.cell(4))
            ),
            (),
        )
        # a slot of another family is not used
        run.policy._decision_triggers = ("escape", ((1, 2),))
        self.assertEqual(
            run.policy._claim_trigger_monsters(
                ClaimOwner.POSITIONING, reach(run.cell(4))
            ),
            (),
        )


class PickupCensusTest(unittest.TestCase):
    """Round 2, F5: the loot producer's own pickup reasons are floor-loot."""

    def test_pickup_and_auto_destroy_are_floor_loot(self):
        from hengbot.claim_goal_typing import goal_typing

        for reason in ("pickup", "trigger-autodestroy"):
            with self.subTest(reason=reason):
                self.assertEqual(reason_owner_family(reason), "floor-loot")
                self.assertEqual(goal_typing("floor-loot", reason).kind,
                                 "Terminal")
                self.assertEqual(rung_of("floor-loot", reason).name,
                                 "_normal_loot_key#2")
        # the prefixed variants keep their own producers' families
        self.assertEqual(reason_owner_family("fundraise:pickup"), "fundraising")
        self.assertEqual(reason_owner_family("victory:pickup"), "floor-loot")
        self.assertEqual(
            reason_owner_family("mana-food:trigger-autodestroy"), "survival"
        )


class RoundThreeTest(unittest.TestCase):
    """Round 3 (the re-review of d0aa2f86)."""

    def test_the_overflow_block_ranks_at_its_own_rung(self):
        rung = rung_of("town-plan", "town:blocked:overflow-no-legal-disposal")
        self.assertEqual(rung.producer, "_town_overflow_destroy_key")
        self.assertGreater(rung.rank, 2)
        self.assertLess(rung.rank, TOWN_RANK)
        # every other town:blocked stays at town-plan's rewrite rung
        self.assertEqual(rung_of("town-plan", "town:blocked:owner-retired").rank, 1)

    def _suspended_store_walk(self):
        from hengbot.model import Position
        from hengbot.policy_types import StoreVisit

        run = _Decisions()
        entrance = run.cell(3)
        run.policy._store_visit = StoreVisit(
            owner="store-router", purpose="test", store_type=1,
            goal=Position(*entrance),
        )
        walk = run.decide("shop:approach", cell=entrance)
        self.assertEqual(walk["owner"], "store-router")
        swing = run.decide("melee")
        self.assertEqual(swing["closed_claim"]["claim_id"], walk["claim_id"])
        self.assertEqual(swing["suspended_depth"], 1)
        inside = replace(run.board, store=object())
        return run, walk, inside

    def test_a_suspended_walk_completes_on_entering_its_store(self):
        run, walk, inside = self._suspended_store_walk()
        # combat still holds the decision (it nests over the walk), so only
        # the completion test can end the walk
        row = run.decide("melee", board=inside)
        closings = {
            entry["claim_id"]: (entry["closed"], entry["closed_reason"])
            for entry in row["suspended_closed"]
        }
        self.assertEqual(closings, {walk["claim_id"]: ("complete", "entered-store")})
        self.assertEqual(row["suspended_depth"], 0)

    def test_revert_proof_cell_equality_alone_leaves_it_suspended(self):
        from unittest.mock import patch

        run, walk, inside = self._suspended_store_walk()
        with patch.object(
            HengbotPolicy, "_claim_entered_store_at",
            lambda self, snapshot, cell: False,
        ):
            row = run.decide("melee", board=inside)
        self.assertIsNone(row["suspended_closed"])
        self.assertEqual(row["suspended_depth"], 1)

    def _floorless_register(self, run, cell):
        register = ClaimRegister()
        claim = register.declare(ClaimOwner.FLOOR_LOOT, reach(cell))
        object.__delattr__(claim, "floor")
        return register, claim

    def test_a_floorless_claim_suspended_now_expires_on_the_next_floor(self):
        run = _Decisions()
        register, claim = self._floorless_register(run, run.cell(3))
        run.policy._claim_register = pickle.loads(pickle.dumps(register))
        self.assertIsNone(run.register.current.floor)
        swing = run.decide("melee")
        self.assertEqual(swing["closed_claim"]["claim_id"], claim.claim_id)
        (stacked,) = run.register.suspended
        self.assertEqual(stacked.floor, tuple(run.board.floor_key))
        self._assert_expires_on_the_next_floor(run, claim)

    def test_a_floorless_claim_restored_on_the_stack_expires(self):
        run = _Decisions()
        register, claim = self._floorless_register(run, run.cell(3))
        register.suspend("preempted-by:combat")  # the round-2 writer's stack
        (stacked,) = register.suspended
        self.assertIsNone(stacked.floor)
        state = {"_claim_register": register}
        restored = pickle.loads(pickle.dumps(state))["_claim_register"]
        run.policy._claim_register = restored
        # the first board that sees it suspended stamps its floor ...
        run.decide("melee")
        (stamped,) = run.register.suspended
        self.assertEqual(stamped.floor, tuple(run.board.floor_key))
        self._assert_expires_on_the_next_floor(run, claim)

    def _assert_expires_on_the_next_floor(self, run, claim):
        floor = run.board.floor_key
        elsewhere = replace(run.board, floor_key=(floor[0], floor[1] + 1, floor[2]))
        row = run.decide("explore", cell=run.cell(5), board=elsewhere)
        closings = {
            entry["claim_id"]: (entry["closed"], entry["closed_reason"])
            for entry in row["suspended_closed"]
        }
        self.assertEqual(
            closings, {claim.claim_id: ("release", "suspended-expired")}
        )
        self.assertEqual(row["suspended_depth"], 0)


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
        self.assertNotIn("_decision_triggers", state)
        restored = restore_checkpoint(HengbotPolicy, encoded)
        self.assertIsNone(restored.__dict__["_decision_triggers"])
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
