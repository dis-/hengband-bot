"""Every item kind the bot keeps has a declared use route (owner 2026-11-13).

Owner (verbatim): 「n1-cの現状を見ると、挑まないQ25用のアイテム、使用経路のない薬や巻物、魔道具術師
では不要な解呪、捨てると決めた岩石溶解を持っている。アイテムが整理できていない。」

One rule, one table.  ``ROUTES`` names, per item kind, the owner that uses it (``consumer``) and
the condition under which it uses it for THIS character (``when``, a ``WHEN`` predicate: class,
absorbed powers, the quest plan being prepared, fear resistance, ...).  An in-scope item with no
live route is surplus:

 * retention keeps none of it (policy_home ``_retention_reservation_detail``), so no stale
   reservation (a Q25 carry, the *Remove Curse* reserve, the Stone to Mud keep-all) holds it;
 * it is never shelved at Home (``_home_deposit_candidate``) -- it is sold at a store that buys
   it (the town organization sale, ``sale_candidate``; a Home copy by the Home sweep,
   item_fate.sweep_ware), and destroyed when no store buys it (policy_helpers._junk_class's
   ``no-use-route`` class: ``disposable``);
 * no purchase rung buys it back (policy_shop._matching_live_purchase_rungs); the departure
   ledger's own requirement buys only kinds whose row holds for every character (the lint).

Scope (``in_scope``): identified potions and scrolls of every class, and identified wands,
staffs and rods of the Magic-Eater (class 16), whose device table (me_device_policy) says what
each device is for.  Everything else is kept by its own authority (``DELEGATED``): equipment by
the loadout and item_fate's ranking, ammunition by the carry plan, lights and oil by the light
rules, food by the supply ledger, books by the book rules, another class's devices by the device
sale rules.

``OWNER_PENDING`` names the kinds the owner's tables tell the bot to keep (consumable_policy.json
「購入する」/「持ち歩く」/「自宅に片付ける」/「使う」) for which no consumer exists yet: they stay as today
until the owner answers the question named there (implement the use, or let them go).  An
absorbed power that replaces an item (me_capability.REPLACES, use NEED) outranks the table: the
item is surplus whatever the table says (「魔道具術師では不要な解呪」).

The town rebuild's single departure table answers "needed" (how many to carry for the next
departure); this module answers "has a use".  A kept count is ``min(needed, has a use ? needed
: 0)``: the departure table reads ``has_use`` before it counts a kind, and a row here never
counts anything.

Adding an item kind or a consumer is one ``Route`` row (a new condition is one ``WHEN``
predicate); tests/test_item_use_route_lint.py fails while a kind some owner keeps has no row.
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import consumable_policy, heroism_potion, me_capability, me_device_policy, quest_optional_carry
from hengbot.item_reservation import decision_memo
from hengbot.magic_eater_devices import (
    PLAYER_CLASS_MAGIC_EATER, SV_WAND_WONDER, drained_staple_food, is_staple_food, staple_food,
)
from hengbot.model import (
    SV_POTION_CURE_CRITICAL, SV_POTION_ENLIGHTENMENT, SV_POTION_HEALING,
    SV_POTION_HEROISM, SV_POTION_LIFE, SV_POTION_RESISTANCE, SV_POTION_RESIST_COLD,
    SV_POTION_RESTORE_EXP, SV_POTION_SPEED,
    SV_POTION_STAR_HEALING, SV_ROD_RECALL, SV_SCROLL_DETECT_TREASURE, SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
    SV_SCROLL_ENCHANT_WEAPON_TO_HIT, SV_SCROLL_IDENTIFY, SV_SCROLL_LIGHT, SV_SCROLL_MAPPING,
    SV_SCROLL_PHASE_DOOR, SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_DESTRUCTION, SV_SCROLL_STAR_IDENTIFY,
    SV_SCROLL_STAR_REMOVE_CURSE, SV_SCROLL_TELEPORT, SV_SCROLL_WORD_OF_RECALL, SV_STAFF_DESTRUCTION,
    SV_WAND_STONE_TO_MUD, RESTORE_POTION_SVAL_BY_STAT,
    TVAL_POTION, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND,
)
from hengbot.policy_constants import FOOD_TYPE_MANA

SV_POTION_RESIST_HEAT = 30        # sv-potion-types.h (oneshot_breath.DRINKS)
SV_SCROLL_TELEPORT_LEVEL = 10     # sv-scroll-types.h (threat_escape)
DEVICE_TVALS = frozenset({TVAL_WAND, TVAL_STAFF, TVAL_ROD})
ANY = None                        # every sval of the row's tval


@dataclass(frozen=True)
class Route:
    tval: int
    sval: int | None
    consumer: str     # the owner that uses the kind (module / function)
    when: str = "always"


# -- the conditions ---------------------------------------------------------------

def _always(policy, snapshot, item) -> bool:
    return True


def _not_replaced(policy, snapshot, item) -> bool:
    """No absorbed power stands in for the item (me_capability.REPLACES, NEED)."""
    return not me_capability.replaced_by_absorbed(policy, snapshot, item, me_capability.NEED)


def _prepared_strategy(policy, snapshot):
    """The quest plan the town prepares or the floor runs (the retention's own reading)."""
    return decision_memo(policy, "item-use-route-strategy", snapshot, None, lambda: (
        policy._carry_procurement_strategy(snapshot, cache_fixed_quest_head=False)
        or policy._quest_strategy_for_errand_or_floor(snapshot)))


def _quest_carry(policy, snapshot, item) -> bool:
    """The prepared quest's required_force names the kind (policy_quest carry target)."""
    strategy = _prepared_strategy(policy, snapshot)
    return (strategy is not None and policy._quest_carry_target_for_item(
        snapshot, item, strategy.required_force) is not None)


def _quest_optional_carry(policy, snapshot, item) -> bool:
    """A quest still ahead names it as its optional carry (owner 2026-11-05 「自宅にある場合は
    受注前に持ち出して」: the Home copy waits for that quest)."""
    return quest_optional_carry.wanted_ahead(policy, snapshot, item)


def _no_lasting_fear_resistance(policy, snapshot, item) -> bool:
    """Owner 2026-11-11: carried only without a lasting fear resistance."""
    return not heroism_potion.lasting_fear_resistance(snapshot)


def _light_carry_not_replaced(policy, snapshot, item) -> bool:
    """Owner 2026-10-31 「光の巻物→購入を抑制」 once the Staff of Light is absorbed."""
    return not me_capability.replaced_by_absorbed(
        policy, snapshot, me_capability.Carry("required_scrolls", "light"))


def _magic_eater_absorbs(policy, snapshot, item) -> bool:
    """The device table absorbs the kind and another copy still raises its count.

    Owner 2026-11-13 「99回なら必ず拾わない」: at the cap (mind-magic-eater.cpp keeps no count past
    99) a copy adds nothing.  The first copy of a stage staff counts too (me_device_policy).
    """
    row = me_device_policy.device(item)
    if row is None or row.never or not (row.absorb_now or row.absorb_after_charge or row.stage):
        return False
    return (me_capability.count(policy, snapshot, row.kind, row.sval)
            < me_device_policy.POWER_COUNT_CAP)


def _mana_food(policy, snapshot, item) -> bool:
    """The zombie's food: the Wand of Wonder staple (owner 2026-10-30), the food the drained
    staple leaves (magic_eater_devices.drained_staple_food), any charged device without one."""
    if snapshot.player.food_type != FOOD_TYPE_MANA or item.tval == TVAL_ROD:
        return False
    if is_staple_food(item):
        return True
    if staple_food(snapshot) is None:
        return item.charges > 0
    return drained_staple_food(policy, snapshot, item)


def _drink_does_something(policy, snapshot, item) -> bool:
    """Drinking it raises a stat below the character's maximum (consumable_policy.DRINK_AT_ONCE)."""
    return consumable_policy.does_something(snapshot, item)


def _stone_to_mud_kept(policy, snapshot, item) -> bool:
    """User 2026-10-20 「すべて残す」, lifted for the Magic-Eater that absorbed it (owner
    2026-11-07 「岩石溶解の全部持つ決まりは、取り込む分だけ外す。」): its wands then serve only
    the absorption (``_magic_eater_absorbs``), and the absorbed power meets the quests' wall
    breach (me_capability.REPLACES)."""
    return not me_capability.has(policy, snapshot, "wand", SV_WAND_STONE_TO_MUD)


WHEN = {
    "always": _always,
    "not-replaced": _not_replaced,
    "quest-carry": _quest_carry,
    "quest-optional-carry": _quest_optional_carry,
    "no-lasting-fear-resistance": _no_lasting_fear_resistance,
    "light-carry-not-replaced": _light_carry_not_replaced,
    "magic-eater-absorbs": _magic_eater_absorbs,
    "mana-food": _mana_food,
    "stone-to-mud-kept": _stone_to_mud_kept,
    "drink-does-something": _drink_does_something,
}


# -- the table: kind -> who uses it, when -------------------------------------------

ROUTES = (
    # Survival (never surplus but what an absorbed power replaces).
    Route(TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, "supply-ledger:recall"),
    Route(TVAL_SCROLL, SV_SCROLL_TELEPORT, "supply-ledger:teleport"),
    Route(TVAL_SCROLL, SV_SCROLL_TELEPORT_LEVEL, "threat_escape:teleport-level"),
    Route(TVAL_SCROLL, SV_SCROLL_PHASE_DOOR, "policy_combat:relocation"),
    Route(TVAL_POTION, SV_POTION_CURE_CRITICAL, "supply-ledger:cure"),
    Route(TVAL_POTION, SV_POTION_HEALING, "policy_constants.HEAL_ORDER"),
    Route(TVAL_POTION, SV_POTION_STAR_HEALING, "policy_constants.HEAL_ORDER"),
    Route(TVAL_POTION, SV_POTION_LIFE, "policy_constants.HEAL_ORDER"),
    Route(TVAL_POTION, SV_POTION_RESISTANCE, "resist_potion"),
    Route(TVAL_POTION, SV_POTION_RESIST_HEAT, "oneshot_breath.DRINKS"),
    Route(TVAL_POTION, SV_POTION_RESIST_COLD, "oneshot_breath.DRINKS"),
    # Owner 2026-11-01: a reliable absorbed Speed staff replaces the potion.
    Route(TVAL_POTION, SV_POTION_SPEED, "speed_dose", "not-replaced"),
    Route(TVAL_POTION, SV_POTION_HEROISM, "heroism_potion", "no-lasting-fear-resistance"),
    # Drunk: restores when drained (policy_home reserves them at Home).
    *(Route(TVAL_POTION, sval, "stat-restore") for sval in sorted(RESTORE_POTION_SVAL_BY_STAT.values())),
    Route(TVAL_POTION, SV_POTION_RESTORE_EXP, "experience-restore"),
    # Drunk at once, wherever they are (consumable_policy.DRINK_AT_ONCE, owner 2026-11-13).
    *(Route(TVAL_POTION, sval, consumable_policy.DRINK_AT_ONCE[TVAL_POTION, sval].drinker,
            "drink-does-something")
      for sval in sorted(sval for tval, sval in consumable_policy.DRINK_AT_ONCE)),
    # Owner 2026-11-05: Enlightenment only as the Q25 optional carry.
    Route(TVAL_POTION, SV_POTION_ENLIGHTENMENT, "quest_optional_carry", "quest-optional-carry"),
    # Scrolls of a use.
    Route(TVAL_SCROLL, SV_SCROLL_IDENTIFY, "identification"),
    Route(TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, "full-identification", "not-replaced"),
    # Owner 2026-11-13 「魔道具術師では不要な解呪」: the absorbed Remove Curse staff's powerful
    # activation (remove_all_curse) replaces both scrolls (me_capability.REPLACES).
    Route(TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, "_town_remove_curse_key", "not-replaced"),
    Route(TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, "remove-curse:reserve", "not-replaced"),
    Route(TVAL_SCROLL, SV_SCROLL_LIGHT, "quest-light", "light-carry-not-replaced"),
    Route(TVAL_SCROLL, SV_SCROLL_MAPPING, "area_mapping"),
    Route(TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, "mining:detection"),
    Route(TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION, "destruction-gate"),
    Route(TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_HIT, "launcher-enchant"),
    Route(TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_DAM, "launcher-enchant"),
    Route(TVAL_SCROLL, 46, "consumable_policy.read_on_sight"),   # Acquirement
    Route(TVAL_SCROLL, 47, "consumable_policy.read_on_sight"),   # *Acquirement*
    # Any potion or scroll the prepared quest plan carries (QUEST_*.jsonc required_force).
    Route(TVAL_POTION, ANY, "quest-carry", "quest-carry"),
    Route(TVAL_SCROLL, ANY, "quest-carry", "quest-carry"),
    # The Magic-Eater's devices (me_device_policy).
    *(Route(tval, ANY, "magic_eater:absorb", "magic-eater-absorbs") for tval in sorted(DEVICE_TVALS)),
    Route(TVAL_WAND, SV_WAND_WONDER, "mana-food:staple", "mana-food"),
    Route(TVAL_WAND, ANY, "mana-food", "mana-food"),
    Route(TVAL_STAFF, ANY, "mana-food", "mana-food"),
    Route(TVAL_WAND, SV_WAND_STONE_TO_MUD, "utility:stone-to-mud", "stone-to-mud-kept"),
    Route(TVAL_ROD, SV_ROD_RECALL, "supply-ledger:recall-rod"),
    Route(TVAL_STAFF, SV_STAFF_DESTRUCTION, "destruction-gate"),
)

# Kinds the owner's tables keep but no code uses yet: kept as today until the owner answers.
OWNER_PENDING = {
    (TVAL_POTION, 40): "Q-ITEM-1 Restore Mana (表: 購入・自宅; 魔道具術師の取り込んだ魔力の回復に使える)",
    (TVAL_POTION, 61): "Q-ITEM-1 Curing (表: 持ち歩く)",
    (TVAL_POTION, 62): "Q-ITEM-1 Invulnerability (表: 自宅)",
    (TVAL_POTION, 63): "Q-ITEM-1 New Life (表: 自宅)",
    (TVAL_SCROLL, 23): "Q-ITEM-1 Mundanity (表: 自宅)",
    (TVAL_SCROLL, 37): "Q-ITEM-1 Protection from Evil (表: 自宅)",
    (TVAL_SCROLL, 38): "Q-ITEM-1 Rune of Protection (表: 購入・自宅)",
    (TVAL_SCROLL, 52): "Q-ITEM-1 Artifact Creation (表: 自宅)",
    # consumable_policy.USE_UNSUPPORTED: no rule chooses the item to enchant.
    (TVAL_SCROLL, 16): "Q-ITEM-1 Enchant Armour (表: 使う; 対象を選ぶ決まりが無い)",
    (TVAL_SCROLL, 20): "Q-ITEM-1 *Enchant Armour* (表: 使う; 対象を選ぶ決まりが無い)",
    (TVAL_SCROLL, 21): "Q-ITEM-1 *Enchant Weapon* (表: 使う; 対象を選ぶ決まりが無い)",
}

# The in-scope kinds the retention authority (policy_home._retention_reservation_baseline_detail)
# names outside the two owner tables.
RETENTION_KINDS = {
    (TVAL_WAND, SV_WAND_WONDER): "retention:mana-food:staple",
    (TVAL_WAND, SV_WAND_STONE_TO_MUD): "retention:utility:stone-to-mud",
    (TVAL_ROD, SV_ROD_RECALL): "retention:supply-ledger:recall-rod",
    (TVAL_STAFF, SV_STAFF_DESTRUCTION): "retention:destruction-gate",
}

# Who keeps what this module does not rule (for the report and the lint).
DELEGATED = {
    "equipment": "loadout optimizer, item_fate.gear_tier, spare_gear",
    "ammunition": "ammo_carry_plan / _retained_ammo_slots",
    "light and oil": "light rules, supply-ledger:oil",
    "food": "supply-ledger:food",
    "books": "the book sale and junk rules",
    "devices of other classes": "_find_device_sale / _is_useful_device / identify-staff cap",
    "unidentified items": "identification",
    "potions and scrolls the table marks 「捨てる」": "the junk path (table-discard)",
}


# -- the answers ----------------------------------------------------------------------

def _magic_eater(snapshot) -> bool:
    return snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER


def in_scope(snapshot, item) -> bool:
    """An identified potion or scroll, or an identified device of the Magic-Eater.

    A kind the owner's table marks 「捨てる」 is the junk path's (consumable_policy.discarded,
    policy_helpers._junk_class ``table-discard``): it is destroyed, not sold.  A kind outside
    the table keeps today's handling."""
    if not getattr(item, "aware", True) or getattr(item, "sval", -1) < 0:
        return False
    if item.tval in consumable_policy.KINDS:
        row = consumable_policy.row(item)
        return row is not None and not row.discard
    return (item.tval in DEVICE_TVALS and _magic_eater(snapshot)
            and getattr(item, "known", True))


def rows(tval: int, sval: int):
    """The table rows of one kind (its own rows, then the tval-wide ones)."""
    return tuple(route for route in ROUTES
                 if route.tval == tval and route.sval in (sval, ANY))


def _live(policy, snapshot, item):
    """The live consumers of ``item``, table order (a generator: the first answers ``has_use``)."""
    for route in rows(item.tval, item.sval):
        if WHEN[route.when](policy, snapshot, item):
            yield route.consumer
    if (item.tval, item.sval) in OWNER_PENDING and _not_replaced(policy, snapshot, item):
        yield "owner-pending"


def uses(policy, snapshot, item) -> tuple[str, ...]:
    """Every consumer that uses ``item`` now, for this character (empty: none)."""
    return tuple(dict.fromkeys(_live(policy, snapshot, item)))


def has_use(policy, snapshot, item) -> bool:
    """The kind is kept (an out-of-scope item: its own authority decides)."""
    return not in_scope(snapshot, item) or next(_live(policy, snapshot, item), None) is not None


def surplus(policy, snapshot, item) -> bool:
    """An in-scope item no consumer uses: never kept, shelved or bought."""
    return not has_use(policy, snapshot, item)


def has_buyer(policy, item) -> bool:
    """A store pays for it (store/service-checker.cpp, the known sale value)."""
    from hengbot.item_fate import sale_value
    from hengbot.model import STORE_HOME

    if policy._item_signature(item) in policy._unsellable_items or sale_value(policy, item) <= 0:
        return False
    return any(policy._store_accepts_sale(store, item) for store in range(STORE_HOME))


def disposable(policy, snapshot, item) -> bool:
    """Surplus with no buyer: destroyed (policy_helpers._junk_class ``no-use-route``)."""
    return surplus(policy, snapshot, item) and not has_buyer(policy, item)


def sale_candidate(policy, snapshot):
    """The first carried surplus stack an outlet of this visit buys, whole (the town
    organization sale); one no outlet takes this visit waits for the next."""
    return next((item for item in snapshot.inventory
                 if surplus(policy, snapshot, item) and has_buyer(policy, item)
                 and policy._entire_stack_is_surplus(snapshot, item)
                 and policy._town_organization_sale_store(snapshot, item) is not None), None)


def kept_kinds() -> dict:
    """(tval, sval) -> why some owner keeps the kind: the lint's subject."""
    kept = {}
    for kind, row in consumable_policy.consumables().items():
        flags = [flag for flag in ("buy", "carry", "home", "use") if getattr(row, flag)]
        if flags:
            kept[kind] = "consumable_policy:" + "+".join(flags)
    for kind in (*consumable_policy.USE_OWNED_ELSEWHERE, *consumable_policy.RESERVES):
        kept.setdefault(kind, "consumable_policy:owned-elsewhere")
    for kind, row in me_device_policy.devices().items():
        if row.buy_first or row.buy_more or row.absorb_now or row.absorb_after_charge or row.stage:
            kept.setdefault(kind, "me_device_policy")
    for kind, why in RETENTION_KINDS.items():
        kept.setdefault(kind, why)
    return kept


def registered(kind: tuple[int, int]) -> bool:
    """A row names the kind itself, or the device table routes it to the absorption.

    The tval-wide quest-carry rows serve whatever a quest plan names; they register nothing.
    """
    if kind in OWNER_PENDING or any(route.sval == kind[1] for route in rows(*kind)):
        return True
    row = me_device_policy.devices().get(kind)
    return row is not None and not row.never and bool(
        row.absorb_now or row.absorb_after_charge or row.stage)


def unregistered_kinds() -> dict:
    """The kept kinds no row registers (the lint fails on any)."""
    return {kind: why for kind, why in kept_kinds().items() if not registered(kind)}
