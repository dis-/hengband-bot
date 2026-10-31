"""Status treatment: Cure Critical Wounds (or Healing) for blindness, confusion, cuts.

Cure Critical Wounds is status treatment, never an HP-response potion
(_find_status_cure_potion keeps it ahead of Healing).  Blindness also hides
every monster and forbids reading, so the unseen-attacker branch cures it
before walking (death 1, #47, n1-a life-446: blinded beside a dragon, it
stepped into the adjacent monster five times and drank the cure at HP 15).
"""

from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_POTION_CURE_CRITICAL


def status_cure_key(policy, snapshot, *, blind_only: bool = False) -> str | None:
    """Quaff the status cure for the player's blindness (or any treated status)."""
    player = snapshot.player
    if not (player.blind or (not blind_only and (player.confused or player.cut))):
        return None
    potion = policy._find_status_cure_potion(snapshot)
    if potion is None:
        return None
    policy.last_reason = (
        "item:cure-critical"
        if potion.sval == SV_POTION_CURE_CRITICAL
        else "item:cure-status-healing"
    )
    return reserved_item_command(policy, snapshot, "quaff", potion)
