"""Prove foreign store-visit transfers converge on a named policy stop."""

import gzip
import json
from pathlib import Path

from hengbot.cli import POLICY_FINAL_STOP_REASONS
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


TERMINAL = "town:blocked:owner-retired"


def _town_snapshot():
    fixture = Path(__file__).parent / "fixtures" / "incident-postlevel-repetition-turn-1006064.jsonl.gz"
    with gzip.open(fixture, "rt", encoding="utf-8-sig") as stream:
        return parse_snapshot(json.loads(next(stream)), {})


def measure():
    policy = HengbotPolicy()
    arbiter = policy._town_turn_arbiter
    bound = 2 * arbiter.registry["detectors"].budget + 1
    acquisitions = 0
    wanted = 7
    while acquisitions < bound:
        # The ordinary per-owner vectors change on every pass, reproducing the
        # case that evades owner recurrence accounting while the store pair
        # itself alternates without making useful progress.
        vector = ("alternating-target", wanted, acquisitions)
        reason = "shop:approach" if wanted == 7 else "equipment-transaction:approach"
        if not arbiter.may_select(reason, vector):
            key = policy.choose_key(_town_snapshot())
            return policy.last_reason, acquisitions, bound, key
        visit = arbiter.acquire_store_visit(
            store_type=wanted,
            owner="store-router",
            purpose="alternation-gate",
            opened_sequence=acquisitions,
            close_visit=policy._close_store_visit,
        )
        if visit is None:
            return None, acquisitions, bound, None
        acquisitions += 1
        arbiter.observe(
            in_town=True,
            reason=reason,
            progress_vector=vector,
            close_visit=policy._arbiter_close_store_visit,
        )
        wanted = 0 if wanted == 7 else 7
    return None, acquisitions, bound, None


if __name__ == "__main__":
    reason, acquisitions, bound, key = measure()
    print(f"reason={reason} key={key!r} acquisitions={acquisitions} bound={bound}")
    raise SystemExit(
        reason not in POLICY_FINAL_STOP_REASONS or acquisitions > bound
    )
