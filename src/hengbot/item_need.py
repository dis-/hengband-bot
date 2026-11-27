"""Is this piece needed?  The one answer (equipment review E6, 2026-11-22).

Equipment review 2026-11-22 (maintainability-review-equip-1122, finding 4): 「この品は要るか」
was defined seven-odd times -- the sale-value ranking (item_fate ``gear_tier``), the copy of the
search's choice (spare_gear ``released``), the downgrade of the kept pieces (item_fate
``_dominated``), the plain gear worse than the chosen loadout (policy ``_plain_gear_surplus``),
the search's dominance prune reused for disposal (policy ``_is_disposable_dominated_armour``),
the downgrade of the worn launcher (``_is_disposable_dominated_launcher``), the weapon worse
than the wielded high-grade one (``_find_weapon_sale``), the jewelry the race already gives
(item_fate ``_innate_covered``) and the cash sale's jewelry (home_cash_sale
``unneeded_jewelry``).  Each answered with its own exceptions; none asked whether the piece was
the only one that meets a depth requirement (owner Q3 of the review).

This module owns the part every one of them must share: why a piece is needed.

* :func:`carry_reason` -- the piece stays in the pack (no spare-gear deposit to Home): it is
  worn, the visit's target loadout wears it, it re-arms an empty weapon hand, Q25 carries it in
  for the druj, or it is the launcher that waits for its ammunition.
* :func:`keep_reason` -- the piece never leaves the character's ownership (no sale, no destroy,
  no Black Market fund): every carry reason but the re-arm, the equipment transaction owns it, it is the only
  owned source of a depth-table ability (owner Q3 「深さの条件を満たす唯一の品は全ての深さで
  優先して残し（売らない・闇市の資金にしない）」, ability_sources ``sole_depth_source``), a piece that
  closes or narrows the unmet depth row the character is held by (depth_gap_gear, 2026-11-28), a bounty,
  or a quest's tagged piece (Q34).  A kept piece may still wait at Home (Q3 「自宅・荷物に
  あれば持っている物として数え」).
* :func:`need` -- the whole verdict: ``CARRY`` / ``KEEP`` with the reason, else the owner's
  ranking (item_fate ``gear_tier``: ``KEEP`` top five, ``ROOM`` ranks 6-20, ``SPARE`` 21+, the
  named artifacts and the Black Market fund's exception) unless a named ground says the piece is
  spare first (:data:`GROUNDS`).

Every definition above now asks :func:`keep_reason` (or :func:`carry_reason`) before its own
ground, so a ground can only name a piece nothing needs.  ``scripts/equipment_writer_lint.py``
fails a read of ``ability_sources.sole_depth_source`` outside this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CARRY, KEEP, ROOM, SPARE = "carry", "keep", "room", "spare"
LEVELS = (CARRY, KEEP, ROOM, SPARE)

# The named spare grounds, in the order :func:`need` asks them (each read only once nothing
# keeps the piece): the old definitions of 「要らない」.
GROUND_DOMINATED = "dominated"                    # item_fate._dominated (Home stock)
GROUND_INNATE = "innate-covered"                  # item_fate._innate_covered (Home stock)
GROUND_ANTI_MAGIC = "anti-magic"                  # item_fate._anti_magic_unwearable (2026-11-27)
GROUND_PLAIN_GEAR = "plain-gear"                  # policy._plain_gear_surplus (junk class)
GROUND_DOMINATED_ARMOUR = "dominated-armour"      # policy._is_disposable_dominated_armour
GROUND_DOMINATED_LAUNCHER = "dominated-launcher"  # policy._is_disposable_dominated_launcher
GROUND_INFERIOR_WEAPON = "inferior-weapon"        # policy._find_weapon_sale's comparison
GROUNDS = (GROUND_DOMINATED, GROUND_INNATE, GROUND_ANTI_MAGIC, GROUND_PLAIN_GEAR, GROUND_DOMINATED_ARMOUR,
           GROUND_DOMINATED_LAUNCHER, GROUND_INFERIOR_WEAPON)


@dataclass(frozen=True)
class Need:
    """The verdict: ``level`` (``LEVELS``) and the reason or ground that decided it."""
    level: str
    reason: str

    @property
    def needed(self) -> bool:
        return self.level in (CARRY, KEEP)


# --- why a piece is needed ---------------------------------------------------------------------

def target_piece(policy: Any, item: Any) -> bool:
    """The visit's target loadout (the search's last preparation) wears ``item``."""
    from hengbot import equipment_target
    from hengbot.equipment_optimizer import equipment_identity

    best = getattr(getattr(equipment_target.loadout_target(policy), "result", None), "best", None)
    loadout = getattr(best, "loadout", None)
    if loadout is None or not getattr(item, "is_equipment", False):
        return False
    identity = equipment_identity(item)
    return any(equipment_identity(owned.item) == identity for _, owned in getattr(loadout, "slots", ()))


def rearm_weapon(snapshot: Any, item: Any) -> bool:
    """A good weapon while the hand holds no real weapon (a digger or nothing)."""
    good = item.is_melee_weapon and item.known and (
        item.is_ego or item.is_artifact or item.to_h > 0 or item.to_d > 0 or item.pval > 0)
    if not good:
        return False
    if snapshot is None:
        return True
    main_hand = next((worn for worn in snapshot.equipment if worn.slot == "main_hand"), None)
    return main_hand is None or main_hand.is_digging_tool


def _worn(snapshot: Any, item: Any) -> bool:
    if snapshot is None:
        return False
    if any(item is worn for worn in snapshot.equipment):
        return True
    # A worn slot is named (main_hand, ring_left, ...); a pack slot is a letter and a Home
    # stack is "home-surplus".
    slot = getattr(item, "slot", None)
    return (isinstance(slot, str) and len(slot) > 1 and slot != "home-surplus"
            and any(worn.slot == slot for worn in snapshot.equipment))


def _wanted_piece(policy: Any, snapshot: Any, item: Any) -> str | None:
    """The reasons a piece is wanted wherever it lies (worn, carried or at Home)."""
    from hengbot import launcher_upgrade, quest25_druj_gear

    if _worn(snapshot, item):
        return "worn"
    if target_piece(policy, item):
        return "target-loadout"
    if quest25_druj_gear.kept(policy, snapshot, item):
        return "quest25-druj"   # Q25 carries it in for the druj (phase7_druj)
    if snapshot is not None and launcher_upgrade.is_waiting(policy, snapshot, item):
        return "launcher-waiting"
    return None


def carry_reason(policy: Any, snapshot: Any, item: Any) -> str | None:
    """Why ``item`` stays carried (never shelved at Home as spare gear), or None.

    Every reason a piece is wanted (worn, the target loadout's, Q25's druj piece, the launcher
    that waits for its ammunition), and a good weapon while the hand holds no real weapon: it
    stays in the pack for the re-arm, but it is no reason to keep it from a sale (the re-arm
    returns the hand to the target loadout's weapon, equipment review E5)."""
    if rearm_weapon(snapshot, item):
        return "rearm-weapon"
    return _wanted_piece(policy, snapshot, item)


def keep_reason(policy: Any, snapshot: Any, item: Any) -> str | None:
    """Why ``item`` is never sold, destroyed or spent on a fund (it may wait at Home), or None.

    Asked by every disposal path, so it is kept once per decision, piece and place."""
    from hengbot.item_reservation import decision_memo

    key = (policy._item_signature(item), getattr(item, "slot", None))
    return decision_memo(policy, "item-need-keep", snapshot, key,
                         lambda: _keep_reason(policy, snapshot, item))


def _keep_reason(policy: Any, snapshot: Any, item: Any) -> str | None:
    from hengbot import ability_sources, depth_gap_gear
    from hengbot.equipment_optimizer import q34_item_tagged

    if getattr(item, "is_bounty", False):
        return "bounty"
    if not getattr(item, "is_equipment", False):
        return None
    if ability_sources.sole_depth_source(policy, snapshot, item):
        return "sole-depth-source"
    # A piece closing or narrowing the unmet depth row the character is held by (the speed
    # ceiling's row, a missing depth ability): supervisor 2026-11-28, n1-b life-419's sold
    # スピードの指輪 (+8) (depth_gap_gear).
    gap = depth_gap_gear.keep_reason(policy, snapshot, item)
    if gap is not None:
        return gap
    if q34_item_tagged(item):
        return "quest-tagged"
    if policy._equipment_transaction_owns_item(item):
        return "transaction"
    return _wanted_piece(policy, snapshot, item)


def needed(policy: Any, snapshot: Any, item: Any) -> bool:
    """``item`` is kept (:func:`keep_reason`): no ground may call it spare."""
    return keep_reason(policy, snapshot, item) is not None


# --- the whole verdict --------------------------------------------------------------------------

def _ground(policy: Any, snapshot: Any, item: Any) -> str | None:
    """The first named ground calling ``item`` spare (asked once nothing keeps it)."""
    from hengbot import item_fate

    if item_fate._dominated(policy, snapshot, item):
        return GROUND_DOMINATED
    if item_fate._innate_covered(snapshot, item):
        return GROUND_INNATE
    if item_fate._anti_magic_unwearable(snapshot, item):
        return GROUND_ANTI_MAGIC
    if policy._is_plain_gear(item) and policy._plain_gear_surplus(snapshot, item):
        return GROUND_PLAIN_GEAR
    if policy._is_disposable_dominated_armour(snapshot, item):
        return (GROUND_DOMINATED_LAUNCHER if item.tval == item_fate.TVAL_BOW
                else GROUND_DOMINATED_ARMOUR)
    if policy._inferior_weapon_spare(snapshot, item):
        return GROUND_INFERIOR_WEAPON
    return None


def need(policy: Any, snapshot: Any, item: Any) -> Need:
    """The one verdict for a piece of equipment (``Need``)."""
    from hengbot import item_fate

    reason = carry_reason(policy, snapshot, item)
    if reason == "rearm-weapon" and not (snapshot is None or any(
            item is carried for carried in snapshot.inventory)):
        reason = _wanted_piece(policy, snapshot, item)   # the re-arm takes a carried weapon
    if reason is not None:
        return Need(CARRY, reason)
    reason = keep_reason(policy, snapshot, item)
    if reason is not None:
        return Need(KEEP, reason)
    if item.known:
        ground = _ground(policy, snapshot, item)
        if ground is not None:
            return Need(SPARE, ground)
    tier = item_fate.gear_tier(policy, snapshot, item)
    return Need({item_fate.KEEP: KEEP, item_fate.ROOM: ROOM}.get(tier, SPARE), f"rank:{tier}")
