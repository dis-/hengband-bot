#!/usr/bin/env python3
"""Measure the town visit stages' per-visit maxima from recorded journals (town rebuild 3-5).

usage: PYTHONPATH=src python scripts/town_stage_deadline_measure.py <captures root> [...]

Owner 2026-11-14 「ループと止まり以外の全訪問で測る」 and 「歩きは数えない」: every
``town-arrival`` journal under the roots is one visit.  Counted are the visits that did not
end in a loop or a stop: a visit that reached its departure (counted up to the recall read or
the stairs and through the recall countdown that follows), a visit that ended in the player's
death, and a Zul round trip (a visit with ``town:zul:`` decisions).  A forced repetition
departure is a loop.  Each recorded reason is put in its stage as the stage trace does (the
arbiter's census family, town_visit_plan.stage_of); a walk is not counted
(town_visit_plan.is_walking).
The output is the per-stage maximum to compare with town_visit_plan.STAGE_MEASURED.
"""
from __future__ import annotations

import collections
import gzip
import json
from pathlib import Path
import sys

DEPARTED = ("town:recall-to-", "town:wait-recall", "descend")
COUNTDOWN = ("town:recall-to-", "town:wait-recall", "town:await-recall-confirmation")
LOOP_DEPARTURE = ("town:repetition-depart", "repetition-depart")


def visit_span(reasons: list[str], kind: str) -> tuple[int, str] | None:
    """The counted rows of one visit (how many) and why it counts, or None (a loop or a stop)."""
    hit = next((i for i, reason in enumerate(reasons) if reason.startswith(DEPARTED)), None)
    looped = any(reason.startswith(LOOP_DEPARTURE)
                 for reason in (reasons[:hit + 1] if hit is not None else reasons))
    if hit is not None and not looped:
        end = hit + 1
        while end < len(reasons) and reasons[end].startswith(COUNTDOWN):
            end += 1
        return end, "departed"
    if "death" in kind and not looped:
        return len(reasons), "death"
    if any(reason.startswith("town:zul:") for reason in reasons):
        return len(reasons), "zul round trip"
    return None


def main(roots: list[str]) -> int:
    from hengbot.town_arbiter import _new_town_turn_arbiter
    from hengbot.town_visit_plan import (
        MEASURE_AT_VISITS, STAGE_MEASURED, UNMEASURED_STAGES, is_walking, stage_of,
    )

    arbiter = _new_town_turn_arbiter()
    peak: collections.Counter = collections.Counter()
    source: dict[str, str] = {}
    having: collections.Counter = collections.Counter()
    counted: collections.Counter = collections.Counter()
    skipped = 0
    for root in roots:
        for journal in sorted(Path(root).rglob("town-arrival/journal.jsonl.gz")):
            rows = [json.loads(line) for line in gzip.open(journal, "rt", encoding="utf-8")]
            capture = journal.parent.parent
            kind = capture.name
            meta = capture / "meta.json"
            if meta.is_file():
                kind = json.loads(meta.read_text(encoding="utf-8")).get("kind") or kind
            span = visit_span([row.get("reason") or "" for row in rows], kind)
            if span is None:
                skipped += 1
                continue
            counted[span[1]] += 1
            stages = collections.Counter(
                stage_of(arbiter.ownership_family(row.get("reason") or ""))
                for row in rows[:span[0]]
                if not is_walking(row.get("key"), row.get("reason")))
            for stage in STAGE_MEASURED:
                if stages[stage]:
                    having[stage] += 1
                if stages[stage] > peak[stage]:
                    peak[stage], source[stage] = stages[stage], str(capture)
    print(f"counted {dict(counted)}, excluded (loop or stop) {skipped}")
    print(f"unmeasured stages {sorted(UNMEASURED_STAGES)} get a deadline at "
          f"{MEASURE_AT_VISITS} visits with the stage")
    for stage, measured in STAGE_MEASURED.items():
        print(f"{stage:15s} journals {peak[stage]:4d} (visits with the stage {having[stage]:3d})"
              f"  STAGE_MEASURED {measured}  max from {source.get(stage, '-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
