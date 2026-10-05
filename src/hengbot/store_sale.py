"""Player-known zero-value classes from Hengband's sale item tester.

Source: store/service-checker.cpp; system/item/item-entity.cpp:calc_price;
object/object-value.cpp:object_value_real; lib/edit/BaseitemDefinitions.jsonc.
The zero base kinds are enumerated from definitions, not a potion blacklist.
Unaware flavors use get_baseitem_price's positive guesses, never hidden sval.
"""
from hengbot.model import InventoryItem
from functools import lru_cache
import json
from pathlib import Path
import re

# All nonpositive base kinds in BaseitemDefinitions.jsonc (2026-10-05).
ZERO_BASE_KINDS = frozenset({
    (0, 0),
    (1, 1),
    (1, 2),
    (1, 3),
    (1, 4),
    (1, 5),
    (1, 6),
    (1, 7),
    (1, 8),
    (3, 3),
    (3, 6),
    (7, 0),
    (9, 50),
    (10, 0),
    (10, 1),
    (36, 0),
    (40, 0),
    (45, 0),
    (45, 1),
    (45, 2),
    (45, 3),
    (45, 50),
    (55, 0),
    (55, 1),
    (55, 2),
    (55, 3),
    (65, 0),
    (65, 2),
    (66, 30),
    (70, 0),
    (70, 1),
    (70, 2),
    (70, 3),
    (70, 4),
    (70, 5),
    (70, 7),
    (75, 4),
    (75, 5),
    (75, 6),
    (75, 7),
    (75, 9),
    (75, 11),
    (75, 13),
    (75, 15),
    (75, 16),
    (75, 17),
    (75, 18),
    (75, 19),
    (75, 20),
    (75, 21),
    (75, 23),
    (75, 65),
    (80, 0),
    (80, 1),
    (80, 2),
    (80, 3),
    (80, 4),
    (80, 5),
    (80, 6),
    (80, 7),
    (80, 8),
    (80, 9),
})
ARMOUR = frozenset(range(30, 39))
WEAPONS = frozenset({19, 20, 21, 22, 23})
AMMO = frozenset({16, 17, 18})
WEARABLE = ARMOUR | WEAPONS | AMMO | {39, 40, 45}
# EgoDefinitions uses inventory-slot-types.h to distinguish identical labels.
EGO_SLOTS = {16: 23, 17: 23, 18: 23, 19: 26, 20: 24, 21: 24, 22: 24,
             23: 24, 30: 35, 31: 34, 32: 33, 33: 33, 34: 25, 35: 32,
             36: 31, 37: 31, 38: 31, 39: 30, 40: 29, 45: 27}


@lru_cache(maxsize=1)
def _value_knowledge():
    return json.loads(Path(__file__).with_name("store_sale_knowledge.json").read_text(encoding="utf-8"))


def _named_definition(item, definitions):
    # Strip inscriptions: text there is player input, not an item identity.
    name = re.sub(r"\s+\{[^{}]*\}\s*$", "", item.name)
    matches = []
    for entry in definitions:
        if 'slot' in entry and entry['slot'] != EGO_SLOTS.get(item.tval):
            continue
        kind = entry.get("base_item")
        if kind and (kind["type_value"], kind["subtype_value"]) != (item.tval, item.sval):
            continue
        score = max((len(label) for label in entry["name"].values()
                     if label and label in name), default=0)
        if score:
            matches.append((score, entry))
    return max(matches, key=lambda pair: pair[0])[1] if matches else None


def sale_monrace(item):
    """Monster identity printed on a figurine/statue, never a hidden pval ID."""
    return _named_definition(item, _value_knowledge()["monraces"])


def _flag_cost(flags, pval, knowledge):
    total = 0
    groups = [[0, sum(flag in flags for flag in knowledge["group_zero_extra_count"])], [0, 0]]
    for rule in knowledge["flag_rules"]:
        if rule["flag"] not in flags or rule["unless"] in flags:
            continue
        if rule["positive_pval"] and pval <= 0:
            continue
        cost = rule["constant"] + rule["slope"] * pval
        if rule["group"] is None:
            total += cost
        else:
            group = groups[rule["group"]]
            group[0] += cost
            group[1] += rule["count"]
    total += sum(cost * count for cost, count in groups)
    if knowledge["uncursed_teleport"] in flags:
        total += 250
    return total


def has_positive_sale_value(item: InventoryItem, base_cost: int | None) -> bool:
    """Project calc_price/object_value_real using player-visible item knowledge.

    Unknown flavors use the game's guesses. Named fixed artifacts bypass the
    ordinary modifier rules. Unresolved ego/artifact identities fail closed:
    the combined exported artifact bit cannot prove which value branch applies.
    Hidden activation IDs and flags are never used to rescue a nonpositive
    visible valuation; this can conservatively decline an ambiguous item.
    """
    knowledge = _value_knowledge()
    base = knowledge["baseitems"].get(f"{item.tval}:{item.sval}")
    if base_cost is None and base is not None and item.aware:
        base_cost = base["cost"]
    if (item.known or item.pseudo_feeling) and (item.is_broken or item.is_cursed):
        return False
    if not item.known and not item.aware:
        if item.tval == 8:
            race = sale_monrace(item)
            return race is not None and race["level"] > 0
        return item.tval in {80, 75, 70, 55, 65, 66, 40, 45, 11}
    if item.aware and (base_cost is not None and base_cost <= 0
                       or (item.tval, item.sval) in ZERO_BASE_KINDS):
        return False
    if base_cost is None or (item.known and base is None):
        return False
    if not item.known:
        return True
    flags = set(item.known_flags) | set(base["flags"] if base else ())
    fixed = (_named_definition(item, knowledge["artifacts"])
             if item.is_artifact else None)
    ego = _named_definition(item, knowledge["egos"]) if item.is_ego else None
    if (item.is_ego or item.is_artifact) and not item.fully_known:
        return False
    if item.is_ego and (ego is None or ego["cost"] <= 0):
        return False
    if fixed is not None:
        if fixed["cost"] <= 0:
            return False
        extra_flags = flags - set(base["flags"] if base else ()) - set(fixed["flags"])
        return fixed["cost"] + _flag_cost(extra_flags, item.pval, knowledge) > 0
    if item.tval in WEARABLE and item.pval < 0:
        return False
    if item.tval in ARMOUR and item.to_a < 0:
        return False
    if item.tval in WEAPONS | AMMO and item.to_h + item.to_d < 0:
        return False
    if item.tval in {40, 45} and item.to_h + item.to_d + item.to_a < 0:
        return False
    if item.tval == 7 and item.pval == 0:
        return False
    value = base_cost
    if ego is not None:
        flags.update(ego["flags"])
        value += ego["cost"]
    extra_flags = flags - set(base["flags"] if base else ()) - set(ego["flags"] if ego else ())
    extra_value = _flag_cost(extra_flags, item.pval, knowledge)
    # Ordinary items only add flag_cost when art_flags.any(). Smith effects
    # also appear in get_flags, but the emitter does not expose their origin.
    # A positive extra cannot prove that a nonpositive ordinary value is rescued.
    value += extra_value if ego is not None or item.is_artifact else min(0, extra_value)
    if item.tval in WEARABLE and item.pval > 0:
        number = knowledge["flag_numbers"]
        value += sum(item.pval * 200 for flag in ("STR", "INT", "WIS", "DEX", "CON", "CHR")
                     if number[flag] in flags)
        value += sum(item.pval * 100 for flag in ("MAGIC_MASTERY", "STEALTH", "SEARCH")
                     if number[flag] in flags)
        if number["SPEED"] in flags:
            value += item.pval * 10000
    if item.tval in {55, 65} and base and base["parameter_value"] > 0:
        charge_value = value * item.charges
        if item.tval == 65:
            charge_value //= max(1, item.count)
        value += charge_value // (base["parameter_value"] * 2)
    if item.tval in ARMOUR:
        value += 200 * (item.to_h - (base["hit_bonus"] if base else 0)
                        + item.to_d - (base["damage_bonus"] if base else 0)) + 100 * item.to_a
    elif item.tval in WEAPONS:
        value += 100 * (item.to_h + item.to_d + item.to_a)
    elif item.tval in AMMO:
        value += 5 * (item.to_h + item.to_d)
    elif item.tval in {40, 45}:
        value += 200 * (item.to_h + item.to_d + item.to_a)
    if item.tval in WEAPONS | AMMO and base is not None:
        num, sides = map(int, base["base_dice"].split("d"))
        factor = 250 if item.tval in WEAPONS else 5
        value += factor * ((item.damage_dice_num - num) * item.damage_dice_sides
                           + (item.damage_dice_sides - sides) * item.damage_dice_num)
    if item.tval == 8:  # Figurine: object_value_real replaces the base value.
        race = sale_monrace(item)
        if race is None:
            return False
        value = race["level"] * 50  # Sign is positive in every higher level band.
    if item.tval == 11:  # Capture balls are worth at least 1000, even empty.
        return True
    return value > 0
