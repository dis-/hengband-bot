"""Multi-decision policy trajectories and incident-checkpoint conversion."""

from __future__ import annotations

import base64
import json
import pickle
import unittest
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrajectoryResult:
    transcript: tuple[tuple[str, str], ...]
    milestones: tuple[tuple[str, int], ...]
    longest_owner_stall: int


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
    raise AssertionError(f"trajectory exhausted after {decisions}; missing {missing}; tail={transcript[-8:]}")


def checkpoint_rows(path: Path):
    """Yield replayable pre-decision checkpoints from a capture or JSONL."""
    if not path.exists():
        return
    files = sorted(path.rglob("*.jsonl")) if path.is_dir() else [path]
    for source in files:
        with source.open(encoding="utf-8-sig") as rows:
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
        raise unittest.SkipTest(f"no replayable pre-decision checkpoint in {path}")
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
