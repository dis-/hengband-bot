#!/usr/bin/env python3
"""Fail on an owner family without a town visit stage (town rebuild stage 3-1).

usage: PYTHONPATH=src python scripts/town_visit_plan_lint.py

Checks hengbot.town_visit_plan.FAMILY_STAGE against the one family list
(town_arbiter.owner_families): every family has a row, every row names a
registered family, and every row's stage is one of STAGES, INTERRUPT or
REWRITE.  Every stage of STAGES is some family's.  Every owner's stage
transition (TRANSITIONS, stage 3-3e) names a family with a stage that is not
the rewrite stage and a method the policy has.  Exit status 1 on a gap.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def problems() -> list[str]:
    sys.path.insert(0, str(ROOT / "src"))
    from hengbot.town_arbiter import owner_families
    from hengbot.policy import HengbotPolicy
    from hengbot.town_visit_plan import FAMILY_STAGE, INTERRUPT, REWRITE, STAGES, TRANSITIONS

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
    return found


def main() -> int:
    found = problems()
    for problem in found:
        print(f"town-visit-plan-lint: {problem}")
    print(f"town-visit-plan-lint: {len(found)} gap(s)")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
