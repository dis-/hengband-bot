"""Stop an S3.3 recorded replay at its first ON/OFF decision difference.

Run one fixture per process with PYTHONPATH=src;tests;scripts.  Each mode uses
the fixture's own declared walls.  The OFF stream is checked against the R4
hash before the ON replay starts.
"""

import hashlib
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tests  # noqa: F401 -- keep runtime files isolated as in fixture tests

from hengbot.policy import HengbotPolicy
from measure_s3_prereq import CASES
from test_ownership_s3_3_first_divergence import EXPECTED_FIRST, trajectory_defect


OFF_SHA = {
    "tour": "d30b053bc9744336253c0b2235f7887dd3b4604bc09a86b715262c8377de5464",
    "town": "7fe5100909a3346355e5c0a9c4e66d649bae412987a46276040c077277f550b1",
    "overweight": "8e76a2056d587730d825bc367b0fc3812da13610809f96193b03445ef542758b",
    "withdraw": "a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9",
    "recall": "b21c0b3b423c886674960f5f3640424b8a51fc3d1f8215e31b3f61a5299bcef4",
    "stuck": "c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5",
}

# Frozen before the cross-area policy switch was implemented.  These six S3.3
# fixtures contain no accepted fundraising run, so its first difference is
# expected to be absent.  The 09-29 stair pair is pinned separately from its
# recorded pre-decision facts; it is not an action-consistent replay of this
# six-fixture stream.
CROSSAREA_EXPECTED_FIRST = {case: None for case in OFF_SHA}
MODES = {"off", "s33", "crossarea"}


def _identity(value):
    if value is None:
        return None
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, (tuple, list, str, int, bool, float)):
        return value
    return repr(value)


def _state(policy):
    register = getattr(policy, "_claim_register", None)
    parent = getattr(register, "current", None)
    session = getattr(policy, "_equipment_transaction_session", None)
    visit = getattr(policy, "_store_visit", None)
    return {
        "parent": None if parent is None else {
            "claim_id": parent.claim_id, "family": parent.owner.value,
            "state": parent.state.value, "goal": parent.goal.as_dict(),
        },
        "session": None if session is None else {
            "identity": _identity(getattr(session, "claim_operation_identity", None)),
            "opened_sequence": getattr(session, "opened_sequence", None),
            "pending_action": _identity(getattr(session, "pending_action", None)),
            "complete": getattr(session, "complete", None),
        },
        "operation": None if visit is None else {
            "claim_id": visit.claim_id, "phase": visit.phase.value,
            "purpose": visit.purpose, "store_type": visit.store_type,
            "posted": visit.operation_posted,
            "identity": _identity(visit.claim_operation_identity),
            "producer": visit.operation_producer_family,
            "released": visit.operation_released,
        },
        "delegates": [getattr(record, "as_dict", lambda: record)()
                      for record in getattr(policy, "_execution_delegations", ())],
    }


def _stream(case, fixture, replay):
    if case == "tour":
        return [(row.get("key"), row.get("reason")) for row in fixture.claim_rows]
    if case == "withdraw":
        return list(replay["decisions"])
    if case == "recall":
        return [decision for pair in replay
                for decision in (pair["read"], pair["cancel"])]
    if case == "stuck":
        return [(row.get("key"), row.get("reason"))
                for row in replay[0].values()]
    return [(row.get("key"), row.get("reason")) for row in replay]


class FirstDifference(Exception):
    def __init__(self, row):
        self.row = row


def measure(case, mode="s33"):
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose {sorted(MODES)}")
    module = importlib.import_module(CASES[case][0])
    fixture = getattr(module, CASES[case][1])
    fixture.setUpClass()
    original_init = HengbotPolicy.__init__
    original_choose = HengbotPolicy.choose_key
    off_calls = []
    on_calls = []

    def observe_off(policy, snapshot):
        before = _state(policy)
        key = original_choose(policy, snapshot)
        off_calls.append((key, policy.last_reason, policy._decision_sequence, before))
        return key

    HengbotPolicy.choose_key = observe_off
    try:
        off_replay = fixture._replay()
    finally:
        HengbotPolicy.choose_key = original_choose
    stream = _stream(case, fixture, off_replay)
    digest = hashlib.sha256(json.dumps(
        stream, ensure_ascii=True, separators=(",", ":")
    ).encode()).hexdigest()
    if digest != OFF_SHA[case]:
        raise AssertionError(f"{case}: OFF hash {digest} != {OFF_SHA[case]}")

    # Clear only replay output; setUpClass's immutable fixture inputs and walls
    # are used again for the second independent policy instance.
    fixture.replay = None

    if mode == "off":
        return {"case": case, "mode": mode,
                "fixture_sha256": module.FIXTURE_SHA256,
                "off_sha256": digest, "off_rows": len(stream),
                "first_divergence": None}

    def enforced_init(policy, *args, **kwargs):
        original_init(policy, *args, **kwargs)
        if mode == "s33":
            policy._town_claim_bar_enforced = True
        else:
            policy._crossarea_fundraising_enforced = True

    def observe_on(policy, snapshot):
        before = _state(policy)
        key = original_choose(policy, snapshot)
        index = len(on_calls)
        observed = (key, policy.last_reason, policy._decision_sequence, before)
        on_calls.append(observed)
        if index >= len(off_calls) or observed[:2] != off_calls[index][:2]:
            raise FirstDifference((index, off_calls[index] if index < len(off_calls)
                                   else None, observed))
        return key

    HengbotPolicy.__init__ = enforced_init
    HengbotPolicy.choose_key = observe_on
    difference = None
    try:
        fixture._replay()
    except FirstDifference as error:
        difference = error.row
    finally:
        HengbotPolicy.__init__ = original_init
        HengbotPolicy.choose_key = original_choose
    result = {"case": case, "mode": mode,
              "fixture_sha256": module.FIXTURE_SHA256,
              "off_sha256": digest, "off_rows": len(stream)}
    expected = (EXPECTED_FIRST if mode == "s33"
                else CROSSAREA_EXPECTED_FIRST)
    if difference is None:
        result["first_divergence"] = None
        result["expected_first"] = expected[case]
        result["trajectory_defect"] = (trajectory_defect(case, None)
                                       if mode == "s33" else None)
        return result
    index, off, on = difference
    historical = None
    if case == "tour":
        historical = fixture.boundaries["recorded"][index]
        historical = {"key": historical[0], "reason": historical[1],
                      # This fixture stores key/reason only.  The OFF replay
                      # follows its decision counter under the same walls.
                      "decision_sequence": off[2] if off else None}
    elif hasattr(fixture, "recorded"):
        historical = fixture.recorded[index]
    result["first_divergence"] = {
        "list_index": index,
        "historical_sequence": historical.get("decision_sequence")
            if isinstance(historical, dict) else None,
        "historical": {name: historical.get(name) for name in ("key", "reason")}
            if isinstance(historical, dict) else historical,
        "historical_sequence_source": (
            "off-replay-counter" if case == "tour" else "fixture"
        ),
        "off_sequence": off[2] if off else None,
        "new_sequence": on[2],
        "off": list(off[:2]) if off else None,
        "on": list(on[:2]),
        "pre_decision_off": off[3] if off else None,
        "pre_decision_on": on[3],
    }
    result["expected_first"] = expected[case]
    result["trajectory_defect"] = (
        trajectory_defect(case, result["first_divergence"])
        if mode == "s33" else "unexpected-divergence"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(measure(sys.argv[1], sys.argv[2] if len(sys.argv) > 2
                             else "s33"), sort_keys=True, default=str))
