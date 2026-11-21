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
  awake.  Flight goes first (survival) only beside an awake hostile or
  below FLEE_HP_RATIO (``_flight_first``): elsewhere the empty hand is the
  flight's own cause (n1-a life-518, 2026-11-12: a Lv1 worm mass three
  cells away read T1 against the bare hand and the re-arm yielded to the
  flee rung for the rest of the run).  With nothing awake in view the hand
  is re-armed too once no swap owner will wield the digger
  (``swap_abandoned``: a latched return, no mining run, no dig route of
  the breakout's family on this floor).  After a restart the remembered
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

from hengbot import equipment_target
from hengbot.equipment_mutation import EquipmentMutationResult
from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import TVAL_SHIELD
from hengbot.policy_constants import FLEE_HP_RATIO


# Not one of the executor's opposing goals: undoing the swap's own strip is
# not a mining<->combat flip, so the supersession guard does not refuse it.
# The contact re-arm of a digger in hand (``_restore_mining_combat_hand_key``
# after MINING_COMBAT_CONTACT_LIMIT contact decisions) undoes the swap too: as
# combat-loadout it was refused while the fight changed neither gold, experience
# nor items (equipment_mutation.progress_core).  n1-a life-525 (2026-11-15 16:54,
# Lv37 Warrior, Yeek cave 1F) fought a 巨大ハツカネズミ swarm with the two diggers
# for 90 decisions (467 of 513 blows missed: the two-weapon penalty,
# player-status.cpp calc_double_weapon_penalty) until the loop detector stopped it.
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
    preparation = equipment_target.loadout_target(policy)
    best = getattr(getattr(preparation, "result", None), "best", None)
    loadout = getattr(best, "loadout", None)
    return loadout if loadout is not None and hasattr(loadout, "item_at") else None


HANDS = ("main_hand", "sub_hand")
# The causes the town's two hand owners name when the lending holds them (policy_equipment).
LENT_CAUSE = "hands-lent-to-mining"
SESSION_CAUSE = "hands-owned-by-transaction"
# A mining set open: the next departure is the mining walk-in.
LENDING_MODES = frozenset({"prepare", "mine"})
# A mining run came back to this town visit with a digger in a hand (state_registry row).
RETURN_STATE = "_mining_hands_returned"


def _digger_in_hand(snapshot) -> bool:
    return any(item.is_digging_tool and item.slot in HANDS
               for item in getattr(snapshot, "equipment", ()))


def note_run_return(policy, snapshot) -> None:
    """A mining run came back to town (policy_observation ``returned_from_fundraising``) with a
    digger in a hand: the hands stay lent through this town visit (``hands_lent``)."""
    if _digger_in_hand(snapshot):
        setattr(policy, RETURN_STATE, True)


def end_lending(policy) -> None:
    """The lending of a run's return ends: the town left (policy_observation), or an ordinary
    (not mining) departure asked for the weapon (``departure_asks_weapon``)."""
    setattr(policy, RETURN_STATE, False)


def hands_lent(policy, snapshot) -> bool:
    """In town, the combat hands are lent to the mining fundraise: one owner for them.

    Owner 2026-11-22 Q6 (verbatim choice): after a temporary swap (mining, a quest, Zul) the
    visit's target-loadout weapon is worn -- after the swap, not during it.  The mining
    fundraise runs its Yeek cave 1F floors through town: the restock-wait owners (the
    Magic-Eater's staff stock-out, the Identify-staff and recall stock-outs, the town end's
    cycle) open a one-run set, its return to town ends the set (policy_observation, the run
    count), and the visit opens the next one-run set late in its errands.  Each such visit took
    the hands back first -- the town re-arm (``_town_restore_weapon_key``) or the visit's
    equipment swap wielded the weapon, took the diggers off and even deposited them in the Home,
    and the mining kit withdrew one again -- and the next floor's ``_wield_digging_tool_key``
    stripped the weapon: n1-c life-220 (2026-11-22 06:04-06:13, build 56fa91268, Lv8
    Magic-Eater, me-staff:fundraise:staff-stockout) wore ロング・ソード in town and シャベル on 1F
    by turns every few seconds (equipment-visit.jsonl, decisions 269/328/407/421/429/444 ...).

    So in town, with a digger in a hand, the hands are lent while a mining set is open (mode
    "prepare" or "mine": the next departure is the mining walk-in) or while the visit a run
    came back to has not asked for an ordinary departure (``note_run_return`` /
    ``end_lending``): neither town owner touches them, nor starts the visit's swap.  An
    ordinary departure asks for the weapon (policy ``_combat_weapon_ready``, the walk-in's
    ``_descent_is_blocked``: ``departure_asks_weapon``) and ends the lending, so the visit's
    target loadout is worn before it leaves.  The dungeon's own fight rules still re-arm on
    contact (MINING_COMBAT_CONTACT_LIMIT)."""
    if not (getattr(snapshot, "in_town", False) or getattr(snapshot, "store", None) is not None):
        return False
    if not _digger_in_hand(snapshot):
        return False
    mode = getattr(policy, "_fundraising_mode", None)
    if mode in LENDING_MODES:
        return True
    # A scavenging set does not dig: its departure is no mining walk-in.
    return mode is None and bool(getattr(policy, RETURN_STATE, False))


def departure_asks_weapon(policy, snapshot) -> bool:
    """An ordinary departure (not the mining walk-in) asks for the weapon: the lending of a run's
    return ends here, and True says the hands were still lent (the caller's departure waits one
    decision for the town re-arm or the visit's swap to wear the target's weapon)."""
    lent = hands_lent(policy, snapshot) and getattr(policy, "_fundraising_mode", None) not in LENDING_MODES
    if lent:
        end_lending(policy)
    return lent


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


def stray_off_hand_digger(snapshot):
    """The digger worn in the off hand beside a main-hand combat weapon, else None.

    The restore takes it off (``_restore_mining_combat_hand_key``); when the
    town pack budget refuses that takeoff, wielding a pack weapon into the
    main hand only displaced the worn one into the pack: n1-c life-113
    (2026-11-03 01:34) swapped タルワール and サーベル beside the off-hand
    穴掘りのドワーフのつるはし until stall:town:restore-combat-weapon, twice.
    """
    main, sub = worn_in_slot(snapshot, "main_hand"), worn_in_slot(snapshot, "sub_hand")
    if (sub is None or not sub.is_digging_tool or main is None
            or main.is_digging_tool or not main.is_melee_weapon):
        return None
    return sub


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


def begin_swap(policy, snapshot, reason: str) -> None:
    """The digger swap stripped a combat hand for ``reason``'s digger (policy_equipment
    ``_wield_digging_tool_key``): the swap is in progress until its digger is worn or it aborts."""
    policy._digger_swap = (snapshot.floor_key, reason)


def swap_in_progress(policy, snapshot) -> bool:
    """A combat hand is off for the digger and the digger is not worn yet: the hand is the swap's.

    One owner for the weapon slot (n1-b life-413, Angband 12F, 2026-11-21 19:02:06,
    stall:floor-dwell): stuck:walled-off-wield-digger took the Long Sword off ('ta'); on the next
    board the breakout's restore rung read "no digger worn" as the swap over and cleared the dig
    floor, so ``swap_abandoned`` held and the re-arm wielded the sword back ('wq') before the
    digger's wield -- 97 times each.  The swap ends by the game's state, never by a count of
    moves: the digger worn (done), the floor left, or the swap's own abort (``finish_swap_key``)."""
    swap = getattr(policy, "_digger_swap", None)
    if swap is None:
        return False
    if swap[0] != snapshot.floor_key or policy._equipped_digging_tool(snapshot) is not None:
        policy._digger_swap = None
        return False
    return True


def finish_swap_key(policy, snapshot) -> str | None:
    """The swap's second post, by the swap itself: the digger wielded on the emptied hand, else
    (an awake hostile in view: ``strip_allowed``, or no digger left to wield) the abort, the
    displaced weapon wielded back.  Asked before any other rung that would act on the hand."""
    if not swap_in_progress(policy, snapshot):
        return None
    reason = policy._digger_swap[1]
    if strip_allowed(policy, snapshot):
        key = policy._wield_digging_tool_key(snapshot, reason)
        if key is not None:
            return key
    policy._digger_swap = None
    target = _rearm_target(policy, snapshot)
    if target is None:
        return None
    slot, item = target
    key = policy._equipment_wield(snapshot, ROLLBACK_GOAL, item, slot)
    if key is not None:
        policy.last_reason = REARM_REASON
    return key


def swap_abandoned(policy, snapshot) -> bool:
    """No owner of the digger swap will wield the digger on this board.

    The mining run wields it only while it goes on (mode "mine", no return
    latched: policy_fundraising ``_fundraising_key`` hands a latched return
    to the floor exit at once); the dig-to-stairs breakout, the walk-out dig
    and the enclosure dig mark their floor (``_breakout_dig_floor``) when
    they strip, and the breakout's restore rung clears it once no dig route
    is left.  n1-a life-518 (2026-11-12, Yeek cave 1F): 'ta' at 139869, a
    worm mass, two Teleportation scrolls, then the return walked
    bare-handed from 139938 to the stop at 156613 with nothing in view.
    """
    if policy._breakout_dig_floor == snapshot.floor_key or swap_in_progress(policy, snapshot):
        return False
    return policy._returning_to_town or policy._fundraising_mode != "mine"


def _flight_first(policy, snapshot, hostiles) -> bool:
    """Flight goes before the re-arm only where the turn the wield costs is not free.

    An awake hostile beside the player strikes during the wield, and below
    FLEE_HP_RATIO no turn is spent before leaving; otherwise the empty hand
    is the flight's own cause (a free damage of 0 reads every monster T1:
    n1-a life-518 fled a Lv1 white worm mass three cells away at 139876 and
    read ten Teleportation scrolls), so the weapon goes back first and the
    flight is judged again with it.
    """
    adjacent = policy._physical_adjacent_hostiles(snapshot)
    if not policy._should_flee(snapshot, hostiles, adjacent):
        return False
    return bool(awake(adjacent)) or snapshot.player.hp_ratio < FLEE_HP_RATIO


def rollback_key(policy, snapshot) -> str | None:
    """Re-arm a combat hand the digger swap left empty before a fight, or
    while no swap owner will wield the digger (``swap_abandoned``)."""
    if snapshot.in_town or getattr(snapshot, "store", None) is not None:
        return None
    if swap_in_progress(policy, snapshot):
        # The emptied hand is the swap's: it wields the digger, or aborts and re-arms itself.
        return finish_swap_key(policy, snapshot)
    if not any(item.is_digging_tool for item in snapshot.inventory):
        return None
    hostiles = policy._physical_hostiles(snapshot)
    if not awake(hostiles):
        if (snapshot.player.class_id in MARTIAL_ARTS_CLASS_IDS
                or not swap_abandoned(policy, snapshot)):
            return None
    target = _rearm_target(policy, snapshot)
    if target is None:
        return None
    if awake(hostiles) and _flight_first(policy, snapshot, hostiles):
        return None
    slot, item = target
    key = policy._equipment_wield(snapshot, ROLLBACK_GOAL, item, slot)
    if key is not None:
        policy.last_reason = REARM_REASON
    return key
