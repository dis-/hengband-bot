"""The *Destruction* means: the one fact every reader of "is there a *Destruction* means" reads.

Maintainability review of the whole bot 2026-11-16 (R1, stage 2; behaviour-preserving).  Six
readers asked the same question with four definitions, each reading the pack, the Home, the
staff's success and the absorbed power on its own.  ``Means`` now gathers the raw facts once per
ask, and each reader keeps today's combination under a name below (``COMBINATIONS``):

| combination          | reader                                              | scroll | carried staff | 80% | absorbed | Home staff |
|----------------------|-----------------------------------------------------|--------|---------------|-----|----------|------------|
| ``depth_gate``       | destruction_use.holds_means                         | no     | yes           | yes | yes      | town, 80%  |
| ``departure_uses``   | policy._total_destruction_uses / _has_destruction_method | yes | yes (all)  | no  | yes      | no         |
| ``owns_staff``       | destruction_use.owns_charged_staff                  | no     | yes           | no  | no       | town       |
| ``carry_uses``       | destruction_use.staff_carry_uses                    | no     | yes           | yes | no       | town       |
| ``optimizer``        | policy_equipment._optimizer_destruction_means       | yes    | per loadout   | per loadout | yes | town  |
| ``in_hand``          | destruction_use.usable / key (the means part)       | no     | yes           | yes (stun) | yes (stun, cast) | no |

The differences are kept as they are (the owner decides how to align them, review §6 Q1); the
record-only observer ``cross-rule:destruction-means`` (cross_rules) logs the boards where the
answers disagree.  scripts/destruction_means_lint.py fails when a module outside this one reads
SV_STAFF_DESTRUCTION or the ``_is_destruction_*`` predicates at a site not on its list.

Every fact is computed on first read and only for the ``Means`` it belongs to (one ask, one
board): a combination reads the facts in the order and with the short-circuits its reader had,
and nothing is kept between asks.
"""

from __future__ import annotations

from functools import cached_property

from hengbot.model import SV_SCROLL_STAR_DESTRUCTION, SV_STAFF_DESTRUCTION, TVAL_SCROLL, TVAL_STAFF
from hengbot.policy_constants import DESTRUCTION_USES_PER_STEP, PLAYER_CLASS_BERSERKER

SCROLL = (TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION)
STAFF = (TVAL_STAFF, SV_STAFF_DESTRUCTION)
POWER = ("staff", SV_STAFF_DESTRUCTION)
STAFF_LEVEL = 50             # BaseitemDefinitions.jsonc id 307
HOME_STAFF = "_destruction_home_staves"  # the last complete Home catalogue's charged staves


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


def charged_staves(items) -> tuple:
    """The known staves with a charge (sval is sent for AWARE items, charges for KNOWN ones)."""
    return tuple(item for item in items if is_staff(item) and item.known and item.charges > 0)


def staff_home_items(policy, snapshot) -> tuple:
    """The Home's charged staves, in town only: the page knowledge, else the last complete
    catalogue's (``HOME_STAFF``, destruction_use.observe)."""
    if not snapshot.in_town:
        return ()
    if getattr(policy, "_home_knowledge_current", False):
        return charged_staves(getattr(policy, "_home_knowledge_items", ()))
    return tuple(getattr(policy, HOME_STAFF, ()) or ())


# -- the staff's success ------------------------------------------------------------

def staff_success(player, level: int) -> float:
    """A carried staff's success percent (not confused): use-execution.cpp's chance
    (attack_expectation) at the item's level; stunned, times the chance check_stun lets the
    use through (me_powers.STUN_ITEM_PENALTY); a Berserker always fails."""
    from hengbot import attack_expectation, me_powers

    if player.class_id == PLAYER_CLASS_BERSERKER:
        return 0.0
    success = attack_expectation.device_use_success(player.device_skill, level) * 100
    if player.stunned:
        success *= (100 - me_powers.STUN_ITEM_PENALTY[me_powers._stun_rank(player)]) / 100
    return success


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

    @cached_property
    def scroll_count(self) -> int:
        """The carried *Destruction* scrolls."""
        return sum(max(0, item.count) for item in self.snapshot.inventory if is_scroll(item))

    @cached_property
    def carried_staff_charges(self) -> int:
        """The charges of every carried staff stack (an untried staff shows none)."""
        return sum(stack_charges(item) for item in self.snapshot.inventory if is_staff(item))

    @cached_property
    def carried_charged_staff(self):
        """The first known carried staff with a charge, else None."""
        return next(iter(charged_staves(self.snapshot.inventory)), None)

    @cached_property
    def home_staves(self) -> tuple:
        """The Home's charged staves (town only)."""
        return staff_home_items(self.policy, self.snapshot)

    @cached_property
    def owned_staff_charges(self) -> int:
        """The charges of the known charged staves carried and (in town) in the Home."""
        return sum(stack_charges(item) for item in
                   charged_staves((*self.snapshot.inventory, *self.home_staves)))

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

    # -- the readers' combinations (kept as they are; review §6 Q1) --

    def depth_gate(self) -> bool:
        """destruction_use.holds_means: a staff or absorbed power at 80%+ with a charge; a scroll
        is no means (owner 2026-11-04); in town a Home staff counts at 80%."""
        return (self.absorbed_charges > 0
                or (self.staff_reliable and self.carried_charged_staff is not None)
                or (self.staff_reliable and next(iter(self.home_staves), None) is not None))

    def departure_uses(self) -> int:
        """policy._total_destruction_uses: scrolls, every carried staff's charges and the absorbed
        charges, the success not asked (user decision 2026-09-23)."""
        return self.scroll_count + self.carried_staff_charges + self.absorbed_charges

    def owns_staff(self) -> bool:
        """destruction_use.owns_charged_staff: a known charged staff carried or (town) in the Home."""
        return (self.carried_charged_staff is not None
                or next(iter(self.home_staves), None) is not None)

    def carry_uses(self) -> int:
        """destruction_use.staff_carry_uses: the owned staff charges carried short of 50F."""
        if self.berserker or not self.staff_reliable:
            return 0
        return min(DESTRUCTION_USES_PER_STEP, self.owned_staff_charges)

    def optimizer_without_gear(self) -> bool:
        """policy_equipment._optimizer_destruction_means' first test: the absorbed power or a
        carried scroll is a means in every loadout."""
        return self.absorbed_charges > 0 or self.scroll_count > 0

    def optimizer_staff_owned(self) -> bool:
        """The optimizer's second test: an owned charged staff, no Berserker's."""
        return not self.berserker and self.owns_staff()

    def optimizer_worn(self) -> bool:
        """The optimizer's answer for the worn loadout (its StaffGate opens at the board's
        device skill); the observer's reading, no decision asks it."""
        return self.optimizer_without_gear() or (
            self.optimizer_staff_owned()
            and self.snapshot.player.device_skill >= reliable_skill())


# reader -> its combination (the observer's row order).
COMBINATIONS = (
    ("holds", "destruction_use.holds_means", "depth_gate"),
    ("departure", "policy._total_destruction_uses", "departure_uses"),
    ("owns", "destruction_use.owns_charged_staff", "owns_staff"),
    ("carry", "destruction_use.staff_carry_uses", "carry_uses"),
    ("optimizer", "policy_equipment._optimizer_destruction_means", "optimizer_worn"),
    ("in-hand", "destruction_use.usable", None),
)


def answers(policy, snapshot) -> tuple:
    """(name, bool) per reader on this board, for the record-only observer.  ``in-hand`` is
    destruction_use's means part of ``usable``/``key`` (the absorbed cast, else a reliable carried
    staff), the scene and the item's key not asked."""
    from hengbot import destruction_use

    means = Means(policy, snapshot)
    rows = []
    for name, _reader, combination in COMBINATIONS:
        if combination is None:
            value = (destruction_use._absorbed_key(policy, snapshot) is not None
                     or destruction_use._reliable_carried_staff(policy, snapshot) is not None)
        else:
            value = getattr(means, combination)()
        rows.append((name, bool(value)))
    return tuple(rows)
