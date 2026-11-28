"""The *Destruction* means: the one fact every reader of "is there a *Destruction* means" reads.

Maintainability review of the whole bot 2026-11-16 (R1).  Stage 2 gathered the six readers' raw
facts into ``Means`` with each reader's own combination; stage 3 (owner, review section 6 Q1,
verbatim 「深さの条件の定義に揃える」) gives every reader the depth condition's definition
(``depth_gate``, destruction_use.holds_means): a staff or the absorbed power at 80%+ with a
charge, a scroll no means (owner 2026-11-04), in town a Home staff at 80% too.  A reader keeps its
own quantity where it is a count, but the count holds only what the definition counts:

| reader                                        | answer / quantity                                    |
|-----------------------------------------------|------------------------------------------------------|
| destruction_use.holds_means                   | ``depth_gate``: the definition                       |
| policy._has_destruction_method                | ``depth_gate``                                       |
| policy._total_destruction_uses                | ``departure_uses``: the absorbed charges and the     |
|                                               | carried staves' charges when the staff is reliable   |
| destruction_use.owns_charged_staff            | ``staff_means``: the staff part of the definition    |
| destruction_use.staff_carry_uses              | ``carry_uses``: the owned staff charges to carry,    |
|                                               | when the staff part holds                            |
| policy_equipment._optimizer_destruction_means | the absorbed power, else the owned staff per loadout |
|                                               | at the definition's skill (``staff_gate``)           |
| destruction_use.usable / key (the means part) | the absorbed cast, else a reliable carried staff     |
| ``departure_carried`` (the 50F+ arrivals)     | ``carried``: the definition without the Home staves  |

``supplies(item)`` is the definition's test of one item: the departure's purchase, the Home-first
take and their quantities count only an item that adds a means (a staff the worn loadout makes
reliable).  ``staff_owned`` is the item fact without the success, read only where the gear search
asks which loadout would make the staff a means (the optimizer's StaffGate, ability_gear's
MAGIC_MASTERY search); it answers no "is there a means".

The invariant (``violations``): no reader answers a means the definition denies, and the exact
readers equal it.  cross_rules records ``cross-rule:destruction-means:broken`` on a board that
breaks it (none is expected; the tests assert none).  scripts/destruction_means_lint.py fails
when a module outside this one reads SV_STAFF_DESTRUCTION or the ``_is_destruction_*``
predicates at a site not on its list.

The recharge (owner 2026-11-28 「盗賊が破壊の杖をチャージして使い回せるようにして」, n1-a life-545):
a staff counts by its known charges, so an empty staff is no means and no stock (``supplies``,
``charged_staves``).  ``recharge_planned`` answers "does this stay's Tower trip recharge the
staves" (wand_tower_recharge, the Stone to Mud wands' trip): the uses wanted (``wanted_uses``, the
depth table's at the depth the means would open) are short of the owned charged staves, a carried
or Home staff takes a charge, and the trip is possible and spare.  Its readers: the Home take of
the empty staves (``home_recharge_take``), the pack's retention (``retains``), the trip's list
(wand_tower_recharge.short) and the purchases' fallback (``recharge_covers``: the Black Market's
staff row and the departure's *Destruction* rung buy nothing while it fills the shortage).

Every fact is computed on first read and only for the ``Means`` it belongs to (one ask, one
board): nothing is kept between asks.
"""

from __future__ import annotations

from functools import cached_property

from hengbot.model import SV_SCROLL_STAR_DESTRUCTION, SV_STAFF_DESTRUCTION, TVAL_SCROLL, TVAL_STAFF
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot import deep_admission
from hengbot.policy_constants import DESTRUCTION_USES_PER_STEP, PLAYER_CLASS_BERSERKER

SCROLL = (TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION)
STAFF = (TVAL_STAFF, SV_STAFF_DESTRUCTION)
POWER = ("staff", SV_STAFF_DESTRUCTION)
STAFF_LEVEL = 50             # BaseitemDefinitions.jsonc id 307
HOME_STAFF = "_destruction_home_staves"  # the last complete Home catalogue's known staves


# -- the kinds --------------------------------------------------------------------

def is_scroll(item) -> bool:
    return item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_DESTRUCTION


def is_staff(item) -> bool:
    return item.tval == TVAL_STAFF and item.sval == SV_STAFF_DESTRUCTION


def is_item(item) -> bool:
    """Either carrier of the 50F+ *Destruction* gate, shelf or pack."""
    return is_scroll(item) or is_staff(item)


def stack_charges(item) -> int:
    """policy._stack_charges: the charges one stack represents."""
    return max(0, item.charges) * max(1, item.count)


def known_staves(items) -> tuple:
    """The staves whose charges are known (sval is sent for AWARE items, charges for KNOWN ones)."""
    return tuple(item for item in items if is_staff(item) and item.known)


def charged_staves(items) -> tuple:
    """The known staves with a charge.  An empty staff, or one whose charges are not known, is no
    use: no means and no stock (owner 2026-11-28, n1-a life-545)."""
    return tuple(item for item in known_staves(items) if item.charges > 0)


def staff_units(item, uses: int) -> int:
    """The staves of ``item``'s stack that carry ``uses`` charges (at least one, at most the
    stack): a Home take of the staff moves staves, the shortage counts uses."""
    per_staff = max(1, item.charges)
    return max(0, min(item.count, -(-uses // per_staff)))


def staff_home_known(policy, snapshot) -> tuple:
    """The Home's known staves, in town only: the page knowledge, else the last complete
    catalogue's (``HOME_STAFF``, destruction_use.observe)."""
    if not snapshot.in_town:
        return ()
    if getattr(policy, "_home_knowledge_current", False):
        return known_staves(getattr(policy, "_home_knowledge_items", ()))
    return tuple(getattr(policy, HOME_STAFF, ()) or ())


def staff_home_items(policy, snapshot) -> tuple:
    """The Home's charged staves, in town only (``staff_home_known``)."""
    return charged_staves(staff_home_known(policy, snapshot))


# -- the recharge (owner 2026-11-28 「盗賊が破壊の杖をチャージして使い回せるようにして」) ----------
#
# market/building-recharger.cpp building_recharge_all (Morivant's Tower of Sorcery 'a', the trip
# of wand_tower_recharge) never fails and fills a staff to its kind's pval: 5 for this staff
# (lib/edit/BaseitemDefinitions.jsonc id 307, line 10967), at (cost 7500 / 10) * number gold a
# charge (building-recharger.cpp:173-176): 750 a charge, 3750 an empty staff.  A Scroll of
# Recharging (recharge(130), magic-item-recharger.cpp:79-91,177-179) blows the staff up at one in
# (180 - 8 * charges) / 15 reads (1 in 12 empty) for 1-3 charges: the scroll is not used.

def refill_uses(item) -> int:
    """The uses the Tower's recharge adds to ``item``'s stack (morivant_tower's fill; a staff's
    pval is per staff, use-execution.cpp:118-127)."""
    from hengbot import morivant_tower

    return max(0, morivant_tower.charges_after_recharge(item) - item.charges) * max(1, item.count)


def recharge_take_units(item, uses: int) -> int:
    """The staves of ``item``'s Home stack whose recharge adds ``uses`` (at most the stack)."""
    from hengbot import morivant_tower

    per_staff = morivant_tower.charges_after_recharge(item) - item.charges
    if per_staff <= 0 or uses <= 0:
        return 0
    return min(item.count, -(-uses // per_staff))


# -- the staff's success ------------------------------------------------------------

def device_success(player, kind: str, level: int) -> float:
    """A carried device's success percent (not confused), the one reading of it: a staff's
    (use-execution.cpp) or a wand's (zapwand-execution.cpp) chance is skill - level
    (attack_expectation.device_use_success), a rod's is zaprod-execution.cpp's
    (attack_expectation.rod_use_success), at the board's device skill (the worn loadout's);
    stunned, times the chance check_stun lets the use through (me_powers.STUN_ITEM_PENALTY, all
    three commands ask it); a Berserker always fails."""
    from hengbot import attack_expectation, me_powers

    if player.class_id == PLAYER_CLASS_BERSERKER:
        return 0.0
    chance = (attack_expectation.rod_use_success if kind == "rod"
              else attack_expectation.device_use_success)
    success = chance(player.device_skill, level) * 100
    if player.stunned:
        success *= (100 - me_powers.STUN_ITEM_PENALTY[me_powers._stun_rank(player)]) / 100
    return success


def staff_success(player, level: int) -> float:
    """A carried staff's success percent (``device_success``)."""
    return device_success(player, "staff", level)


def reliable_skill() -> int:
    """The device skill at which the staff is a means (``RELIABLE_MIN_SUCCESS``)."""
    from hengbot import device_skill, me_capability

    return device_skill.reliable_staff_skill(STAFF_LEVEL, me_capability.RELIABLE_MIN_SUCCESS)


def staff_gate(player, loadout, natural_int: int, intrinsic_int: int):
    """The staff's success per loadout: device_skill.StaffGate at ``reliable_skill``."""
    from hengbot import device_skill

    return device_skill.staff_gate(player, loadout, natural_int, intrinsic_int, reliable_skill())


# -- the fact -----------------------------------------------------------------------

class Means:
    """The raw facts of one board's *Destruction* means, read on first use."""

    def __init__(self, policy, snapshot) -> None:
        self.policy = policy
        self.snapshot = snapshot

    @cached_property
    def berserker(self) -> bool:
        return self.snapshot.player.class_id == PLAYER_CLASS_BERSERKER

    def town_absorbs(self, item) -> bool:
        """A Magic-Eater's staff the town absorbs (me_device_policy.absorbs: the *Destruction* row
        「持ち帰って充填してから取り込む」, below the count cap): it ends as the absorbed power, so
        in town it is that power's means (``absorbed_charges``, 80%+), never a staff means.

        n1-b life-413 2026-11-22 00:13:49-00:13:55: a bought staff, reliable at the worn device
        skill, opened the optimizer's 80F band (the launcher read for its abilities, owner
        2026-11-18: ★森の狩人ロビンフッドのショート・ボウ worn); the staff sequence absorbed it
        four seconds later into a power at 75%, the band fell back to 49F and the Light Crossbow
        was worn again (owner 2026-11-22 「一瞬変えた後戻してるみたい」)."""
        if not self.snapshot.in_town or self.snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
            return False
        from hengbot import me_device_policy

        return me_device_policy.absorbs(self.policy, self.snapshot, item)

    def kept_staves(self, items) -> tuple:
        """``charged_staves`` of ``items`` but the ones the town absorbs (``town_absorbs``)."""
        return tuple(item for item in charged_staves(items) if not self.town_absorbs(item))

    @cached_property
    def carried_charged_staff(self):
        """The first known carried staff with a charge the town does not absorb, else None."""
        return next(iter(self.kept_staves(self.snapshot.inventory)), None)

    @cached_property
    def home_staves(self) -> tuple:
        """The Home's charged staves the town does not absorb (town only)."""
        return self.kept_staves(staff_home_items(self.policy, self.snapshot))

    @cached_property
    def owned_staff_charges(self) -> int:
        """The charges of the known charged staves carried and (in town) in the Home."""
        return sum(stack_charges(item) for item in
                   (*self.kept_staves(self.snapshot.inventory), *self.home_staves))

    @cached_property
    def staff_success(self) -> float:
        """The staff's success with the worn loadout (the board's device skill), stun included."""
        return staff_success(self.snapshot.player, STAFF_LEVEL)

    @cached_property
    def staff_reliable(self) -> bool:
        from hengbot import me_capability

        return self.staff_success >= me_capability.RELIABLE_MIN_SUCCESS

    @cached_property
    def absorbed_charges(self) -> int:
        """The absorbed power's charges me_capability's counting row adds (in a town whose inn
        refills it, the refilled count: me_capability.charges, me_inn_refill.refill_open)."""
        from hengbot import me_capability

        return me_capability.replacing_charges(self.policy, self.snapshot, STAFF)

    @cached_property
    def staff_owned(self) -> bool:
        """A known charged staff carried or (in town) in the Home, its success not asked: the
        item fact the gear search reads (which loadout would make it a means), no means itself."""
        return (self.carried_charged_staff is not None
                or next(iter(self.home_staves), None) is not None)

    @cached_property
    def staff_means(self) -> bool:
        """The definition's staff part: an owned charged staff the worn loadout makes reliable."""
        return self.staff_reliable and self.staff_owned

    def supplies(self, item) -> bool:
        """``item`` adds a *Destruction* means by the definition: a known charged staff
        (``charged_staves``) the worn loadout makes reliable and the town does not absorb
        (``town_absorbs``).  A scroll never does (owner 2026-11-04), nor an empty staff: n1-a
        life-545 (2026-11-28 15:13) took 11 empty staves from the Home for an 11-use shortage."""
        return (bool(charged_staves((item,))) and self.staff_reliable
                and not self.town_absorbs(item))

    # -- the recharge (owner 2026-11-28) --

    def rechargeable(self, item) -> bool:
        """A known staff the Tower's recharge adds a use to, kept as the item (not absorbed)."""
        return (bool(known_staves((item,))) and not self.town_absorbs(item)
                and refill_uses(item) > 0)

    @cached_property
    def wanted_uses(self) -> int:
        """The uses the character wants owned: the depth table's at the depth it would dive to
        holding the means (policy._means_held_dive_depth); short of 50F the staff it carries
        whatever the depth (``carry_uses``' DESTRUCTION_USES_PER_STEP, owner 2026-11-15)."""
        from hengbot.policy_constants import required_destruction_uses

        return (required_destruction_uses(self.policy._means_held_dive_depth(self.snapshot))
                or DESTRUCTION_USES_PER_STEP)

    @cached_property
    def recharge_short(self) -> int:
        """The wanted uses the owned charged staves (carried and Home) leave missing, in town,
        when the worn loadout makes the staff reliable (else a recharge adds no means)."""
        if not self.snapshot.in_town or not self.staff_reliable:
            return 0
        return max(0, self.wanted_uses - self.owned_staff_charges)

    @cached_property
    def carried_refill(self) -> int:
        return sum(refill_uses(item) for item in self.snapshot.inventory
                   if self.rechargeable(item))

    @cached_property
    def home_recharge_stack(self):
        """The Home stack a recharge takes from: the emptiest (the fewest staves to carry for the
        uses; the gold per use is the same), then the largest; None without one."""
        stacks = [item for item in staff_home_known(self.policy, self.snapshot)
                  if self.rechargeable(item) and item.count > 0]
        return min(stacks, key=lambda item: (item.charges, -item.count, item.name), default=None)

    @cached_property
    def home_take_uses(self) -> int:
        """The uses the Home's rechargeable staves would be taken out for: the shortage the
        carried rechargeable staves do not fill."""
        return max(0, self.recharge_short - self.carried_refill)

    @cached_property
    def home_take_units(self) -> int:
        stack = self.home_recharge_stack
        return recharge_take_units(stack, self.home_take_uses) if stack is not None else 0

    @cached_property
    def recharge_planned(self) -> bool:
        """This stay's Tower trip recharges the staves: a recharge adds a wanted use (carried, or
        Home staves to take), the trip can run this stay (wand_tower_recharge.staff_trip_open)
        and its gold is spare with the Home staves' price (staff_trip_spare).  Nothing is taken
        out of the Home or kept in the pack for a trip that cannot be paid."""
        if self.recharge_short <= 0 or (self.carried_refill <= 0 and self.home_take_units <= 0):
            return False
        from hengbot import morivant_tower, wand_tower_recharge

        if not wand_tower_recharge.staff_trip_open(self.policy, self.snapshot):
            return False
        stack, take = self.home_recharge_stack, self.home_take_units
        extra = (morivant_tower.recharge_all_price(stack, morivant_tower.device_definitions())
                 // max(1, stack.count) * take if take else 0)
        return wand_tower_recharge.staff_trip_spare(self.policy, self.snapshot, extra)

    def home_recharge_take(self, item) -> int:
        """The staves of the Home stack ``item`` taken out to be recharged this stay (0 for any
        other stack, or without the planned trip)."""
        stack = self.home_recharge_stack
        if stack is None or (item.name, item.count, item.charges) != (
                stack.name, stack.count, stack.charges) or not self.recharge_planned:
            return 0
        return self.home_take_units

    def retained_for_recharge(self, item) -> bool:
        """A carried rechargeable staff waits in the pack for the stay's planned recharge."""
        return self.rechargeable(item) and self.recharge_planned

    def retains(self, item, gate_open: bool) -> bool:
        """A carried *Destruction* item (policy_home's retention) stays in the pack: while the
        departure wants uses (``gate_open``) a scroll, a staff of unknown charges and a charged
        staff; an empty staff only for the stay's planned recharge (``retained_for_recharge``)."""
        if self.retained_for_recharge(item):
            return True
        return gate_open and (not known_staves((item,)) or bool(charged_staves((item,))))

    def recharge_covers(self) -> bool:
        """The stay's planned recharge fills the whole shortage: no staff is bought for it
        (buying is the recharge's fallback)."""
        if not self.recharge_planned:
            return False
        stack = self.home_recharge_stack
        per_staff = refill_uses(stack) // max(1, stack.count) if stack is not None else 0
        return self.carried_refill + per_staff * self.home_take_units >= self.recharge_short

    # -- the readers (owner 2026-11-16 「深さの条件の定義に揃える」) --

    def depth_gate(self) -> bool:
        """destruction_use.holds_means, the definition: the absorbed power at 80%+ with a charge,
        or a charged staff at 80%+ carried or (town) in the Home; a scroll is no means."""
        return self.absorbed_charges > 0 or self.staff_means

    def carried(self) -> bool:
        """The definition on what the character takes with him: the absorbed power with a charge,
        or a carried charged staff the worn loadout makes reliable -- the Home staves left out.
        Out of town it is ``depth_gate`` itself (the Home is counted in town only).

        Owner 2026-11-18 (n1-a life-530), verbatim 「破壊を持っていないのに50F以降にいるのが不具合」:
        the town's ``depth_gate`` counts a Home staff so the 50F+ destination opens and the
        departure takes it (owner 2026-11-15); what lands at 50F+ is what is carried, so every
        town-to-dungeon arrival at 50F+ asks this one (``departure_carried``)."""
        return self.absorbed_charges > 0 or (
            self.staff_reliable and self.carried_charged_staff is not None)

    def departure_uses(self) -> int:
        """policy._total_destruction_uses: the absorbed charges and, when the worn loadout makes
        the staff reliable, every carried known staff's charges (user decision 2026-09-23 counts
        the charges); a scroll counts nothing.  More than 0 only when ``depth_gate`` holds."""
        carried = (sum(stack_charges(item) for item in self.kept_staves(self.snapshot.inventory))
                   if self.staff_reliable else 0)
        return carried + self.absorbed_charges

    def owns_staff(self) -> bool:
        """destruction_use.owns_charged_staff: the definition's staff part (``staff_means``)."""
        return self.staff_means

    def carry_uses(self) -> int:
        """destruction_use.staff_carry_uses: the owned staff charges carried short of 50F, when the
        definition's staff part holds."""
        if not self.staff_means:
            return 0
        return min(DESTRUCTION_USES_PER_STEP, self.owned_staff_charges)

    def optimizer_without_gear(self) -> bool:
        """policy_equipment._optimizer_destruction_means' first test: the absorbed power is a
        means in every loadout without a NO_MAGIC (equipment_optimizer.destruction_means; a
        scroll is none).  Asked of the board with the worn NO_MAGIC taken off: a worn one
        refuses the power on this board, not in the loadouts the search weighs (n1-b
        life-411 2026-11-21 04:55: worn, every loadout read as without the means)."""
        return self.unrefused_absorbed_charges > 0

    @cached_property
    def unrefused_absorbed_charges(self) -> int:
        """``absorbed_charges`` on this board with no worn NO_MAGIC."""
        from dataclasses import replace

        from hengbot import me_capability, me_power_success

        if not me_power_success.worn_anti_magic(self.snapshot):
            return self.absorbed_charges
        flag = me_power_success.TR_NO_MAGIC
        board = replace(self.snapshot, equipment=tuple(
            replace(item, known_flags=item.known_flags - {flag}) if flag in item.known_flags
            else item for item in self.snapshot.equipment))
        return me_capability.replacing_charges(self.policy, board, STAFF)

    def optimizer_staff_owned(self) -> bool:
        """The optimizer's second test: an owned charged staff, no Berserker's; its StaffGate
        then asks the definition's skill per loadout."""
        return not self.berserker and self.staff_owned

    def optimizer_worn(self) -> bool:
        """The optimizer's answer for the worn loadout (its StaffGate opens at the board's
        device skill; the stun is not asked, the gear does not change with a stun)."""
        return self.optimizer_without_gear() or (
            self.optimizer_staff_owned()
            and self.snapshot.player.device_skill >= reliable_skill())

    def in_hand(self) -> bool:
        """destruction_use's means part of ``usable``/``key``: the absorbed cast, else a reliable
        carried staff (the scene and the item's key not asked)."""
        from hengbot import destruction_use

        return destruction_use.means_in_hand(self.policy, self.snapshot)


# (name, reader, exact) in the observer's row order.  An exact reader equals the definition;
# the others are parts or counts of it and may answer no where it holds, never yes where it
# does not.
COMBINATIONS = (
    ("holds", "destruction_use.holds_means", True),
    ("departure", "policy._has_destruction_method", True),
    ("departure-uses", "policy._total_destruction_uses", False),
    ("owns", "destruction_use.owns_charged_staff", False),
    ("carry", "destruction_use.staff_carry_uses", False),
    ("optimizer", "policy_equipment._optimizer_destruction_means", False),
    ("in-hand", "destruction_use.usable", False),
    ("carried", "destruction_means.departure_carried", False),
)


def departure_carried(policy, snapshot, depth: int) -> bool:
    """A town-to-dungeon arrival at ``depth`` is allowed by the *Destruction* rule: short of
    50F always; from 50F only with the means carried (``Means.carried``).  The departure
    leaf ``destruction_carried`` (policy_town) and the final town-to-dungeon boundary
    (policy_navigation._dungeon_entry_allowed) read it."""
    from hengbot import deep_climb  # import cycle

    # Owner 2026-11-22 「城の50Fに帰還してすぐ38〜42Fへ登る」: the held Castle's 50F landing is
    # climbed from at once without the means (deep_climb).
    return deep_admission.verdict(
        policy._target_dungeon_id, depth, "recall", Means(policy, snapshot).carried,
        lambda: deep_climb.departure_admits(policy, snapshot, depth)).admitted


def answers(policy, snapshot) -> tuple:
    """(name, bool) per reader on this board, through the readers' own entry points."""
    from hengbot import destruction_use

    means = Means(policy, snapshot)
    readers = {
        "holds": lambda: destruction_use.holds_means(policy, snapshot),
        "departure": lambda: policy._has_destruction_method(snapshot),
        "departure-uses": lambda: policy._total_destruction_uses(snapshot) > 0,
        "owns": lambda: destruction_use.owns_charged_staff(policy, snapshot),
        "carry": lambda: destruction_use.staff_carry_uses(policy, snapshot) > 0,
        "optimizer": means.optimizer_worn,
        "in-hand": means.in_hand,
        "carried": means.carried,
    }
    return tuple((name, bool(readers[name]())) for name, _reader, _exact in COMBINATIONS)


def violations(policy, snapshot) -> tuple:
    """The readers that break the invariant on this board: an exact reader that differs from the
    definition, or any reader that answers a means the definition denies.  The optimizer's worn
    answer does not ask the stun (the gear's reading), so it is not compared on a stunned board."""
    rows = answers(policy, snapshot)
    definition = dict(rows)["holds"]
    stunned = bool(snapshot.player.stunned)
    broken = []
    for (name, answer), (_name, _reader, exact) in zip(rows, COMBINATIONS):
        if name == "optimizer" and stunned:
            continue
        if (exact and answer != definition) or (answer and not definition):
            broken.append(name)
    return tuple(broken)
