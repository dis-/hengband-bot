"""The temporary mining loadout's combat hands (D45).

Mining and the dig-to-stairs breakout swap the combat hands for diggers in
several posts.  ``_wield_digging_tool_key`` strips every combat hand first
('ta', 'tb') and only then wields the digger(s) on the emptied board, because
do_cmd_wield's prompt chain depends on which hands are occupied
(cmd-item/cmd-equipment.cpp:170-196).  Between those posts a combat hand is
empty.

Recorded n1-c life-065 (2026-10-31, zombie Magic-Eater Lv9, Yeek cave 1F):
'ta' at game turn 778659 (fundraise:wield-digging-tool), a breeding worm mass
came into view at 778665, and fundraise:eliminate-multiplier, the
Magic-Eater's ranged fire and melee took every later turn bare-handed for
more than 11,900 game turns.  The re-arm (``_restore_mining_combat_hand_key``)
only ever replaces a digger, and the executor refuses a combat-loadout
request on the board the mining-loadout post left unchanged
("goal-already-superseded"), so an empty hand was never re-armed.

This module owns both ends of that window, with one predicate (an awake
hostile in view, ``awake``) so they can never alternate:

- ``strip_allowed``: a combat hand is stripped only while no awake hostile is
  in view (a mining run already waits MINING_THREAT_FREE_LIMIT quiet
  decisions, counted by the same predicate).  Owner 2026-10-31: 「眠っている
  敵なら外してよい」 -- a hostile that is asleep does not keep the weapon on;
- ``rollback_key``: while an awake hostile is in view, an empty combat hand
  is re-armed with the weapon the swap displaced before any fight producer
  takes the turn -- at once when a sleeping one wakes or one comes into view
  awake.  Flight goes first (survival).  After a restart the remembered
  weapon is lost: the cached optimizer winner, else the first usable melee
  weapon carried (the established fallback of every re-arm), never a digger.

A digger in a hand keeps the approved mining-combat spec (ranged first,
re-arm after MINING_COMBAT_CONTACT_LIMIT contact decisions).

In town the emptied main hand is re-armed too (owner 2026-10-31 「町でも持た
せる」): ``empty_main_hand_weapon`` is the one choice both the town re-arm
(``_town_restore_weapon_key``) and the departure readiness
(``_combat_weapon_ready``) read, so readiness never waits on a weapon the
re-arm cannot wield.  The classes the game gives martial arts fight with the
main hand empty and are left as they are.
"""

from __future__ import annotations

from hengbot.equipment_mutation import EquipmentMutationResult
from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import TVAL_SHIELD


# Not one of the executor's opposing goals: undoing the swap's own strip is
# not a mining<->combat flip, so the supersession guard does not refuse it.
ROLLBACK_GOAL = "mining-loadout-rollback"
REARM_REASON = "melee:rearm-empty-hand"
STRIP_DEFERRED_REPORT = "mining-loadout:strip-deferred-hostile-in-view"
# player-status.cpp is_martial_arts_mode: Monk (8), Force-trainer (20) and
# Berserker (23) fight with martial arts while the main hand is empty
# (player-info/class-types.h).
MARTIAL_ARTS_CLASS_IDS = frozenset({8, 20, 23})


def awake(hostiles) -> list:
    """The hostiles that keep the combat hands on (every one not asleep)."""
    return [monster for monster in hostiles if not monster.asleep]


def worn_in_slot(snapshot, slot: str):
    return next((item for item in snapshot.equipment if item.slot == slot), None)


def cached_optimal_loadout(policy):
    """The cached optimizer winner's loadout, or None."""
    preparation = policy._equipment_optimization_preparation
    best = getattr(getattr(preparation, "result", None), "best", None)
    loadout = getattr(best, "loadout", None)
    return loadout if loadout is not None and hasattr(loadout, "item_at") else None


def remember_combat_hands(policy, main_hand, sub_hand) -> None:
    """Record the combat hands the digger swap displaces, once per swap.

    The cached optimizer winner is authoritative for both hands, its empty
    off hand included.  An absent main-hand choice is not: the observed
    weapon is kept so a cold or incomplete cache never makes the restore
    weaponless.  Without a winner the observed hands are recorded, and an
    off hand seen empty is authoritative too (#47, n1-c lives 077 and 086:
    an unrecorded empty off hand was re-armed with any carried melee
    weapon, a dual wield the Magic-Eater's skill cannot hit with,
    player-status.cpp calc_double_weapon_penalty).  A digger in the off
    hand (a restart mid-swap) leaves it unknown.
    """
    loadout = cached_optimal_loadout(policy)
    optimal_main = loadout.item_at("main_hand") if loadout is not None else None
    if optimal_main is not None:
        policy._normal_weapon_name = optimal_main.item.name
        policy._normal_weapon_identity = equipment_identity(optimal_main.item)
        policy._normal_weapon_is_optimal = True
    elif main_hand is not None and not main_hand.is_digging_tool:
        policy._normal_weapon_name = main_hand.name
        policy._normal_weapon_identity = equipment_identity(main_hand)
        policy._normal_weapon_is_optimal = False
    if loadout is not None:
        sub = loadout.item_at("sub_hand")
        _remember_sub_hand(policy, sub.item if sub is not None else None, True)
    elif sub_hand is None:
        _remember_sub_hand(policy, None, True)
    elif not sub_hand.is_digging_tool:
        _remember_sub_hand(policy, sub_hand, False)
    else:
        _remember_sub_hand(policy, None, False)
    policy._mining_combat_loadout_remembered = True


def _remember_sub_hand(policy, item, authoritative: bool) -> None:
    policy._normal_sub_hand_name = item.name if item is not None else None
    policy._normal_sub_hand_identity = (
        equipment_identity(item) if item is not None else None)
    policy._normal_sub_hand_is_optimal = authoritative


def remembered_hands(policy) -> tuple:
    """(slot, name, identity, authoritative) of each displaced combat hand.

    ``authoritative`` (the ``_normal_*_is_optimal`` attributes) marks the
    optimizer winner, or an off hand remember_combat_hands saw empty: an
    authoritative empty off hand is restored empty.
    """
    return (
        ("main_hand", policy._normal_weapon_name,
         policy._normal_weapon_identity, policy._normal_weapon_is_optimal),
        ("sub_hand", policy._normal_sub_hand_name,
         policy._normal_sub_hand_identity, policy._normal_sub_hand_is_optimal),
    )


def restorable_item(policy, snapshot, slot: str, name, identity):
    """The carried item that goes back into ``slot`` (never a digger).

    The remembered identity, else the remembered name, else any usable melee
    weapon for the main hand and a shield for the off hand: a second weapon
    goes on only as the displaced item or the optimizer's choice, never
    unevaluated (#47: the Magic-Eater's unskilled dual wield missed).
    """
    def matches(item) -> bool:
        if identity is not None:
            return equipment_identity(item) == identity
        if name is not None:
            return item.name == name
        if slot == "main_hand":
            return item.is_melee_weapon
        return item.tval == TVAL_SHIELD

    return policy._first_item(
        snapshot,
        lambda item: item.is_equipment
        and not item.is_digging_tool
        and not policy._equip_blocked_by_identification(item)
        and not item.is_broken
        and not policy._blocks_teleport(item)
        and matches(item),
    )


def strip_allowed(policy, snapshot) -> bool:
    """A combat hand may be emptied for the digger only with no awake hostile in view."""
    return not awake(policy._physical_hostiles(snapshot))


def deferred_strip() -> EquipmentMutationResult:
    return EquipmentMutationResult(None, STRIP_DEFERRED_REPORT)


def main_hand_weapon(policy, snapshot):
    """The carried weapon an empty main hand takes, or None.

    The displaced weapon, else (a restart lost it) the cached optimizer
    winner, else any usable melee weapon carried (owner 2026-10-31:
    「最適化の結果→最初の近接武器」 「これでよい」).
    """
    loadout = cached_optimal_loadout(policy)
    optimal = loadout.item_at("main_hand") if loadout is not None else None
    choices = tuple(
        choice for choice in (
            (policy._normal_weapon_name, policy._normal_weapon_identity),
            (None, equipment_identity(optimal.item) if optimal is not None else None),
        ) if choice != (None, None)
    ) + ((None, None),)
    for name, identity in choices:
        item = restorable_item(policy, snapshot, "main_hand", name, identity)
        if item is not None:
            return item
    return None


def empty_main_hand_weapon(policy, snapshot):
    """The carried weapon an empty main hand takes, or None (no digger held).

    Owner 2026-10-31 「町でも持たせる」; a martial-arts class keeps its hand
    empty (MARTIAL_ARTS_CLASS_IDS).
    """
    if (snapshot.player.class_id in MARTIAL_ARTS_CLASS_IDS
            or worn_in_slot(snapshot, "main_hand") is not None
            or any(item.is_digging_tool for item in snapshot.equipment)):
        return None
    return main_hand_weapon(policy, snapshot)


def _rearm_target(policy, snapshot):
    """(slot, item) the rollback wields next, main hand first, or None."""
    main = worn_in_slot(snapshot, "main_hand")
    for slot, name, identity, _optimal in remembered_hands(policy):
        if worn_in_slot(snapshot, slot) is not None:
            continue
        if slot == "main_hand":
            item = main_hand_weapon(policy, snapshot)
        elif main is None or main.is_digging_tool or (name is None and identity is None):
            # An empty off hand is an ordinary loadout unless the swap
            # displaced an item from it; it never goes beside a digger.
            continue
        else:
            item = restorable_item(policy, snapshot, slot, name, identity)
        if item is not None:
            return slot, item
    return None


def rollback_key(policy, snapshot) -> str | None:
    """Re-arm a combat hand the digger swap left empty before a fight."""
    if snapshot.in_town or getattr(snapshot, "store", None) is not None:
        return None
    hostiles = policy._physical_hostiles(snapshot)
    if not awake(hostiles) or not any(item.is_digging_tool for item in snapshot.inventory):
        return None
    target = _rearm_target(policy, snapshot)
    if target is None:
        return None
    if policy._should_flee(snapshot, hostiles, policy._physical_adjacent_hostiles(snapshot)):
        return None
    slot, item = target
    key = policy._equipment_wield(snapshot, ROLLBACK_GOAL, item, slot)
    if key is not None:
        policy.last_reason = REARM_REASON
    return key
