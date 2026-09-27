"""Replay-only compatibility for pre-loot-fix dungeon paths.

Town incident fixtures contain later boards from the original dungeon route.
Only town-subject replays use this patch. Loot regression replays must run the
production observer so their first changed key remains visible.
"""

from contextlib import contextmanager
from unittest.mock import patch

from hengbot.policy import CLAIM_LOOT_OWNERS, HengbotPolicy


@contextmanager
def pre_fix_loot_observation():
    """Restore the old fallback charge while retaining current non-loot work."""
    current = HengbotPolicy._observe_navigation_commitments

    def observe(policy, snapshot):
        committed = policy._loot_target
        if committed is None:
            committed = min(
                policy._known_loot - policy._deferred_loot,
                key=lambda pos: (pos.y, pos.x), default=None,
            )
        if committed is not None:
            policy._nav_ledger.observe(
                "loot", committed,
                snapshot.player.position.distance_to(committed),
            )
            if policy._nav_ledger.is_expired("loot", committed):
                policy._deferred_loot.add(committed)
                policy._nav_ledger_deferred_loot.add(committed)
                policy._loot_defer_blocker = "navigation-ledger:loot"
                if policy._loot_target == committed:
                    policy._release_claim_goal(
                        "loot-navigation-expired", committed,
                        owners=CLAIM_LOOT_OWNERS,
                    )
                    policy._loot_target = None
        # Delegate exploration and guard observation. Hide the loot target to
        # avoid a second charge by the repaired production implementation.
        target = policy._loot_target
        policy._loot_target = None
        try:
            current(policy, snapshot)
        finally:
            policy._loot_target = target

    with patch.object(HengbotPolicy, "_observe_navigation_commitments", observe):
        yield
