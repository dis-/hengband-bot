"""Measure one recorded S3.3 ownership replay with the town bar setting.

Run one case per process with PYTHONPATH=src;tests;scripts.
"""

from collections import Counter
import hashlib
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tests  # noqa: F401 -- recorded replay runtime-file isolation

from hengbot.policy import HengbotPolicy
from hengbot.ownership_metrics import ladder_numbers, s3_numbers
from measure_s3_prereq import CASES


FOCUS = {
    "tour": {2701, 3037, 3052},
    "town": {1177, 1916, 1922, 1941, 1947, 1957, 1958},
    "overweight": {3723},
}


def claim_goal_summary(rows, claim_id):
    goal = next((candidate.get("goal") for candidate in rows
                 if candidate.get("claim_id") == claim_id), None)
    if not isinstance(goal, dict):
        return None
    return {name: goal.get(name) for name in ("kind", "source", "cell")
            if goal.get(name) is not None}


def main(case, mode="on"):
    original_init = HengbotPolicy.__init__
    original_choose = HengbotPolicy.choose_key
    silent_details = []
    stale_visit_details = []

    def enforced_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._town_claim_bar_enforced = True

    if mode == "on":
        HengbotPolicy.__init__ = enforced_init
    def captured_choose(self, snapshot):
        key = original_choose(self, snapshot)
        visit = getattr(self, "_store_visit", None)
        for deferred in getattr(self, "_decision_errand_deferred", ()) or ():
            holder_id = deferred.get("holder_claim_id")
            if visit is not None and visit.claim_id == holder_id and (
                visit.phase.value == "closed"
                or (visit.operation_posted and visit.operation_released
                    and visit.operation_effect_observed)
            ):
                stale_visit_details.append({
                    "sequence": self._decision_sequence,
                    "holder": deferred.get("holder_family"),
                    "claim_id": holder_id,
                    "phase": visit.phase.value,
                    "operation_posted": visit.operation_posted,
                    "operation_released": visit.operation_released,
                    "effect_observed": visit.operation_effect_observed,
                })
        if (self.last_reason or "").startswith("ownership:holder-silent:"):
            visit = getattr(self, "_store_visit", None)
            session = getattr(self, "_equipment_transaction_session", None)
            silent_details.append({
                "sequence": getattr(self, "_decision_sequence", None),
                "reason": self.last_reason,
                "session": session is not None,
                "pending_action": getattr(session, "pending_action", None) is not None,
                "calibration_active": self._calibration_active(),
                "visit": visit is not None,
                "visit_operation_posted": getattr(visit, "operation_posted", None),
                "visit_operation_released": getattr(visit, "operation_released", None),
                "visit_effect_observed": getattr(visit, "operation_effect_observed", None),
            })
        return key
    HengbotPolicy.choose_key = captured_choose
    module_name, class_name = CASES[case]
    fixture = getattr(importlib.import_module(module_name), class_name)
    fixture.setUpClass()
    replay = fixture._replay()
    if case == "tour":
        rows = list(fixture.claim_rows)
        stream = [(row.get("key"), row.get("reason")) for row in rows]
    elif case == "withdraw":
        rows = list(replay["claim_rows"])
        stream = list(replay["decisions"])
    elif case == "recall":
        rows = [claim for pair in replay
                for claim in (pair["read_claim"], pair["cancel_claim"])]
        stream = [decision for pair in replay
                  for decision in (pair["read"], pair["cancel"])]
    elif case == "stuck":
        rows = [row["claim"] for row in replay[0].values()]
        stream = [(row.get("key"), row.get("reason"))
                  for row in replay[0].values()]
    else:
        rows = [row["claim"] for row in replay]
        stream = [(row.get("key"), row.get("reason")) for row in replay]
    digest = hashlib.sha256(json.dumps(
        stream, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    class_rows = []
    classes = Counter()
    for row in rows:
        violation = row.get("violation")
        if isinstance(violation, dict) and violation.get("scope") == "S3":
            classes[violation.get("kind", "unknown")] += 1
            class_rows.append({
                "sequence": row.get("decision_sequence"),
                "reason": row.get("reason"),
                "kind": violation.get("kind"),
                "from": violation.get("from"),
                "to": violation.get("to"),
            })
        for duplicate in row.get("purpose_duplicates") or ():
            if duplicate != violation:
                classes[duplicate.get("kind", "purpose-duplicate")] += 1
    ladder = ladder_numbers(rows)
    s3 = s3_numbers(rows)
    s3_gate = (ladder.get("violations", {}).get("S3", {}).get("count", 0)
               - s3.get("plan_handoff", 0))
    deferrals = Counter()
    holder_claims = Counter()
    holder_examples = {}
    claim_endings = {}
    silent = []
    stops = []
    focus = []
    violation_windows = []
    purpose_duplicate_rows = []
    suspended_violation_rows = []
    event_windows = []
    for index, row in enumerate(rows):
        sequence = row.get("decision_sequence")
        closed = row.get("closed_claim")
        if isinstance(closed, dict) and closed.get("claim_id") is not None:
            claim_endings[closed["claim_id"]] = {
                "sequence": sequence, "reason": closed.get("closed_reason"),
                "ending": closed.get("closed"),
            }
        decision_key = (
            replay[index].get("key") if case in {"town", "overweight"}
            else replay["decisions"][index][0] if case == "withdraw"
            else row.get("key")
        )
        for deferred in row.get("errand_deferred") or ():
            deferrals[(deferred.get("holder_family"),
                       deferred.get("deferred_family"))] += 1
            holder_claims[(deferred.get("holder_family"),
                           deferred.get("holder_claim_id"))] += 1
            holder_examples.setdefault(
                (deferred.get("holder_family"), deferred.get("holder_claim_id")),
                {"first_deferred_sequence": sequence,
                 "first_deferred_reason": row.get("reason"),
                 "holder_goal": claim_goal_summary(
                     rows, deferred.get("holder_claim_id"))},
            )
        reason = row.get("reason") or ""
        if "holder-silent" in reason:
            silent.append(sequence)
        if reason.startswith(("town:blocked:", "stuck:", "livelock:",
                              "ownership:holder-silent:")):
            stops.append((sequence, reason))
        if sequence in FOCUS.get(case, ()):
            if case == "tour":
                recorded = fixture.boundaries["recorded"][index]
            elif case in {"town", "overweight"}:
                recorded = [fixture.recorded[index][name]
                            for name in ("key", "reason")]
            else:
                recorded = None
            focus.append({"sequence": sequence,
                          "recorded": recorded,
                          "on": [decision_key, reason],
                          "violation": row.get("violation")})
        if isinstance(row.get("violation"), dict) and row["violation"].get("scope") == "S3":
            violation_windows.append({
                "sequence": sequence,
                "previous": rows[index - 1].get("reason") if index else None,
                "reason": reason, "key": decision_key,
                "owner": row.get("owner"), "goal": row.get("goal"),
                "next": rows[index + 1].get("reason") if index + 1 < len(rows) else None,
            })
        if row.get("purpose_duplicates"):
            purpose_duplicate_rows.append({
                "sequence": sequence, "reason": reason,
                "duplicates": row["purpose_duplicates"],
            })
        for suspended in row.get("suspended_closed") or ():
            if isinstance(suspended, dict) and suspended.get("violation"):
                suspended_violation_rows.append({
                    "sequence": sequence,
                    "reason": reason,
                    "closing": suspended,
                })
        if (reason.startswith(("town:blocked:", "ownership:holder-silent:"))
                or any(isinstance(item, dict) and item.get("violation")
                       for item in row.get("suspended_closed") or ())):
            event_windows.append([
                {"sequence": neighbor.get("decision_sequence"),
                 "reason": neighbor.get("reason"),
                 "owner": neighbor.get("owner"),
                 "goal": {name: neighbor["goal"].get(name)
                          for name in ("kind", "source", "cell")
                          if isinstance(neighbor.get("goal"), dict)
                          and neighbor["goal"].get(name) is not None},
                 "claim_id": neighbor.get("claim_id"),
                 "closed_claim": {
                     name: neighbor["closed_claim"].get(name)
                     for name in ("claim_id", "owner", "closed",
                                  "closed_reason", "state")
                 } if isinstance(neighbor.get("closed_claim"), dict) else None}
                for neighbor in rows[max(0, index - 2):index + 3]
            ])
    print(json.dumps({
        "case": case, "mode": mode, "rows": len(rows),
        "violations": class_rows,
        "classes": dict(classes),
        "s3_gate": s3_gate,
        "errand_deferred": sum(deferrals.values()),
        "deferral_families": [
            {"holder": holder, "deferred": deferred, "count": count}
            for (holder, deferred), count in deferrals.most_common()
        ],
        "holder_claims": [
            {"holder": holder, "claim_id": claim_id, "count": count,
             **holder_examples[(holder, claim_id)],
             "ending": claim_endings.get(claim_id)}
            for (holder, claim_id), count in holder_claims.most_common(12)
        ],
        "holder_silent": silent, "stops": stops,
        "holder_silent_details": silent_details,
        "stale_visit_details": stale_visit_details,
        "focus": focus, "violation_windows": violation_windows,
        "purpose_duplicate_rows": purpose_duplicate_rows,
        "suspended_violation_rows": suspended_violation_rows,
        "event_windows": event_windows[:2],
        "tail": [
            {"sequence": row.get("decision_sequence"),
             "reason": row.get("reason"),
             "owner": row.get("owner"),
             "key": replay[index]["key"] if case in {"town", "overweight"}
             else replay["decisions"][index][0] if case == "withdraw" else None}
            for index, row in enumerate(rows)
            if case == "withdraw" and (row.get("decision_sequence") or 0) >= 24
        ],
        "stream_sha256": digest,
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    if (len(sys.argv) not in {2, 3} or sys.argv[1] not in CASES
            or (len(sys.argv) == 3 and sys.argv[2] not in {"on", "off"})):
        raise SystemExit("Choose a replay and optional on/off: "
                         + ", ".join(CASES))
    main(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else "on")
