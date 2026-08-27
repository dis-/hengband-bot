"""Prove foreign store-visit transfers converge on a named policy stop."""

from hengbot.cli import POLICY_FINAL_STOP_REASONS
from hengbot.policy import HengbotPolicy


TERMINAL = "town:blocked:owner-retired"


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
            terminal = TERMINAL if getattr(
                arbiter, "_transfer_exhausted", False
            ) else None
            return terminal, acquisitions, bound
        visit = arbiter.acquire_store_visit(
            store_type=wanted,
            owner="store-router",
            purpose="alternation-gate",
            opened_sequence=acquisitions,
            close_visit=policy._close_store_visit,
        )
        if visit is None:
            return None, acquisitions, bound
        acquisitions += 1
        arbiter.observe(
            in_town=True,
            reason=reason,
            progress_vector=vector,
            close_visit=policy._arbiter_close_store_visit,
        )
        wanted = 0 if wanted == 7 else 7
    return None, acquisitions, bound


if __name__ == "__main__":
    reason, acquisitions, bound = measure()
    print(f"reason={reason} acquisitions={acquisitions} bound={bound}")
    raise SystemExit(
        reason not in POLICY_FINAL_STOP_REASONS or acquisitions > bound
    )
