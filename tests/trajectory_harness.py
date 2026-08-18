"""Multi-decision policy trajectories and incident-checkpoint conversion."""

from __future__ import annotations

import base64
import json
import pickle
import gzip
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrajectoryResult:
    transcript: tuple[tuple[str, str], ...]
    milestones: tuple[tuple[str, int], ...]
    longest_owner_stall: int


def _open_jsonl(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8-sig")
    return path.open(encoding="utf-8-sig")


def drive_trajectory(policy, world, *, decisions, milestones, owner_bound=20,
                     pair_bound=20):
    """Drive public decisions, enforcing ordered milestones and liveness."""
    transcript = []
    reached = []
    next_milestone = 0
    fingerprint = world.progress_fingerprint()
    owner = None
    owner_stall = longest = 0
    pair_run = 0
    previous_pair = None
    for decision in range(1, decisions + 1):
        world.deliver_events(policy)
        key = policy.choose_key(world.snapshot(decision))
        reason = policy.last_reason
        pair = (reason, key)
        transcript.append(pair)
        pair_run = pair_run + 1 if pair == previous_pair else 1
        previous_pair = pair
        if pair_run > pair_bound:
            raise AssertionError(f"identical decision pair repeated {pair_run} times: {pair!r}")
        confirm = getattr(policy, "confirm_key_posted", None)
        if confirm is not None:
            confirm(key)
        world.apply(key)
        current = world.progress_fingerprint()
        current_owner = reason.split(":", 1)[0]
        if current != fingerprint:
            fingerprint = current
            owner_stall = 0
        elif current_owner == owner:
            owner_stall += 1
        else:
            owner_stall = 1
        owner = current_owner
        longest = max(longest, owner_stall)
        if owner_stall > owner_bound:
            raise AssertionError(
                f"owner {owner!r} made no progress for {owner_stall} decisions"
            )
        while next_milestone < len(milestones):
            name, bound, predicate = milestones[next_milestone]
            if predicate(policy, world, reason, key):
                if decision > bound:
                    raise AssertionError(f"milestone {name!r} reached at {decision}, bound {bound}")
                reached.append((name, decision))
                next_milestone += 1
            else:
                break
        if next_milestone == len(milestones):
            return TrajectoryResult(tuple(transcript), tuple(reached), longest)
    missing = [name for name, _bound, _predicate in milestones[next_milestone:]]
    raise AssertionError(
        f"trajectory exhausted after {decisions}; first unsatisfied milestone "
        f"{missing[0]!r}; missing {missing}; tail={transcript[-8:]}"
    )


def checkpoint_rows(path: Path):
    """Yield replayable pre-decision checkpoints from a capture or JSONL."""
    if not path.exists():
        raise FileNotFoundError(f"required frozen incident fixture is absent: {path}")
    files = sorted(path.rglob("*.jsonl")) if path.is_dir() else [path]
    for source in files:
        with _open_jsonl(source) as rows:
            for number, line in enumerate(rows, 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"{source}:{number}: invalid JSON") from error
                policy_blob = row.get("predecision_policy_checkpoint_pickle_b64")
                snapshot_blob = (
                    row.get("snapshot_pickle_b64")
                    or row.get("decision_snapshot_pickle_b64")
                )
                if policy_blob and snapshot_blob:
                    yield source, number, policy_blob, snapshot_blob


def checkpoint_row(path: Path, decision_index: int):
    """Return one named pre-decision checkpoint without loading a huge capture."""
    if not path.exists():
        raise FileNotFoundError(f"required frozen incident fixture is absent: {path}")
    with _open_jsonl(path) as rows:
        for number, line in enumerate(rows, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{number}: invalid JSON") from error
            if row.get("decision_index") == decision_index:
                policy_blob = row.get("predecision_policy_checkpoint_pickle_b64")
                snapshot_blob = row.get("decision_snapshot_pickle_b64")
                if not policy_blob or not snapshot_blob:
                    raise ValueError(
                        f"{path}:{number}: decision {decision_index} has no pre-decision checkpoint"
                    )
                return row, policy_blob, snapshot_blob
    raise AssertionError(f"decision {decision_index} is absent from required fixture {path}")


def decision_window(path: Path, *, start: str, end: str, reason: str):
    """Load the measured rows in a bounded decision-log time window."""
    if not path.exists():
        raise FileNotFoundError(f"required frozen incident fixture is absent: {path}")
    matched = []
    with path.open(encoding="utf-8-sig") as rows:
        for number, line in enumerate(rows, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{number}: invalid JSON") from error
            timestamp = row.get("time", "")
            if start <= timestamp <= end and row.get("reason") == reason:
                matched.append(row)
    if not matched:
        raise AssertionError(
            f"no {reason!r} decisions in {start}..{end} at {path}"
        )
    return matched


def restore_incident_checkpoint(policy_type, policy_blob, snapshot_blob):
    """Restore the exact policy and Snapshot recorded before a decision."""
    from hengbot.latch_onset_capture import restore_checkpoint
    policy = restore_checkpoint(policy_type, policy_blob)
    snapshot = pickle.loads(base64.b64decode(snapshot_blob))
    return policy, snapshot


def replay_incident(policy_type, path: Path, *, forbidden_pair, limit=40):
    """Convert a capture into a bounded regression against the recorded defect."""
    rows = list(checkpoint_rows(path))
    if not rows:
        raise AssertionError(f"no replayable pre-decision checkpoint in required fixture {path}")
    policy, snapshot = restore_incident_checkpoint(policy_type, rows[-1][2], rows[-1][3])
    seen = Counter()
    for _ in range(limit):
        key = policy.choose_key(snapshot)
        pair = (policy.last_reason, key)
        seen[pair] += 1
        if seen[forbidden_pair] > 3:
            raise AssertionError(f"captured defect recurred: {forbidden_pair!r}")
        # An evidence-only converter cannot invent game effects.  A changed
        # decision or an explicit terminal is sufficient; unchanged input is
        # intentionally bounded and will expose absorbing repeats.
        if pair != forbidden_pair:
            return pair
    raise AssertionError(f"checkpoint did not escape within {limit} decisions")


def replay_checkpoint_decision(policy_type, path: Path, decision_index: int,
                               *, forbidden_pair):
    """Replay the exact first decision from a selected capture checkpoint."""
    row, policy_blob, snapshot_blob = checkpoint_row(path, decision_index)
    policy, snapshot = restore_incident_checkpoint(policy_type, policy_blob, snapshot_blob)
    key = policy.choose_key(snapshot)
    pair = (policy.last_reason, key)
    if pair == forbidden_pair:
        raise AssertionError(
            f"captured defect recurred at decision {decision_index}: {pair!r}"
        )
    return row, pair


def replay_checkpoint_trajectory(policy_type, path: Path, decision_indices,
                                 *, forbidden_reasons, required_reason_prefix):
    """Replay frozen points from one no-progress trajectory.

    Each checkpoint is an independently captured pre-decision state.  This is
    deliberately stricter than inventing store or movement effects between
    them: every recorded owner in the incident must leave the forbidden cycle,
    and at least one replacement decision must visibly pursue the required
    higher-priority owner.
    """
    transcript = []
    for decision_index in decision_indices:
        _row, policy_blob, snapshot_blob = checkpoint_row(path, decision_index)
        policy, snapshot = restore_incident_checkpoint(
            policy_type, policy_blob, snapshot_blob
        )
        key = policy.choose_key(snapshot)
        pair = (policy.last_reason, key)
        transcript.append(pair)
        if policy.last_reason in forbidden_reasons:
            raise AssertionError(
                f"captured owner cycle recurred at {decision_index}: {pair!r}"
            )
    if not any(
        reason.startswith(required_reason_prefix) for reason, _key in transcript
    ):
        raise AssertionError(
            f"trajectory never pursued {required_reason_prefix!r}: {transcript!r}"
        )
    return tuple(transcript)
