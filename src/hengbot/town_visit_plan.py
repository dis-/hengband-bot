"""The town visit's stages: one table, one trace (town rebuild stage 3-1).

Owner 2026-11-12 「1〜3まで一気に進める」, stage 3 「町の訪問を明示した計画（状態の流れ）に」:
the town visit becomes an explicit plan whose stages replace the hold flags
and the late rewrite layers, and the owner-retired burst becomes per-stage
deadlines.  Stage 3-1 names the stages and the stage of every town decision;
nothing decides from it yet, so no decision changes.

``STAGES`` is the visit's flow in its order; ``FAMILY_STAGE`` gives every
owner family (``town_arbiter.owner_families``, the one family list) its stage.
A family of the dungeon ladder that may still answer a town board (survival,
combat, escape, the detectors, bookkeeping ...) is an ``INTERRUPT``: it
answers inside the stage the plan is in and does not move it.  ``town-plan``
-- the progress seam ``_town_procurement_decision`` and the town end's
blocked keys -- is the ``REWRITE`` stage: the layer stage 3 retires, so the
trace counts how often it still answers.

``note_decision`` runs on the ``choose_key`` exit of a town board and keeps
the visit's trace (``TownVisit.plan_segments``): one segment per run of
decisions in one stage, ``[stage, first_sequence, last_sequence, decisions,
interrupts]``.  ``facts`` is the decision log's view of it.

scripts/town_visit_plan_lint.py fails on an owner family without a stage, a
stale row, or a stage outside ``STAGES`` (0 gaps).
"""
from __future__ import annotations

from typing import Any

# The visit's stages, in the order a visit flows through them.
STAGES: tuple[str, ...] = (
    "home",            # Home catalogue, withdrawals, deposits, disposal
    "identification",  # identification, curses and enchantment
    "equipment",       # the equipment optimizer and its transaction
    "sell",            # sales
    "buy",             # purchases and the store router's walks
    "quest",           # quest requests, rewards, bounties
    "travel",          # cross-town shopping and rumours
    "fundraising",     # a fundraising run decided in town
    "departure",       # leaving town (stairs, recall, wilderness)
)
INTERRUPT = "interrupt"
REWRITE = "rewrite"

FAMILY_STAGE: dict[str, str] = {
    "home-errand": "home",
    "home-scan": "home",
    "home-visit": "home",
    "identification": "identification",
    "curse-enchant": "identification",
    "equipment-opt": "equipment",
    "equipment-txn": "equipment",
    "shop-sell": "sell",
    "shop-buy": "buy",
    "store-router": "buy",
    "quest-request": "quest",
    "cross-town": "travel",
    "rumor": "travel",
    "fundraising": "fundraising",
    "departure": "departure",
    "town-plan": REWRITE,
    # The dungeon ladder's families: they answer inside the current stage.
    "survival": INTERRUPT,
    "detectors": INTERRUPT,
    "positioning": INTERRUPT,
    "esp-threat": INTERRUPT,
    "escape": INTERRUPT,
    "combat": INTERRUPT,
    "hunt": INTERRUPT,
    "explore": INTERRUPT,
    "floor-loot": INTERRUPT,
    "quest-sweep": INTERRUPT,
    "bookkeeping": INTERRUPT,
    "idle": INTERRUPT,
    "misc": INTERRUPT,
}

# The owners' stage transitions (town rebuild stage 3-3e).  After the owner of
# a town decision has spoken, the plan may move the visit to another owner's
# step: these are every replacement the progress step
# (``_town_procurement_decision``) makes, each named and owned by the family
# whose stage the result belongs to.  name -> (owner family, the TownMixin
# method that decides it), in the order the step consults them.  A method
# returns ``STAY`` when its transition does not apply (the step goes on), and
# declares its name with ``note_transition`` when it replaces the decision.
# scripts/town_visit_plan_lint.py fails on a family without a stage, the
# rewrite stage, or a method the policy lacks.
TRANSITIONS: dict[str, tuple[str, str]] = {
    # Closing equipment over an overweight pack shows Home's weight relief.
    "closing-equipment-weight": ("home-visit", "_closing_equipment_weight_transition"),
    # A Home sequence holding the store router keeps the holder's step.
    "holder-keeps-store-router": ("store-router", "_store_router_hold_transition"),
    # An admitted town-loot walk continues until the pickup.
    "committed-loot": ("floor-loot", "_committed_loot_transition"),
    # A repeated, ineffective step to a bounty's cell names its route.
    "bounty-route-nonprogress": ("quest-request", "_bounty_route_nonprogress_transition"),
    # A posted shop operation's await is its defect, not a new errand.
    "posted-shop-operation": ("shop-buy", "_posted_shop_operation_transition"),
    # The identify-staff shortage keeps its direct supplier route.
    "identify-staff-supplier": ("fundraising", "_identify_staff_supplier_transition"),
    # A town step that makes no progress hands over to the supplier walk.
    "progress-handover": ("store-router", "_progress_handover_transition"),
}
# A transition method's answer when its transition does not apply.
STAY = object()

# -- the plan's rows on the claim ladder (town rebuild stage 3-4) ----------
# town_hold's ladder, town_arbiter's family registration and the reasons the
# transitions write read these names here.  The ranks are unchanged.
# The progress step itself: the ``town-plan`` family's rung in the ladder's
# rewrite section (``town_hold._RUNGS``), ranked after the detectors.
STEP_RUNG: tuple[str, str] = ("_town_procurement_decision", "town-plan")
# The progress invariant's reasons, which the transitions (and the shop
# owner's continuation of an observed shelf) write.  They belong to the
# detectors' family and rank at the detectors' rewrite rank, where they ranked
# as the cycle detector's ordinary rung; the ladder names their rung after
# the plan (``PROGRESS_INVARIANT_RUNG``: producer label, family).
PROGRESS_INVARIANT_PREFIX = "town-progress-invariant:"
PROGRESS_INVARIANT_RUNG: tuple[str, str] = ("town-visit-plan:progress-invariant", "detectors")
PROGRESS_DEFECT_PREFIX = PROGRESS_INVARIANT_PREFIX + "defect:"
PROGRESS_APPROACH_REASON = PROGRESS_INVARIANT_PREFIX + "approach"
CONTINUE_OBSERVED_SHOP_REASON = PROGRESS_INVARIANT_PREFIX + "continue-observed-shop"
# The town repetition cycle's one-turn break (_town_special_key): a detectors'
# reason of the visit too, ranked at the same plan rung (stage 3-4b).
CYCLE_BREAK_REASON = "town:cycle-break"
# The reasons the plan's detector-family rung ranks.
PLAN_DETECTOR_REASONS: tuple[str, ...] = (PROGRESS_INVARIANT_PREFIX, CYCLE_BREAK_REASON)


def progress_defect_reason(winner: str, progress: str) -> str:
    """The reason of a decision the progress invariant names a defect: the
    producer's reason ``winner`` and the progress action that replaced it."""
    return f"{PROGRESS_DEFECT_PREFIX}{winner}=>{progress}"

# A visit's trace keeps its newest segments only.
SEGMENT_LIMIT = 200
# A visit keeps its newest seam replacements and transitions only.
REWRITE_LIMIT = 100


def stage_of(family: str | None) -> str:
    """The stage of an owner family; an unknown family interrupts."""
    return FAMILY_STAGE.get(family or "", INTERRUPT)


def note_decision(policy: Any, snapshot: Any) -> None:
    """Record the stage of the town decision just made (no decision reads it)."""
    if not (snapshot.in_town or snapshot.store is not None):
        return
    from hengbot.town_hold import claim_family_of
    from hengbot.town_visit import town_visit
    stage = stage_of(claim_family_of(policy, policy.last_reason))
    sequence = getattr(policy, "_decision_sequence", None)
    segments = town_visit(policy).plan_segments
    if stage == INTERRUPT:
        if segments:
            segments[-1][2] = sequence
            segments[-1][4] += 1
        else:
            segments.append([INTERRUPT, sequence, sequence, 0, 1])
        return
    if segments and segments[-1][0] in {stage, INTERRUPT} and segments[-1][3] == 0:
        # The visit opened on interrupts: they belong to its first stage.
        segments[-1][0] = stage
    if segments and segments[-1][0] == stage:
        segments[-1][2] = sequence
        segments[-1][3] += 1
    else:
        segments.append([stage, sequence, sequence, 1, 0])
        del segments[:-SEGMENT_LIMIT]


def note_transition(policy: Any, name: str) -> None:
    """Declare that this decision's owner transition ``name`` replaces it."""
    from hengbot.town_visit import town_visit
    town_visit(policy).transition_declared = name


def note_seam(policy: Any, snapshot: Any, before: tuple, key: Any) -> None:
    """Record a town decision the progress step (``_town_procurement_decision``)
    replaced: its key or its reason changed across the step (stage 3-3a).

    A replacement an owner's transition declared (``note_transition``, stage
    3-3e) is that owner's stage transition (``plan_transitions``); any other is
    a seam rewrite (``plan_rewrites``), the late layer stage 3 retires.  The
    ``town-plan`` family counts only the decisions whose reason was renamed
    into its own family; a replacement that keeps the producer's reason and
    changes the key, or relabels under another family, is counted here.
    Nothing decides from it.
    """
    from hengbot.town_visit import town_visit
    visit = town_visit(policy)
    declared, visit.transition_declared = visit.transition_declared, None
    if not (snapshot.in_town or snapshot.store is not None):
        return
    if (key, policy.last_reason) == before:
        return
    sequence = getattr(policy, "_decision_sequence", None)
    if declared is not None:
        visit.plan_transitions.append([sequence, declared, before[1], policy.last_reason])
        del visit.plan_transitions[:-REWRITE_LIMIT]
        return
    visit.plan_rewrites.append([sequence, before[1], policy.last_reason])
    del visit.plan_rewrites[:-REWRITE_LIMIT]


def facts(policy: Any) -> dict:
    """The decision log's view: the current stage and the visit's flow."""
    from hengbot.town_visit import town_visit
    visit = town_visit(policy)
    segments = visit.plan_segments
    if not segments:
        return {}
    stage, since, _last, decisions, interrupts = segments[-1]
    return {
        "stage": stage,
        "since": since,
        "decisions": decisions,
        "interrupts": interrupts,
        "flow": [segment[0] for segment in segments[-12:]],
        "seam_rewrites": len(visit.plan_rewrites),
        "stage_transitions": len(visit.plan_transitions),
    }
