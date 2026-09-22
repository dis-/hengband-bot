"""Bot JSON protocol versions and the protocol-3 derivations.

Protocol 3 (hengband feature/bot-json-screen-parity, tools/bot/README.md
"版3での変更") exposes exactly what a human perceives.  It removed raw values the
screen never prints (item ``fuel`` / ``timeout``, ``player.skills``,
``stats.<stat>.cur``) and turned ``grid_map.palette[][1]`` from reserved CAVE
bits into the map's lighting variant.  Everything here reads the protocol-3
replacement explicitly and raises :class:`ProtocolSchemaError` when a required
replacement key is missing, so a removed key can never be read as a silent 0.

Rows without ``protocol_version`` predate the field (the recorded fixtures of
older emitters) and are parsed exactly as protocol 2 always parsed them.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

PROTOCOL_LEGACY = 2
PROTOCOL_SCREEN_PARITY = 3
SUPPORTED_PROTOCOL_VERSIONS = frozenset({PROTOCOL_LEGACY, PROTOCOL_SCREEN_PARITY})

# Snapshot types that describe the ordinary board (bot-json-output.cpp:1577
# ``player_turn`` and :2620 ``store``).  Every other type is a menu/screen
# response and must never be mistaken for a board.
BOARD_SNAPSHOT_TYPES = frozenset({"player_turn", "store"})
NON_BOARD_SNAPSHOT_TYPES = frozenset(
    {"knowledge", "look", "character", "spell_list", "power_list", "lore"}
)

# grid_map.palette[][1] under protocol 3 (README 圧縮地図): the lighting variant
# the map draws the terrain symbol with.
GRID_LIGHTING_VALUES = frozenset({0, 1, 2})  # 0 normal, 1 lit, 2 dark

# Flask of oil: apply-magic-others.cpp:45-47 moves the base item's
# parameter_value into ``fuel`` at creation and nothing ever burns a flask, so
# every flask carries BaseitemDefinitions.jsonc (tval 77, sval 0)
# parameter_value = 7500.  Protocol 3 prints no lamp life for flasks.
FLASK_OIL_FUEL = 7500

# PlayerStun::get_damage_penalty() (player-stun.cpp:188-205) keyed by the
# protocol-3 ``stun_rank_name`` (bot-json-output.cpp:799-817).
STUN_TO_HIT_PENALTY = {
    "none": 0,
    "slight": 5,
    "stun": 10,
    "heavy": 20,
    "unconscious": 40,
    "knocked_out": 100,
}

BTH_PLUS_ADJ = 3
PLAYER_CLASS_NINJA = 26
PLAYER_CLASS_SNIPER = 27
_TVAL_CAPTURE = 11
_TVAL_BOW = 19
_TVAL_BOLT = 18
_MELEE_WEAPON_TVALS = frozenset({20, 21, 22, 23})  # BaseitemKey::is_melee_weapon
_CROSSBOW_SVALS = frozenset({23, 24})
_WIELD_HAND_SLOTS = frozenset({"main_hand", "sub_hand"})

SKILL_RATING_KEYS = (
    "fighting",
    "shooting",
    "saving_throw",
    "stealth",
    "perception",
    "searching",
    "disarming",
    "magic_device",
    "digging",
)


class ProtocolSchemaError(RuntimeError):
    """A snapshot does not match the protocol it declares.

    Deliberately not a ValueError/LookupError: the CLI skips boards that raise
    those as merely malformed, whereas a protocol mismatch must stop the bot.
    """


def snapshot_protocol_version(data: Mapping[str, Any]) -> int:
    """Return the snapshot's protocol, failing loudly on anything unsupported."""
    if "protocol_version" not in data:
        return PROTOCOL_LEGACY
    version = data["protocol_version"]
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version not in SUPPORTED_PROTOCOL_VERSIONS
    ):
        raise ProtocolSchemaError(f"unsupported bot JSON protocol_version {version!r}")
    return version


def require(mapping: Any, key: str, where: str) -> Any:
    """``mapping[key]`` or a ProtocolSchemaError naming the missing key."""
    if not isinstance(mapping, Mapping) or key not in mapping:
        raise ProtocolSchemaError(f"protocol 3 {where} lacks required key {key!r}")
    return mapping[key]


def require_int(mapping: Any, key: str, where: str) -> int:
    value = require(mapping, key, where)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolSchemaError(f"protocol 3 {where}.{key} is not an integer: {value!r}")
    return value


def grid_lighting(flag_bits: Any) -> int:
    """Decode palette slot 1 under protocol 3 (never as CAVE bits)."""
    value = int(flag_bits)
    if value not in GRID_LIGHTING_VALUES:
        raise ProtocolSchemaError(f"protocol 3 grid lighting variant {flag_bits!r}")
    return value


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


def v3_item_fuel(item_data: Mapping[str, Any], *, tval: int, sval: int, known: bool) -> int:
    """The policy's ``fuel`` quantity from protocol-3 item keys.

    * light sources: ``light_turns`` (the "(N turns of light)" figure).  It is
      required for every known light that prints its life, i.e. everything but
      fixed artifacts and the Feanorian lamp (flavor-describer.cpp:427-436);
      those burn no fuel and read 0, as their raw fuel always was.  For the
      long-life ego the figure is twice the raw fuel -- the real remaining
      illumination time, which is what the refill thresholds measure.
    * flask of oil: :data:`FLASK_OIL_FUEL` (static base-item data).
    * everything else, and every unidentified item: 0 (no fuel evidence),
      exactly as protocol 2 read them.
    """
    if not known:
        return 0
    if tval == 39:  # TV_LITE
        if "light_turns" in item_data:
            return require_int(item_data, "light_turns", "item")
        if item_data.get("is_artifact") or sval == 2:  # SV_LITE_FEANOR
            return 0
        raise ProtocolSchemaError(
            f"protocol 3 known light {item_data.get('name')!r} lacks light_turns"
        )
    if tval == 77 and sval == 0:  # TV_FLASK / SV_FLASK_OIL
        return FLASK_OIL_FUEL
    return 0


def v3_item_charging(item_data: Mapping[str, Any], *, tval: int, known: bool) -> tuple[bool, int | None]:
    """``(charging, charging_count)``; known items must carry ``charging``."""
    if not known:
        return False, None
    charging = require(item_data, "charging", "item")
    if not isinstance(charging, bool):
        raise ProtocolSchemaError(f"protocol 3 item.charging is not a bool: {charging!r}")
    count = require_int(item_data, "charging_count", "rod item") if tval == 66 else None
    return charging, count


def v3_weapon_proficiency(item_data: Mapping[str, Any]) -> tuple[int, int | None]:
    """``(weapon_proficiency, weapon_proficiency_rank)``.

    The rank is always printed for a known weapon/launcher; the number only
    under show_actual_value, which the user decided to enable.  A rank without
    its number means the option is off and every evaluator would read a false
    proficiency, so it fails loudly.  No rank means protocol 2 would not have
    exported a proficiency either (0).
    """
    if "weapon_proficiency_rank" not in item_data:
        return 0, None
    rank = require_int(item_data, "weapon_proficiency_rank", "item")
    if "weapon_proficiency" not in item_data:
        raise ProtocolSchemaError(
            "protocol 3 item has weapon_proficiency_rank but no weapon_proficiency; "
            "the save must enable show_actual_value"
        )
    return require_int(item_data, "weapon_proficiency", "item"), rank


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


def _slot_is_non_weapon_bonus(slot: str, item: Mapping[str, Any]) -> bool:
    """is_non_weapon_bonus_slot() (player-status.cpp:2033-2041)."""
    tval = int(item.get("tval", 0))
    if tval == _TVAL_CAPTURE:
        return False
    if slot == "bow":
        return False
    return not (slot in _WIELD_HAND_SLOTS and tval in _MELEE_WEAPON_TVALS)


def non_weapon_to_hit(equipment: Sequence[Mapping[str, Any]], class_id: int) -> int:
    """Sum of the non-weapon-slot to-hit bonuses the player can read.

    calc_to_hit_misc (player-status.cpp:2525-2544) and calc_to_hit_bow
    (:2469-2488, real value) add every worn non-weapon item's ``to_h``
    (ninja: positive values halved, rounding up).  An unidentified item's
    ``to_h`` is not printed, so it contributes 0 here while the screen's
    displayed skill still includes it.
    """
    total = 0
    for item in equipment:
        slot = str(item.get("slot", ""))
        if not _slot_is_non_weapon_bonus(slot, item):
            continue
        if not item.get("known", False):
            continue
        to_h = int(item.get("to_h", 0))
        if class_id == PLAYER_CLASS_NINJA and to_h > 0:
            to_h = (to_h + 1) // 2
        total += to_h
    return total


def displayed_skill_to_hit_terms(
    *,
    equipment: Sequence[Mapping[str, Any]],
    dex_index: int,
    str_index: int,
    class_id: int,
    level: int,
    blessed: bool,
    hero: bool,
    berserk: bool,
    stun_rank_name: str,
    riding: bool,
) -> tuple[int, int]:
    """``(melee_terms, shooting_terms)`` the fighting/shooting ratings add.

    calc_skill_rating_sources (status-first-page.cpp:291-307):
      fighting = skill_thn + to_h_m * BTH_PLUS_ADJ
      shooting = skill_thb + (to_h_b + bow.to_h) * BTH_PLUS_ADJ
    returned here as ``to_h_m`` and ``to_h_b + bow.to_h`` from printed values.
    """
    from hengbot.warrior_equipment_evaluator import (
        ADJ_DEX_TO_H,
        ADJ_STR_HOLD,
        ADJ_STR_TO_H,
    )

    if stun_rank_name not in STUN_TO_HIT_PENALTY:
        raise ProtocolSchemaError(f"protocol 3 unknown stun rank {stun_rank_name!r}")
    if riding:
        # calc_riding_bow_penalty() depends on the ridden monster and riding
        # skill_exp, neither of which protocol 3 prints on the board.
        raise ProtocolSchemaError("protocol 3 skill derivation while riding is unsupported")
    stat_terms = ADJ_DEX_TO_H[dex_index] + ADJ_STR_TO_H[str_index]
    temporary = 10 * blessed + 12 * hero - STUN_TO_HIT_PENALTY[stun_rank_name]
    worn = non_weapon_to_hit(equipment, class_id)
    # calc_to_hit_misc: berserk adds 12; calc_to_hit_bow: berserk subtracts 12.
    to_h_m = stat_terms + temporary + 12 * berserk + worn
    to_h_b = stat_terms + temporary - 12 * berserk + worn
    bow = next((item for item in equipment if item.get("slot") == "bow"), None)
    bow_to_h = 0
    if bow is not None:
        weight_limit = ADJ_STR_HOLD[str_index]
        bow_weight = int(bow.get("weight", 0)) // 10
        heavy = weight_limit < bow_weight
        if heavy:
            to_h_b += 2 * (weight_limit - bow_weight)
        if (
            not heavy
            and class_id == PLAYER_CLASS_SNIPER
            and int(bow.get("tval", 0)) == _TVAL_BOW
            and int(bow.get("sval", -1)) in _CROSSBOW_SVALS
        ):
            to_h_b += 10 + level // 5
        if bow.get("known", False):
            bow_to_h = int(bow.get("to_h", 0))
    return to_h_m, to_h_b + bow_to_h


def skill_rating_value(ratings: Any, key: str) -> int:
    row = require(ratings, key, "player.skill_ratings")
    if "value" not in row:
        raise ProtocolSchemaError(
            f"protocol 3 skill_ratings.{key} has no value; the save must enable show_actual_value"
        )
    return require_int(row, "value", f"player.skill_ratings.{key}")


def v3_player_skills(player_data: Mapping[str, Any], equipment: Sequence[Mapping[str, Any]]) -> dict[str, int | None]:
    """PlayerState skill fields from protocol-3 player data.

    Derivation (exact inverse of calc_skill_rating_sources):
      melee_skill    = fighting.value - 3 * to_h_m
      shooting_skill = shooting.value - 3 * (to_h_b + bow.to_h)
      saving_skill   = saving_throw.value          (skill_sav)
      device_skill   = magic_device.value          (skill_dev)
      stealth_skill  = stealth.value               (skill_stl; -1 when <= 0)
      two_weapon_skill, shield_skill = None: only the ~f list prints them.
    """
    ratings = require(player_data, "skill_ratings", "player")
    stats = require(player_data, "stats", "player")
    status = require(player_data, "status", "player")
    status_bar = require(player_data, "status_bar", "player")
    speed_display = require(player_data, "speed_display", "player")
    active = {str(entry.get("key")) for entry in status_bar if isinstance(entry, Mapping)}
    to_h_m, bow_terms = displayed_skill_to_hit_terms(
        equipment=equipment,
        dex_index=require_int(require(stats, "dex", "player.stats"), "index", "player.stats.dex"),
        str_index=require_int(require(stats, "str", "player.stats"), "index", "player.stats.str"),
        class_id=int(player_data.get("class_id", -1)),
        level=int(player_data.get("level", 1)),
        blessed="blessed" in active,
        hero="heroism" in active,
        berserk="berserk" in active,
        stun_rank_name=str(require(status, "stun_rank_name", "player.status")),
        riding=bool(require(speed_display, "riding", "player.speed_display")),
    )
    return {
        "melee_skill": skill_rating_value(ratings, "fighting") - BTH_PLUS_ADJ * to_h_m,
        "shooting_skill": skill_rating_value(ratings, "shooting") - BTH_PLUS_ADJ * bow_terms,
        "saving_skill": skill_rating_value(ratings, "saving_throw"),
        "device_skill": skill_rating_value(ratings, "magic_device"),
        "stealth_skill": skill_rating_value(ratings, "stealth"),
        "two_weapon_skill": None,
        "shield_skill": None,
    }


def skill_exp_known(player: Any, names: tuple[str, ...] = ("two_weapon_skill", "shield_skill")) -> bool:
    """Whether the board carries the two-weapon / shield skill_exp.

    Protocol 3 prints them only on the ~f skill list; until the policy has
    read it they are None.  Evaluators then report the value as unknown and
    fail closed (like a missing calibration) instead of guessing 0; the
    decision path requests ~f before any evaluation.
    """
    # Only an explicit None is unknown: PlayerState carries both fields on
    # every protocol, and None only under protocol 3 before ~f was read.
    return all(getattr(player, name, 0) is not None for name in names)


_LIGHT_TURNS_RE = re.compile(r"[\(（](\d+)ターンの寿命[\)）]|\(with (\d+) turns of light\)")


def printed_light_turns(name: str) -> int | None:
    """The "(N turns of light)" figure printed in an item name, if any."""
    match = _LIGHT_TURNS_RE.search(name)
    if match is None:
        return None
    return int(match.group(1) or match.group(2))
