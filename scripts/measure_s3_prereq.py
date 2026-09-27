"""Measure S3 recording on one isolated fixture replay per invocation."""

from collections import Counter
import hashlib
import importlib
import json
import sys

from hengbot.ownership_metrics import ladder_numbers, s3_numbers


CASES = {
    "tour": ("test_unaffordable_claim_tour_recorded", "UnaffordableClaimTourRecordedTest"),
    "town": ("test_town_approach_retired_recorded", "TownApproachRetiredRecordedTest"),
    "overweight": ("test_overweight_home_unreachable_recorded", "OverweightHomeUnreachableRecordedTest"),
    "withdraw": ("test_home_withdraw_failed_stock_present_recorded", "HomeWithdrawFailedStockPresentRecordedTest"),
    "recall": ("test_recall_read_cancel_pingpong_recorded", "RecallReadCancelPingPongRecordedTest"),
    "stuck": ("test_stuck_prompt_staged_tail_recorded", "StuckPromptStagedTailRecordedTest"),
}


def rows_for(case, fixture):
    replay = fixture._replay()
    if case == "tour":
        return list(fixture.claim_rows)
    if case == "withdraw":
        return list(replay["claim_rows"])
    if case == "recall":
        return [claim for pair in replay
                for claim in (pair["read_claim"], pair["cancel_claim"])]
    if case == "stuck":
        return [row["claim"] for row in replay[0].values()]
    return [row["claim"] for row in replay]


def measure(case):
    module_name, class_name = CASES[case]
    fixture = getattr(importlib.import_module(module_name), class_name)
    fixture.setUpClass()
    rows = [dict(row, kind="claim", session=case) for row in rows_for(case, fixture)]
    replay = fixture._replay()
    if case == "tour":
        stream = [(row.get("key"), row.get("reason")) for row in fixture.claim_rows]
    elif case == "withdraw":
        stream = list(replay["decisions"])
    elif case == "recall":
        stream = [decision for pair in replay
                  for decision in (pair["read"], pair["cancel"])]
    elif case == "stuck":
        stream = [(row.get("key"), row.get("reason"))
                  for row in replay[0].values()]
    else:
        stream = [(row.get("key"), row.get("reason")) for row in replay]
    stream_sha256 = hashlib.sha256(json.dumps(
        stream, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    violations = Counter()
    class_rows = []
    for row in rows:
        violation = row.get("violation")
        if isinstance(violation, dict) and violation.get("scope") == "S3":
            violations[violation.get("kind", "unknown")] += 1
            class_rows.append({
                "sequence": row.get("decision_sequence"),
                "reason": row.get("reason"),
                "kind": violation.get("kind"),
                "from": violation.get("from"), "to": violation.get("to"),
            })
        for duplicate in row.get("purpose_duplicates") or ():
            if duplicate != violation:
                violations[duplicate.get("kind", "purpose-duplicate")] += 1
    pairs = {}
    visits = Counter()
    for row in rows:
        if row.get("requester_missing"):
            category = "requester-missing"
        elif row.get("visit_owner_mismatch"):
            category = "genuine"
        elif row.get("visit_owner_structure") == "router-plan-stop":
            category = "router-plan-stop"
        else:
            continue
        visits[category] += 1
        pair = (row.get("visit_requester"), row.get("visit_operator"))
        pairs.setdefault((category, pair), row.get("decision_sequence"))
    ladder = ladder_numbers(rows)
    s3 = s3_numbers(rows)
    return {
        "case": case, "rows": len(rows), "stream_sha256": stream_sha256,
        "classes": dict(violations), "class_rows": class_rows,
        "gate_s3": (ladder.get("violations", {}).get("S3", {}).get("count", 0)
                    - s3.get("plan_handoff", 0)),
        "plan_handoff": s3.get("plan_handoff", 0),
        "visits": dict(visits),
        "visit_pairs": [
            {"class": category, "requester": pair[0], "operator": pair[1],
             "representative_sequence": sequence}
            for (category, pair), sequence in pairs.items()
        ],
        "focus_rows": [
            {name: row.get(name) for name in (
                "decision_sequence", "reason", "owner", "goal", "violation",
                "closed_claim", "visit_owner_structure", "visit_requester",
                "visit_operator", "leave_confirmation_pending",
            )}
            for row in rows if case == "town"
            and 1956 <= (row.get("decision_sequence") or 0) <= 1959
        ],
    }


if __name__ == "__main__":
    print(json.dumps(measure(sys.argv[1]), sort_keys=True, default=str))
