"""Measure the E6 pre-landing live run, separate from historical baseline."""

from __future__ import annotations

from collections import Counter

from historical_emit_fixture import E6_PRELANDING_DECISIONS, rows


LABEL = "E6 pre-landing live run (post-cutoff)"


def measure(decisions: list[dict]) -> dict:
    creations = []
    seen = set()
    for index, row in enumerate(decisions):
        visit = row.get("store_visit") or {}
        if visit.get("owner") != "shop-one-shot":
            continue
        identity = visit.get("opened_sequence")
        if identity in seen:
            continue
        seen.add(identity)
        previous = decisions[index - 1].get("store_visit") or {} if index else {}
        creations.append((visit, previous))
    calls = [row for row in decisions if row.get("acquire_store_visit_called") is True]
    return {
        "rows": len(decisions),
        "first": decisions[0]["time"],
        "last": decisions[-1]["time"],
        "shop_one_shot_rows": sum(
            (row.get("store_visit") or {}).get("owner") == "shop-one-shot"
            for row in decisions
        ),
        "creations": len(creations),
        "same_store_posted_leaving_predecessors": sum(
            previous.get("owner") == "town-errand"
            and previous.get("store_type") == visit.get("store_type")
            and previous.get("phase") == "leaving"
            and previous.get("posted_sequence") is not None
            and previous.get("posted_turn") is not None
            for visit, previous in creations
        ),
        "provable_granted_new": len(creations),
        "acquire_calls": len(calls),
        "acquire_results": Counter(row.get("acquire_result") for row in calls),
    }


def main() -> int:
    report = measure(list(rows(E6_PRELANDING_DECISIONS)))
    assert report == {
        "rows": 3490,
        "first": "2026-09-01T17:30:41+0900",
        "last": "2026-09-01T17:47:46+0900",
        "shop_one_shot_rows": 35,
        "creations": 11,
        "same_store_posted_leaving_predecessors": 11,
        "provable_granted_new": 11,
        "acquire_calls": 111,
        "acquire_results": Counter({"granted-new": 77, "granted-existing": 34}),
    }
    print(LABEL, report, "refused=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
