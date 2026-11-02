"""One shared carry plan for launcher ammunition."""

from dataclasses import dataclass, replace
from types import SimpleNamespace

from hengbot.launcher_damage import launcher_average_damage


@dataclass(frozen=True)
class AmmoCarryPlan:
    ammo_tval: int | None
    plain_slot: str | None
    power_slot: str | None
    reservations: tuple[tuple[str, int], ...]
    target: int

    @property
    def kept_slots(self) -> frozenset[str]:
        return frozenset(slot for slot, count in self.reservations if count > 0)

    @property
    def carried_count(self) -> int:
        return sum(count for _slot, count in self.reservations)

    def reservation(self, slot: str) -> int:
        return next((count for candidate, count in self.reservations if candidate == slot), 0)


def is_plain_store_ammo(item) -> bool:
    """Match the game's emitted ``{average}`` pseudo-ID or known plain (+0,+0).

    Unknown average items carry ``pseudo_feeling == 'average'``.  Once known,
    ordinary store ammunition is non-ego/non-artifact and has zero hit/damage
    enchantment; these are explicit emitter fields, not a name heuristic.
    """
    return bool(
        item.pseudo_feeling == "average"
        or (
            item.known
            and not item.is_ego
            and not item.is_artifact
            and item.to_h == 0
            and item.to_d == 0
        )
    )


def ammo_carry_plan(snapshot, launcher, target: int) -> AmmoCarryPlan:
    if launcher is None or launcher.ammo_tval is None:
        return AmmoCarryPlan(None, None, None, (), target)
    matching = [
        item for item in snapshot.inventory
        if item.tval == launcher.ammo_tval and item.count > 0
    ]
    if not matching:
        return AmmoCarryPlan(launcher.ammo_tval, None, None, (), target)

    # The ranking is the same per-shot damage path used to compare launchers.
    highest = max(
        matching,
        key=lambda item: (launcher_average_damage(launcher, item), item.slot),
    )
    plains = [item for item in matching if is_plain_store_ammo(item)]
    plain = min(plains, key=lambda item: item.slot) if plains else None
    if plain is highest:
        reservations = ((plain.slot, min(plain.count, target)),)
        return AmmoCarryPlan(launcher.ammo_tval, plain.slot, plain.slot, reservations, target)

    power_count = min(highest.count, target)
    reservations = [(highest.slot, power_count)]
    if plain is not None and power_count < target:
        reservations.append((plain.slot, min(plain.count, target - power_count)))
    return AmmoCarryPlan(
        launcher.ammo_tval,
        None if plain is None else plain.slot,
        highest.slot,
        tuple(reservations),
        target,
    )


def power_ammo(snapshot, launcher):
    """The carried stack the plan ranks highest: the one a shot uses first."""
    slot = ammo_carry_plan(snapshot, launcher, 1).power_slot
    return next((item for item in snapshot.inventory if item.slot == slot), None)


def carried_average_damage(snapshot, launcher, rounds: int) -> float | None:
    """Count-weighted shot average over the plan's carried rounds (<= ``rounds``).

    Owner 2026-11-03 「持つ99発の平均で25」: the power and plain stacks the
    plan keeps, best rounds first.  None when no compatible round is carried.
    """
    plan = ammo_carry_plan(snapshot, launcher, rounds)
    stacks = {item.slot: item for item in snapshot.inventory}
    kept = [(stacks[slot], count) for slot, count in plan.reservations if count > 0]
    total = sum(count for _item, count in kept)
    if total <= 0:
        return None
    return sum(
        launcher_average_damage(launcher, item) * count for item, count in kept
    ) / total


# The item fields ammo_carry_plan and launcher_average_damage read.
PLAN_FIELDS = ("tval", "sval", "damage_dice_num", "damage_dice_sides", "to_h", "to_d",
               "known", "pseudo_feeling", "is_ego", "is_artifact")
BOUGHT_SLOT = "~bought"


def with_bought(snapshot, ware, count: int, merge_slot: str | None = None):
    """The pack (all the plan reads) after buying ``count`` of ``ware``.

    ``merge_slot``: the carried stack the game merges the ware into.
    """
    if merge_slot is not None:
        inventory = [replace(item, count=item.count + count) if item.slot == merge_slot
                     else item for item in snapshot.inventory]
    else:
        bought = SimpleNamespace(slot=BOUGHT_SLOT, count=count,
                                 **{name: getattr(ware, name) for name in PLAN_FIELDS})
        inventory = [*snapshot.inventory, bought]
    return SimpleNamespace(inventory=inventory)


def damage_ammo_purchase(snapshot, launcher, wares, minimum: float, rounds: int,
                         bought):
    """The ware whose purchase lifts ``carried_average_damage`` to ``minimum``.

    Quest force ``launcher.min_average_damage`` (owner 2026-11-02 「矢の購入で
    条件を満たせるときは買う」, 2026-11-03 「持つ99発の平均で25」).
    ``bought(ware)`` is the pack after buying the affordable quantity of
    ``ware``; the first ware in the plan's ranking whose pack reaches the
    minimum is chosen, else None.  An unknown ware's enchantment is unread
    and never qualifies.
    """
    if launcher is None or launcher.ammo_tval is None or minimum <= 0:
        return None
    current = carried_average_damage(snapshot, launcher, rounds)
    if current is not None and current >= minimum:
        return None
    ranked = sorted(
        (ware for ware in wares
         if ware.tval == launcher.ammo_tval and ware.count > 0 and ware.known),
        key=lambda ware: (launcher_average_damage(launcher, ware), ware.count),
        reverse=True,
    )
    return next(
        (ware for ware in ranked
         if (after := carried_average_damage(bought(ware), launcher, rounds)) is not None
         and after >= minimum),
        None,
    )
