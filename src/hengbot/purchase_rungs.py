"""Typed shared authority for town purchase eligibility and emission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PurchaseContext:
    snapshot: object


@dataclass(frozen=True)
class PurchaseMatch:
    rung_id: str
    category: str
    item_identity: tuple[object, ...]
    current: int | None = None
    target: int | None = None
    shortage: int | None = None
    rationale: str = ""


# What keeps an item a purchase rung bought once the rung stops firing.  Every
# rung of HengbotPolicy._purchase_rungs carries its entry (``retention``); the
# value is either a branch of the single retention authority
# (_retention_reservation_baseline_detail, policy_home.py), the equipment
# catalogue guard, CONSUMED_ON_USE (read or quaffed at once, nothing left to
# keep) or ALWAYS_LIVE (the rung never stops firing, so the live-rung guard of
# every sale/deposit/destroy selector keeps it).  A rung missing here has
# retention None, which the structural test rejects.
CONSUMED_ON_USE = "consumed-on-use"
ALWAYS_LIVE = "always-live-rung"
PURCHASE_RUNG_RETENTION: dict[str, str] = {
    # Read at once by _town_remove_curse_key.
    "curse:required": CONSUMED_ON_USE,
    # _home_full_equipment_surplus / _is_spare_lantern.
    "legacy:lantern": "equipment-catalogue",
    "legacy:oil": "supply-ledger:oil",
    "legacy:ration": "supply-ledger:food",
    "mining:digger": "mining:digging-tool",
    "mining:treasure-detection": "mining:detection",
    "mandatory:recall": "supply-ledger:recall",
    "mandatory:food": "supply-ledger:food",
    "mandatory:teleport": "supply-ledger:teleport",
    "mandatory:cure": "supply-ledger:cure",
    "mandatory:destruction": "destruction-gate",
    # Read by the identification errand that requested it.
    "identify:normal": CONSUMED_ON_USE,
    "identify:full": CONSUMED_ON_USE,
    # Quaffed by _stat_restore_quaff_key for the drained stat.
    "restore:<stat>": CONSUMED_ON_USE,
    # Active unconditionally (``lambda: True``).
    "restore:proactive": ALWAYS_LIVE,
    "experience:restore-life-levels": "experience-restore",
    "quest:carry": "carry-strategy",
    "quest:speed": "carry-strategy",
    "quest:healing": "carry-strategy",
    "tail:recall": "supply-ledger:recall",
    "tail:mana-food": "supply-ledger:mana-food",
    "tail:torch": "torch-carry",
    "tail:teleport": "supply-ledger:teleport",
    "tail:cure": "supply-ledger:cure",
    "tail:ammo": "ammo:carry-plan",
    "tail:identify-staff": "identify-staff-cap",
    "black-market:speed": "emergency-potion",
    "black-market:healing": "emergency-potion",
    "black-market:stone-to-mud": "utility:stone-to-mud",
    # Read at once by _town_remove_curse_key.
    "curse:normal": CONSUMED_ON_USE,
    "curse:star-reserve": "remove-curse:reserve",
    # Read at once (_observe_launcher_enchant).
    "tail:launcher-enchant": CONSUMED_ON_USE,
}


def purchase_rung_retention(rung_id: str) -> str | None:
    """Return the declared retention of ``rung_id`` (None when undeclared)."""
    if rung_id.startswith("restore:") and rung_id != "restore:proactive":
        rung_id = "restore:<stat>"
    return PURCHASE_RUNG_RETENTION.get(rung_id)


@dataclass(frozen=True)
class PurchaseRung:
    rung_id: str
    category: str
    matcher: Callable[[PurchaseContext, object], PurchaseMatch | None]
    retention: str | None = None

    def match(self, context: PurchaseContext, item: object) -> PurchaseMatch | None:
        return self.matcher(context, item)


@dataclass(frozen=True)
class PurchaseSelection:
    match: PurchaseMatch
    item: object
    supplier: int
    context: PurchaseContext
    quantity: int

