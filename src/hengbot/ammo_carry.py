"""One shared carry plan for launcher ammunition."""

from dataclasses import dataclass

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
