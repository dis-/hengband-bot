#!/usr/bin/env python3
"""Fail on an owner family without a town visit stage (town rebuild stage 3-1).

usage: PYTHONPATH=src python scripts/town_visit_plan_lint.py

Checks hengbot.town_visit_plan.FAMILY_STAGE against the one family list
(town_arbiter.owner_families): every family has a row, every row names a
registered family, and every row's stage is one of STAGES, INTERRUPT or
REWRITE.  Every stage of STAGES is some family's.  Every owner's stage
transition (TRANSITIONS, stage 3-3e) names a family with a stage that is not
the rewrite stage and a method the policy has.  The claim ladder ranks the
plan's rows from the plan's names (stage 3-4): the progress step's rung and
the progress invariant's reasons.  Every stage of STAGES has a deadline
(STAGE_DEADLINES, stage 3-5) of twice its larger measurement, but for the
unmeasured stages (UNMEASURED_STAGES), which have none.  Exit status 1 on
a gap.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def problems() -> list[str]:
    sys.path.insert(0, str(ROOT / "src"))
    from hengbot.town_arbiter import owner_families
    from hengbot.policy import HengbotPolicy
    from hengbot import town_hold
    from hengbot.town_visit_plan import (
        FAMILY_STAGE, INTERRUPT, PLAN_DETECTOR_REASONS, PROGRESS_INVARIANT_RUNG, REWRITE,
        STAGE_DEADLINES, STAGE_MEASURED, STAGES, STEP_RUNG, TRANSITIONS, UNMEASURED_STAGES,
    )

    families = set(owner_families())
    found = []
    for family in sorted(families - set(FAMILY_STAGE)):
        found.append(f"family {family!r} has no stage row")
    for family, stage in sorted(FAMILY_STAGE.items()):
        if family not in families:
            found.append(f"FAMILY_STAGE: {family!r} is no owner family (stale row)")
        if stage not in {*STAGES, INTERRUPT, REWRITE}:
            found.append(f"FAMILY_STAGE: {family!r} names unknown stage {stage!r}")
    for stage in STAGES:
        if stage not in FAMILY_STAGE.values():
            found.append(f"STAGES: {stage!r} is no family's stage")
    for name, (family, method) in TRANSITIONS.items():
        if FAMILY_STAGE.get(family, REWRITE) == REWRITE:
            found.append(f"TRANSITIONS: {name!r} belongs to {family!r}, no owner's stage")
        if not callable(getattr(HengbotPolicy, method, None)):
            found.append(f"TRANSITIONS: {name!r} names {method!r}, which the policy lacks")
    for stage in STAGES:
        if stage not in STAGE_MEASURED:
            found.append(f"STAGE_MEASURED: stage {stage!r} has no measurement")
        elif stage in UNMEASURED_STAGES:
            if STAGE_DEADLINES.get(stage) is not None:
                found.append(f"STAGE_DEADLINES: {stage!r} is unmeasured and has a deadline")
        elif STAGE_DEADLINES.get(stage) != 2 * max(STAGE_MEASURED[stage]):
            found.append(f"STAGE_DEADLINES: {stage!r} is not twice its larger measurement")
    for stage in sorted(set(STAGE_MEASURED) - set(STAGES)):
        found.append(f"STAGE_MEASURED: {stage!r} is no stage (stale row)")
    step = town_hold.rung_named(STEP_RUNG[0])
    if step is None or (step.family, step.section) != (STEP_RUNG[1], town_hold.SECTION_REWRITE):
        found.append(f"STEP_RUNG: the ladder has no {STEP_RUNG[1]!r} rewrite rung {STEP_RUNG[0]!r}")
    for reason in PLAN_DETECTOR_REASONS:
        rung = town_hold.rung_of(PROGRESS_INVARIANT_RUNG[1], reason)
        if rung.name != PROGRESS_INVARIANT_RUNG[0]:
            found.append(f"PROGRESS_INVARIANT_RUNG: {reason!r} ranks at "
                         f"{rung.name!r}, not the plan's rung")
    return found


def main() -> int:
    found = problems()
    for problem in found:
        print(f"town-visit-plan-lint: {problem}")
    print(f"town-visit-plan-lint: {len(found)} gap(s)")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
