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
    # _carry_strategy_potion_target's heroism-carry (heroism_potion.carry_target).
    "tail:heroism": "heroism-carry",
    "tail:ammo": "ammo:carry-plan",
    "tail:identify-staff": "identify-staff-cap",
    # Worn or stored by the equipment comparison (ability_gear).
    "ability-gear:buy": "equipment-catalogue",
    # Worn by the Zul trip before it leaves for the global map (zul_trip).
    "zul:levitation": "zul-trip:levitation",
    "black-market:speed": "emergency-potion",
    "black-market:healing": "emergency-potion",
    "black-market:resistance": "resistance-potion",
    "black-market:stone-to-mud": "utility:stone-to-mud",
    # Worn or stored by the equipment comparison (bm_destruction_fund.PRIORITY_WARES).
    "priority-ware:telepathy": "equipment-catalogue",
    # The first Staff of Speed: the class-16 staff sequence keeps it until absorbed.
    "priority-ware:speed-staff": "me-staff:absorb",
    # A Wand of Rockets: the device table absorbs it after the Tower's recharge
    # (me_device_policy.awaits_absorption).
    "priority-ware:rocket": "me-staff:absorb",
    # Read at once by _town_remove_curse_key.
    "curse:normal": CONSUMED_ON_USE,
    "curse:star-reserve": "remove-curse:reserve",
    # Read at once (_observe_launcher_enchant).
    "tail:launcher-enchant": CONSUMED_ON_USE,
    # The class-16 staff sequence keeps it until absorbed (me_staff_sequence).
    "me-staff:buy": "me-staff:absorb",
    "me-device:policy": "me-staff:absorb",
}


# Owner 2026-11-22, equipment review Q8 (verbatim): 「買い物の表の段に最優先・必須・任意の区分を付け、
# お金が足りない時は区分の高い段から買う。今の順は区分の中で保つ」.  Every rung carries its tier
# (``PurchaseRung.tier``); a rung missing here has tier None, which the census test rejects.
TIER_PRIORITY = "priority"   # 最優先: the owner's 「最優先で買う」 wares
TIER_REQUIRED = "required"   # 必須: what a departure, an errand or a depth gate needs
TIER_OPTIONAL = "optional"   # 任意: the rest (from the gold above the departure resupply)
TIERS = (TIER_PRIORITY, TIER_REQUIRED, TIER_OPTIONAL)
TIER_LABELS = {TIER_PRIORITY: "最優先", TIER_REQUIRED: "必須", TIER_OPTIONAL: "任意"}
PURCHASE_RUNG_TIER: dict[str, str] = {
    # 必須 -- a required remove-curse, the new character's light and food, the mining set's kit,
    # the departure ledger, the 50F+ *Destruction* gate, the identification errand, a drained
    # stat, a taken quest's carry, the depth table's ability gear, the Zul trip's ring and the
    # Magic-Eater's staff sequence (each its own exclusive shopping list).
    "curse:required": TIER_REQUIRED,
    "legacy:lantern": TIER_REQUIRED,
    "legacy:oil": TIER_REQUIRED,
    "legacy:ration": TIER_REQUIRED,
    "mining:digger": TIER_REQUIRED,
    "mining:treasure-detection": TIER_REQUIRED,
    "mandatory:recall": TIER_REQUIRED,
    "mandatory:food": TIER_REQUIRED,
    "mandatory:teleport": TIER_REQUIRED,
    "mandatory:cure": TIER_REQUIRED,
    # The 50F+ gate (user 2026-09-23 「買えるなら買って潜る」, AGENTS.md's depth table).
    "mandatory:destruction": TIER_REQUIRED,
    "identify:normal": TIER_REQUIRED,
    "identify:full": TIER_REQUIRED,
    "restore:<stat>": TIER_REQUIRED,
    "quest:carry": TIER_REQUIRED,
    "quest:damage-ammo": TIER_REQUIRED,
    "quest:speed": TIER_REQUIRED,
    "quest:healing": TIER_REQUIRED,
    "tail:recall": TIER_REQUIRED,
    "tail:mana-food": TIER_REQUIRED,
    "tail:teleport": TIER_REQUIRED,
    "tail:cure": TIER_REQUIRED,
    # Owner 2026-11-04 「深さの条件に足りない耐性の装備が棚にあって買えるなら買う」.
    "ability-gear:buy": TIER_REQUIRED,
    # Owner 2026-11-07 「無ければ指輪を買う」.
    "zul:levitation": TIER_REQUIRED,
    "me-staff:buy": TIER_REQUIRED,
    # 最優先 -- owner 2026-11-07/11-15 「破壊の杖は最優先で購入」, 11-15 「完全なテレパシーを闇市で
    # 最優先で買う」, 11-21 「スピードの杖の一本目は最優先にする」, 11-22 「ロケットの魔法棒の購入優先度を
    # 最優先に」 (bm_destruction_fund.PRIORITY_WARES).
    "black-market:destruction": TIER_PRIORITY,
    "priority-ware:telepathy": TIER_PRIORITY,
    "priority-ware:speed-staff": TIER_PRIORITY,
    "priority-ware:rocket": TIER_PRIORITY,
    # 任意 -- the stock above the departure's needs.
    "restore:proactive": TIER_OPTIONAL,
    "experience:restore-life-levels": TIER_OPTIONAL,
    "tail:torch": TIER_OPTIONAL,
    "tail:heroism": TIER_OPTIONAL,
    "tail:angband-finale": TIER_OPTIONAL,
    "tail:ammo": TIER_OPTIONAL,
    "tail:identify-staff": TIER_OPTIONAL,
    "black-market:speed": TIER_OPTIONAL,
    "black-market:healing": TIER_OPTIONAL,
    "black-market:resistance": TIER_OPTIONAL,
    "black-market:stone-to-mud": TIER_OPTIONAL,
    "me-device:policy": TIER_OPTIONAL,
    "curse:normal": TIER_OPTIONAL,
    "curse:star-reserve": TIER_OPTIONAL,
    "tail:launcher-enchant": TIER_OPTIONAL,
}


def purchase_rung_tier(rung_id: str) -> str | None:
    """Return the declared tier of ``rung_id`` (None when undeclared)."""
    if rung_id.startswith("restore:") and rung_id != "restore:proactive":
        rung_id = "restore:<stat>"
    return PURCHASE_RUNG_TIER.get(rung_id)


def tier_rank(tier: str | None) -> int:
    """0 for 最優先, 1 for 必須, 2 for 任意 (an undeclared tier ranks as 任意)."""
    return TIERS.index(tier) if tier in TIERS else len(TIERS) - 1


def short_money_choice(picks, gold: int):
    """Owner Q8: the ware to buy among ``picks`` -- ``(ware, cost, tier)`` in today's order.

    With the gold for all of them, today's first pick.  Short of it, the first pick of the
    highest tier (today's order within the tier).  None without picks."""
    if not picks:
        return None
    if sum(cost for _ware, cost, _tier in picks) <= gold:
        return picks[0][0]
    best = min(tier_rank(tier) for _ware, _cost, tier in picks)
    return next(ware for ware, _cost, tier in picks if tier_rank(tier) == best)


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
    tier: str | None = None

    def match(self, context: PurchaseContext, item: object) -> PurchaseMatch | None:
        return self.matcher(context, item)


@dataclass(frozen=True)
class PurchaseSelection:
    match: PurchaseMatch
    item: object
    supplier: int
    context: PurchaseContext
    quantity: int

