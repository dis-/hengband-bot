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

# A visit's trace keeps its newest segments only.
SEGMENT_LIMIT = 200


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


def facts(policy: Any) -> dict:
    """The decision log's view: the current stage and the visit's flow."""
    from hengbot.town_visit import town_visit
    segments = town_visit(policy).plan_segments
    if not segments:
        return {}
    stage, since, _last, decisions, interrupts = segments[-1]
    return {
        "stage": stage,
        "since": since,
        "decisions": decisions,
        "interrupts": interrupts,
        "flow": [segment[0] for segment in segments[-12:]],
    }
