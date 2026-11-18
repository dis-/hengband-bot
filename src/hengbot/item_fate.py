"""What may leave the character's hands: the one disposal answer (owner 2026-11-04).

Owner, on the ranking: per slot, by sale value, rank 21+ may be sold any time,
ranks 11-20 when room is needed, the top 10 are kept, artifacts are not sold.
When only the top 10 are left: 「消耗品や不用品などを整理。装備は売らない。」
When selling cannot get under the weight limit: 「基本的には上限を超えない設定なので、
停止して調査」, so the named weight stop stays.

Every sale, Home take and destroy path asks here: ``gear_tier`` for the ranking,
``held`` and ``stock_reserved`` for the gates all of them share, and the order
functions for what goes first.  The consumable and Magic-Eater device tables
keep their own modules.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from hengbot import item_use_route, spare_gear, town_pack_budget
from hengbot.baseitem_knowledge import item_base_cost
from hengbot.item_reservation import decision_memo, item_available
from hengbot.model import SV_STAFF_IDENTIFY, TVAL_ROD, TVAL_STAFF, TVAL_WAND
from hengbot.store_sale import known_sale_value

KEEP, ROOM, ANY = "keep", "room", "any"
KEPT_RANKS = 10
ROOM_RANKS = 20
# Home wares one town stay takes out and sells with no pressure on the Home.
SWEEP_LIMIT_PER_STAY = 3

SLOT_BY_TVAL = {
    19: "launcher", 20: "digger", 21: "melee", 22: "melee", 23: "melee",
    30: "feet", 31: "arms", 32: "head", 33: "head", 34: "shield", 35: "cloak",
    36: "body", 37: "body", 38: "body", 40: "neck", 45: "ring",
}


def sale_value(policy: Any, item: Any) -> int:
    """The known per-item value every ranking and order compares."""
    return max(0, known_sale_value(item, item_base_cost(item, policy._baseitem_costs)) or 0)


def _ranks(policy: Any, snapshot: Any) -> dict:
    """Signature -> best rank in its slot, over worn, pack and Home rows."""
    rows: dict[str, list] = {}
    for item in (*snapshot.equipment, *snapshot.inventory, *policy._home_knowledge_items):
        slot = SLOT_BY_TVAL.get(item.tval)
        if slot is not None and item.known and not item.is_artifact and getattr(item, "slot", None) != "home-surplus":
            rows.setdefault(slot, []).append(
                (-sale_value(policy, item), policy._item_signature(item)))
    ranks: dict = {}
    for row in rows.values():
        for position, (_, signature) in enumerate(sorted(row), 1):
            ranks.setdefault(signature, position)
    return ranks


def gear_rank(policy: Any, snapshot: Any, item: Any) -> int | None:
    """The piece's rank in its slot by sale value; None when unranked."""
    ranks = decision_memo(policy, "gear-ranks", snapshot, None, lambda: _ranks(policy, snapshot))
    return ranks.get(policy._item_signature(item))


def gear_tier(policy: Any, snapshot: Any, item: Any) -> str:
    """KEEP, ROOM (11-20) or ANY (21+); anything unranked is kept.

    Without a current Home census the rank is unknown, so nothing is released,
    except the ware the relief already chose from a census and has taken out.
    """
    if item.is_artifact or not item.known or SLOT_BY_TVAL.get(item.tval) is None:
        return KEEP
    from hengbot import bm_destruction_fund
    if bm_destruction_fund.releases(policy, snapshot, item):
        # Owner 2026-11-07: Home's spare weapons and body armour, ranks 2-10
        # too, pay for the Black Market's Staff of *Destruction*.
        return ANY
    if not policy._home_knowledge_current:
        relief = policy._home_full_relief or {}
        return ROOM if relief.get("rank_released") == policy._item_signature(item) else KEEP
    rank = gear_rank(policy, snapshot, item)
    if rank is None:
        return KEEP
    return KEEP if rank <= KEPT_RANKS else ROOM if rank <= ROOM_RANKS else ANY


def gear_surplus(policy: Any, snapshot: Any, item: Any) -> bool:
    """May this piece go when room or weight relief is needed?  All classes."""
    if not item.is_equipment or item.is_ammo:
        # Ammunition has its own quantity/launcher reservation, applied by callers.
        return True
    if policy._sale_retains_digging_tool(snapshot, item):
        return False
    if (item.is_torch and item.known and item.fuel <= 0) or policy._is_spare_lantern(snapshot, item):
        return True
    if gear_tier(policy, snapshot, item) == KEEP:
        return False
    return item.is_digging_tool or spare_gear.released(policy, snapshot, item)


def held(policy: Any, snapshot: Any, item: Any, owner: str, sink: str, *, known: bool = True) -> bool:
    """The gate every disposal path shares; ``known`` also asks for identification."""
    return bool(
        not item_available(policy, snapshot, item, owner, sink)
        or item.is_bounty
        or policy._home_disposal.decision(policy._item_signature(item)) == "keep"
        or (known and (not item.known or policy._disposal_protected_by_identification(item))))


def empty_identify_staff(item: Any) -> bool:
    return (item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
            and max(item.charges, item.pval) == 0)


def stock_reserved(policy: Any, snapshot: Any, probe: Any, item: Any) -> bool:
    """Retention, ownership and the purchase ladder claim this stock."""
    return bool(
        policy._retention_reservation(probe, item) > 0
        or policy._home_full_equipment_reserved(snapshot, item)
        or (policy._item_matches_purchase_rung(probe, item) and not empty_identify_staff(item)))


HOME_STOCK_SLOT = "home-surplus"
# Home keeps one refill of the pack's carry target (AMMO_CARRY_TARGET) for the worn launcher.
HOME_AMMO_KEEP = 99


def _home_stock(item: Any) -> bool:
    """A Home stack as the full-Home relief asks about it (``_home_full_sale_candidate``)."""
    return getattr(item, "slot", None) == HOME_STOCK_SLOT


TVAL_AMULET = 40
TVAL_RING = 45
JEWELRY_SLOTS = {TVAL_AMULET: 1, TVAL_RING: 2}   # worn slots of the kind (INVEN_NECK, two rings)

# The device kinds some rule of the bot uses (src/hengbot, sv-*-types.h).  A device kind
# outside this table no rule zaps, aims or uses for a class other than the Magic-Eater
# (whose absorption is item_use_route's): owner 2026-11-19 「使わない魔法道具は売る」.
DEVICE_USES = {
    (TVAL_STAFF, 4): "teleport_follower / threat_escape (Teleportation)",
    (TVAL_STAFF, 5): "identification (Identify)",
    (TVAL_STAFF, 9): "area_mapping (Mapping)",
    (TVAL_STAFF, 10): "policy_fundraising (Detect Gold)",
    (TVAL_STAFF, 12): "quest25_battle (Detect Traps)",
    (TVAL_STAFF, 13): "quest_target_search (Detect Doors)",
    (TVAL_STAFF, 15): "kill_all_patrol / quest_target_search (Detect Evil)",
    (TVAL_STAFF, 18): "arena_odds (Healing)",
    (TVAL_STAFF, 22): "speed_dose (Speed)",
    (TVAL_STAFF, 29): "destruction_means (*Destruction*)",
    (TVAL_WAND, 3): "teleport_away_carry (Teleport Other)",
    (TVAL_WAND, 4): "sealed_loot / quest25_battle (Disarming)",
    (TVAL_WAND, 5): "sealed_loot / quest25_battle (Trap/Door Destruction)",
    (TVAL_WAND, 6): "stone_to_mud_carry (Stone to Mud)",
    (TVAL_ROD, 1): "quest_target_search (Door/Stair Location)",
    (TVAL_ROD, 2): "identification (Identify)",
    (TVAL_ROD, 3): "supply-ledger:recall-rod (Recall)",
    (TVAL_ROD, 5): "area_mapping (Detection: mapping)",
    (TVAL_ROD, 6): "kill_all_patrol / quest_target_search (Detection)",
    (TVAL_ROD, 9): "arena_odds (Healing)",
    (TVAL_ROD, 13): "teleport_away_carry / teleport_follower (Teleport Other)",
    (TVAL_ROD, 14): "sealed_loot / quest25_battle (Disarming)",
}

# object-enchant/tr-types.h: what a piece of jewelry gives that no rule reads (the
# IGNORE_* elements, display flags, ACTIVATE: the bot activates no jewelry).
_COSMETIC_FLAGS = frozenset({73, 74, 84, 85, 86, 87, 88, 116, 117})
# The pval abilities (TR_STR .. TR_BLOWS).
_PVAL_FLAGS = frozenset(range(0, 14)) - {7}
# A drawback a dominating piece must not add (NO_TELE, NO_MAGIC, curses, drains, calls).
_DRAWBACK_FLAGS = frozenset({68, 69, 71, 89, 90, 91, *range(118, 138)})
# TR flag -> player.ability_sources key (bot-json-output.cpp
# make_bot_player_ability_sources_json).
_ABILITY_KEY = {
    45: "reflect", 46: "free_action", 47: "hold_exp",
    48: "resist_acid", 49: "resist_elec", 50: "resist_fire", 51: "resist_cold",
    52: "resist_pois", 53: "resist_fear", 54: "resist_lite", 55: "resist_dark",
    56: "resist_blind", 57: "resist_conf", 58: "resist_sound", 59: "resist_shard",
    60: "resist_neth", 61: "resist_nexus", 62: "resist_chaos", 63: "resist_disen",
    72: "warning", 76: "levitation", 78: "see_invisible", 79: "telepathy",
    80: "slow_digest", 81: "regenerate",
    32: "sustain_str", 33: "sustain_int", 34: "sustain_wis",
    35: "sustain_dex", 36: "sustain_con", 37: "sustain_chr",
}


def _flags_complete(item: Any) -> bool:
    """Every ability of the piece is shown: *identified*, or a plain known kind."""
    return bool(item.known and (item.fully_known or not (item.is_ego or item.is_artifact)))


def _abilities(item: Any) -> frozenset:
    return frozenset(item.known_flags) - _COSMETIC_FLAGS


def _unused_book(policy: Any, item: Any) -> bool:
    """A third or fourth realm book of no realm the character sheet shows (owner 2026-11-19
    「高位魔法書→自宅に溜め込まずに売る」).  Unread realms sell nothing."""
    own = getattr(policy, "_own_book_tvals", None)
    return bool(own is not None and policy._is_high_value_book(item) and item.tval not in own)


def _unused_device(policy: Any, snapshot: Any, item: Any) -> bool:
    """A Home device of a kind no rule uses (``DEVICE_USES``), owner 2026-11-19.

    The Magic-Eater keeps what its absorption still raises (item_use_route's
    ``magic-eater-absorbs``, below the 99 cap).  A mana-eating character keeps the Home's
    devices while its carried food is short (policy_supply ``_mana_food_device_target``).
    """
    from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
    from hengbot.policy_constants import FOOD_TYPE_MANA
    if (item.tval not in (TVAL_STAFF, TVAL_WAND, TVAL_ROD) or not item.known
            or not getattr(item, "aware", True) or item.is_artifact
            or (item.tval, item.sval) in DEVICE_USES):
        return False
    if (snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
            and item_use_route.has_use(policy, snapshot, item)):
        return False
    if (snapshot.player.food_type == FOOD_TYPE_MANA and item.tval != TVAL_ROD
            and policy._count_mana_food_devices(snapshot) < policy._mana_food_device_target(snapshot)):
        return False
    return True


def _innate_covered(snapshot: Any, item: Any) -> bool:
    """Jewelry whose every ability the character holds permanently (owner 2026-11-19
    「ゾンビなら絶対装備しないので売って良い」: the zombie warrior's rings of Resist Poison and
    Resist Nether).  No bonus, no unread ability; not while a mimic form shows its race."""
    if (item.tval not in JEWELRY_SLOTS or item.is_artifact or item.is_cursed
            or not _flags_complete(item) or snapshot.player.mimic_form
            or item.pval or item.to_a or item.to_h or item.to_d):
        return False
    abilities = _abilities(item)
    sources = snapshot.player.ability_sources
    return bool(abilities) and all(
        flag in _ABILITY_KEY and "permanent" in sources.get(_ABILITY_KEY[flag], ())
        for flag in abilities)


def _at_most(item: Any, other: Any) -> bool:
    """``other`` gives every ability and bonus of ``item``, adding no drawback."""
    mine, theirs = _abilities(item), _abilities(other)
    if not mine <= theirs or (theirs - mine) & _DRAWBACK_FLAGS:
        return False
    if item.pval > 0 and (mine & _PVAL_FLAGS) and other.pval < item.pval:
        return False
    return item.to_a <= other.to_a and item.to_h <= other.to_h and item.to_d <= other.to_d


def _dominated(policy: Any, snapshot: Any, item: Any) -> bool:
    """Jewelry the kept pieces of its kind outdo (owner 2026-11-19 「耐性のアミュレットの下位互換」).

    A piece another of its kind gives every ability and bonus of (``_at_most``; between
    equals the lesser signature is the other) is dominated.  The pieces dominated by fewer
    than the kind's worn slots are kept; a piece goes when at least that many kept pieces
    (worn, carried or on the Home shelf) dominate it.  Artifacts and pieces whose
    abilities are not all shown are never sold on this ground, nor counted as kept.
    """
    if (item.tval not in JEWELRY_SLOTS or item.is_artifact or item.is_cursed
            or not _flags_complete(item)):
        return False
    return policy._item_signature(item) in decision_memo(
        policy, "dominated-jewelry", snapshot, item.tval,
        lambda: _dominated_signatures(policy, snapshot, item.tval))


def _dominated_signatures(policy: Any, snapshot: Any, tval: int) -> frozenset:
    """The signatures of ``tval`` jewelry ``_dominated`` sells, one census per decision."""
    slots = JEWELRY_SLOTS[tval]
    pieces: dict = {}
    for piece in (*snapshot.equipment, *snapshot.inventory, *policy._home_knowledge_items):
        if (piece.tval == tval and not piece.is_cursed and _flags_complete(piece)
                and not _innate_covered(snapshot, piece)):
            key = policy._item_signature(piece)
            pieces[key] = (piece, pieces.get(key, (piece, 0))[1] + max(1, piece.count))

    def outdoes(other_key, key) -> bool:
        other, piece = pieces[other_key][0], pieces[key][0]
        if other_key == key or not _at_most(piece, other):
            return False
        return not _at_most(other, piece) or other_key < key

    dominators = {key: [other for other in pieces if outdoes(other, key)] for key in pieces}
    kept = {key for key, others in dominators.items()
            if sum(pieces[other][1] for other in others) < slots}
    return frozenset(
        key for key, others in dominators.items()
        if not pieces[key][0].is_artifact
        and sum(pieces[other][1] for other in others if other in kept) >= slots)


def _surplus_digger(policy: Any, snapshot: Any, item: Any) -> bool:
    """A digging tool beside the one the character keeps (owner 2026-11-17: one digger).

    The kept tool is the best by ``_digging_tool_sale_quality`` (the digging bonus first: the
    Q2 breach and the mining kit read the bonus) over the worn, carried and Home tools, then
    the higher sale value and the signature, so a take from the shelf does not change which one
    is kept.  Every tool of another signature is surplus (a stack of the kept signature stays).
    """
    if not item.is_digging_tool or item.is_artifact or not item.known:
        return False
    tools = [tool for tool in (*snapshot.equipment, *snapshot.inventory,
                               *policy._home_knowledge_items)
             if tool.is_digging_tool and tool.known
             and not policy._equip_blocked_by_identification(tool)]
    if not tools:
        return False
    kept = max(tools, key=lambda tool: (policy._digging_tool_sale_quality(tool),
                                        sale_value(policy, tool), policy._item_signature(tool)))
    return policy._item_signature(kept) != policy._item_signature(item)


def _surplus_ammo(policy: Any, snapshot: Any, item: Any) -> bool:
    """A Home stack of the worn launcher's ammunition past ``HOME_AMMO_KEEP`` rounds, best kept.

    The rounds are ranked by the carry plan's per-shot damage (launcher_average_damage); stacks
    of one signature are interchangeable, so a stack is surplus when that many of its signature
    lie past the kept rounds.
    """
    from hengbot.launcher_damage import launcher_average_damage
    launcher = policy._equipped_launcher(snapshot)
    if (not _home_stock(item) or not item.is_ammo or item.is_artifact or not item.known
            or launcher is None or item.tval != launcher.ammo_tval):
        return False
    totals: dict = {}
    for stock in policy._home_knowledge_items:
        if stock.tval == launcher.ammo_tval and stock.count > 0:
            signature = policy._item_signature(stock)
            damage, count = totals.get(signature, (launcher_average_damage(launcher, stock), 0))
            totals[signature] = (damage, count + stock.count)
    left, outside = HOME_AMMO_KEEP, {}
    for signature, (_, count) in sorted(totals.items(), key=lambda row: (-row[1][0], row[0])):
        kept = min(count, left)
        left -= kept
        outside[signature] = count - kept
    return outside.get(policy._item_signature(item), 0) >= item.count


def clearly_useless(policy: Any, snapshot: Any, item: Any, *, carried: bool = False) -> str | None:
    """The class of a stack that only takes a slot, or None (owner 2026-11-17).

    Owner, verbatim: 「自宅は明確に無駄な採掘道具や矢を売却すれば空きを作れる」 -- n1-a life-530's
    Home stood at 239/240 holding a dozen digging tools and some forty stacks of 99 crossbow bolts
    while the full-Home relief sold spikes and a Lance.  The full-Home relief sells these first
    (``relief_order``), past the rank keep, the digger standing retention and the ammunition
    reservations (policy_home ``_home_full_sale_candidate``):

    * ``unused-ammo``: the junk class (policy_helpers ``_junk_class``, ammunition no worn
      launcher fires);
    * ``surplus-digger``: ``_surplus_digger``;
    * ``surplus-ammo``: ``_surplus_ammo``.

    Owner 2026-11-19 「不要物の判定をもう少し頑張って。」: four more classes of Home stock, sold
    whether or not the Home is full (the Home junk sweep, ``sweep_ware``, takes them too):

    * ``unused-book``: ``_unused_book`` (「高位魔法書→自宅に溜め込まずに売る」);
    * ``unused-device``: ``_unused_device`` (「使わない魔法道具は売る」);
    * ``innate-covered``: ``_innate_covered`` (「ゾンビなら絶対装備しないので売って良い」);
    * ``dominated``: ``_dominated`` (「耐性のアミュレットの下位互換」).

    They judge what the Home hoards: ``carried`` (a pack stack the relief probes with the Home
    slot, ``_home_full_sale_candidate``) keeps its own rules.
    """
    if _home_stock(item) and not carried and not item.is_artifact:
        if _unused_book(policy, item):
            return "unused-book"
        if _unused_device(policy, snapshot, item):
            return "unused-device"
        if _innate_covered(snapshot, item):
            return "innate-covered"
        if _dominated(policy, snapshot, item):
            return "dominated"
    relief = getattr(policy, "_home_full_relief", None)
    if relief is None or relief.get("sweep"):
        # Only a full Home's relief (a deposit refused or met by a full Home) makes room.
        return None
    if item.is_ammo and policy._junk_class(snapshot, item) == "unused-ammo":
        return "unused-ammo"
    if _surplus_digger(policy, snapshot, item):
        return "surplus-digger"
    if _surplus_ammo(policy, snapshot, item):
        return "surplus-ammo"
    return None


def relief_ware(policy: Any, snapshot: Any) -> Any:
    """The carried stack the full-Home relief's sale names, or None.

    The stack of the recorded name first: a take of the surplus {@1} bolts sits beside the
    carried {@0} bolts of the same ``_sale_item_identity``, and only the taken stack is the
    ware (n1-a life-530 2026-11-18 03:06).  Without it the first stack of that identity: the
    sale's in-store ``@1`` tag renames the ware (n1-a life-530 2026-11-18 01:28
    town:blocked:stage-deadline:sell).
    """
    relief = getattr(policy, "_home_full_relief", None) or {}
    sale = relief.get("sale")
    if sale is None:
        return None
    exact = policy._first_item(snapshot, lambda item: policy._item_signature(item) == sale[0])
    if exact is not None:
        return exact
    identity = policy._sale_signature_identity(sale[0])
    return policy._first_item(snapshot, lambda item: policy._sale_item_identity(item) == identity)


def relief_useless(policy: Any, snapshot: Any, item: Any) -> bool:
    """The relief's current sale ware, chosen as clearly useless, now off the Home shelf.

    Taken out, the ware is a pack stack: the carry plan would rank the bolts it judged past the
    Home keep as the power stack, and the standing digger retention would count the tool again.
    The relief's choice holds until its sale is observed (policy_home ``relief["useless"]``).
    The ware is the stack ``relief_ware`` names.
    """
    relief = getattr(policy, "_home_full_relief", None) or {}
    sale = relief.get("sale")
    if _home_stock(item) or sale is None or relief.get("useless") != sale[0]:
        return False
    ware = relief_ware(policy, snapshot)
    return (ware is not None and ware.slot == item.slot
            and policy._item_signature(ware) == policy._item_signature(item))


def relief_round_trip(policy: Any, item: Any) -> bool:
    """The full-Home relief's shelf sale ware, not yet taken out.

    The clearly useless ware, or any sale ware the relief chose for a pack at the
    reserve floor (policy_home ``relief["round_trip"]``; n1-a life-531 2026-11-19).
    The relief takes it out of the Home only to sell it at the next store
    (``town_pack_budget.round_trip_fits``); once taken (``withdrawn``) it is a pack
    stack like any other.
    """
    relief = getattr(policy, "_home_full_relief", None) or {}
    sale = relief.get("sale")
    signature = policy._item_signature(item)
    return (not relief.get("withdrawn")
            and signature in (relief.get("useless"), relief.get("round_trip"))
            and (sale is None or sale[0] == signature))


def relief_order(policy: Any, snapshot: Any, item: Any, *, carried: bool = False) -> tuple:
    """Clearly useless stock (the 11-17 classes before the 11-19 ones), rank 21+, then 11-20,
    then surplus consumables; cheapest first."""
    useless = clearly_useless(policy, snapshot, item, carried=carried)
    if useless is not None:
        group = -2 if useless in ("unused-ammo", "surplus-digger", "surplus-ammo") else -1
    elif not item.is_equipment or item.is_ammo:
        group = 2
    else:
        group = 0 if gear_tier(policy, snapshot, item) == ANY else 1
    return (group, sale_value(policy, item), policy._item_signature(item))


def weight_relief_order(policy: Any, snapshot: Any, candidates: list) -> list:
    """The overweight rows: gear first when it alone clears the excess.

    ``candidates`` are the relief's cheapest-first (value, signature, item,
    count, stores) rows; each group keeps that order.
    """
    limit = policy._inventory_weight_limit(snapshot)
    gear = [entry for entry in candidates
            if entry[2].is_equipment and not entry[2].is_ammo]
    if limit is None or sum(entry[2].weight * entry[3] for entry in gear) < (
            policy._inventory_weight(snapshot) - limit):
        return candidates
    return [*gear, *(entry for entry in candidates if entry not in gear)]


def home_take_blocked(snapshot: Any) -> bool:
    """No one-slot Home take is admitted: the pack must shrink first."""
    return not town_pack_budget.permits(snapshot, 1)


def can_identify_now(policy: Any, snapshot: Any, item: Any) -> bool:
    """10-31 「鑑定待ちの装備は預ける」: a take for identification needs a source now."""
    from hengbot.me_staff_sequence import identify_power_command
    full = bool(item.known)
    return (identify_power_command(policy, snapshot, replace(item, slot="a"), full=full) is not None
            or policy._carried_identification_source(snapshot, full=full) is not None)


def ranked_gear_saleable(policy: Any, snapshot: Any, item: Any) -> bool:
    """The owner's ranking applied to a store sale of ranked gear.

    Rank 21+ goes any time, 11-20 only when room is needed, the top 10 and
    anything unranked (an artifact, an unidentified piece) stay.  n1-b life-322
    2026-11-06: an unidentified Light Crossbow from Q14 went to the Weapon Smith
    for $57 as "spare" because the optimizer cannot choose what it cannot judge.
    Digging tools keep their own retention (``_sale_retains_digging_tool``);
    what the ranking does not cover (lights, consumables) is not asked here.
    """
    if not item.is_equipment or item.is_ammo or item.is_digging_tool:
        return True
    if SLOT_BY_TVAL.get(item.tval) is None:
        return True
    tier = gear_tier(policy, snapshot, item)
    if tier == ROOM:
        return policy._town_pack_space_shortage(snapshot) or policy._home_is_full(snapshot)
    return tier == ANY


def sold_not_shelved(policy: Any, snapshot: Any, item: Any) -> bool:
    """Rank 21+ in the pack goes to its buyer, not to Home and out again."""
    return bool(item.is_equipment and not item.is_ammo
                and gear_tier(policy, snapshot, item) == ANY
                and gear_surplus(policy, snapshot, item)
                and not held(policy, snapshot, item, "shop-sell", "sell")
                and policy._town_organization_sale_store(snapshot, item) is not None)


def sweep_ware(policy: Any, snapshot: Any, stock: Any) -> Any:
    """The cheapest rank 21+ Home row with a buyer, the pack able to carry it.

    While the Black Market's *Destruction* staff is short of gold, its fund's
    next piece first (bm_destruction_fund, owner 2026-11-07).  Under the fundraising line
    Home's cash wares go first, most valuable first (home_cash_sale, owner 2026-11-18).
    """
    from hengbot import bm_destruction_fund, home_cash_sale
    cash = home_cash_sale.sweep_ware(policy, snapshot, stock)
    if cash is not None:
        return cash
    for signature in bm_destruction_fund.plan(policy, snapshot):
        ware = next(((result, item) for item in stock
                     if policy._item_signature(item) == signature
                     and (result := policy._home_full_sale_candidate(snapshot, item)) is not None
                     and policy._can_add_item_without_overweight(snapshot, item)), None)
        if ware is not None:
            return ware
    rows = [(result, item) for item in stock
            if ((SLOT_BY_TVAL.get(item.tval) is not None
                 and gear_tier(policy, snapshot, item) == ANY)
                # Owner 2026-11-13: Home kinds no consumer uses (item_use_route).
                or item_use_route.surplus(policy, snapshot, item)
                # Owner 2026-11-19: clearly useless stock is not hoarded (``clearly_useless``).
                or clearly_useless(policy, snapshot, replace(item, slot=HOME_STOCK_SLOT)))
            and (result := policy._home_full_sale_candidate(snapshot, item)) is not None
            and policy._can_add_item_without_overweight(snapshot, item)]
    # Clearly useless stock first, then the cheapest.
    return min(rows, key=lambda entry: (clearly_useless(policy, snapshot, entry[0][0]) is None,
                                        sale_value(policy, entry[0][0]))) if rows else None


def sweep_identify_ware(policy: Any, snapshot: Any, stock: Any) -> Any:
    """The first shelved unaware potion or scroll a carried means identifies now.

    Owner 2026-11-15 「自宅に未鑑定の薬と巻物を溜め込む問題」→「鑑定の手段で
    調べる」: the Home junk sweep takes the stack, the carried means (the
    Magic-Eater's absorbed Identify, the Identify staff or rod, an Identify
    scroll: ``_unaware_consumable_identifiable_now``) identifies it, and the now-known kind is
    kept, sold or destroyed by the existing rules.  With no means the stack
    stays on the shelf.  ``(candidate, item)`` as the relief's identify list
    holds it, or None.
    """
    for item in stock:
        if not policy._unaware_consumable_awaits_identification(item):
            continue
        candidate = policy._home_full_discard_candidate(snapshot, item, identify=True)
        if (candidate is not None
                and policy._can_add_item_without_overweight(snapshot, item)
                and policy._unaware_consumable_identifiable_now(snapshot, candidate)):
            return candidate, item
    return None
