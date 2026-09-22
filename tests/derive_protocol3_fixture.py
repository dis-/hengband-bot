"""Derive protocol-3 rows from recorded protocol-2 rows (derived fixtures).

No protocol-3 capture exists yet (the new exe has not run; only one game
instance may run).  This script rewrites recorded protocol-2 JSONL rows exactly
as the emitter changelog specifies (hengband tools/bot/README.md "版3での変更",
bot-json-output.cpp at 45b567ea7f), so the protocol-3 client path can replay
recorded decisions.  Every value the transformation cannot take from the
protocol-2 row is listed in ``PLACEHOLDERS``; none of them is read by the
client's decision path.

Transformation (per row):
* ``protocol_version`` 2 -> 3.
* items (inventory / equipment / store.items / knowledge.items / look items):
  - ``fuel`` removed; ``light_turns`` = the "(N turns of light)" figure the
    recorded item name prints (flavor-describer.cpp:427-451; absent for fixed
    artifacts and the Feanorian lamp, whose names print none).
  - ``timeout`` removed; ``charging`` = calc_displayed_charging_count() > 0,
    rods also ``charging_count`` (flavor-describer.cpp:343-363, per-rod
    timeout = BaseitemDefinitions parameter_value).
  - ``weapon_proficiency_rank`` = PlayerSkill::weapon_skill_rank(exp); the
    number stays (show_actual_value is on for the bot's save).
* player: ``skills`` removed; ``skill_ratings`` built by
  calc_skill_rating_sources() (status-first-page.cpp:291-307) from the raw
  skills and the printed to-hit terms (hengbot.protocol
  .displayed_skill_to_hit_terms); ``stats.<stat>.cur`` removed, ``top`` added;
  ``status`` gains stun/cut ranks; ``status_bar``, ``speed_display``,
  ``max_exp``/``exp_drained``/``max_level``/``level_drained`` added.
* grid_map ``palette[][1]``: protocol 2 sent the reserved 0 (asserted); it
  becomes lighting variant 0 (normal).
* character: ``skills`` -> ``skill_ratings``, ``alignment`` ->
  ``alignment_label`` / ``alignment_value``.
* monsters gain ``level`` (null), ``fast`` / ``slow`` / ``invulnerable``.

Usage: python tests/derive_protocol3_fixture.py SOURCE.jsonl.gz OUTPUT.jsonl.gz
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    import hengbot  # noqa: F401  (tests run with src on PYTHONPATH)
except ImportError:
    sys.path.insert(0, str(ROOT / "src"))

from hengbot.monrace_knowledge import _strip_jsonc  # noqa: E402
from hengbot.protocol import (  # noqa: E402
    SKILL_RATING_KEYS,
    displayed_skill_to_hit_terms,
    printed_light_turns,
)
from hengbot.warrior_equipment_evaluator import modify_stat_value  # noqa: E402

BASEITEMS = Path("C:/hengband/lib/edit/BaseitemDefinitions.jsonc")

# Values protocol 2 does not carry.  None of them reaches a decision.
PLACEHOLDERS = {
    "player.status_bar": "[] (protocol 2 carries no status-bar evidence)",
    "player.status.stun_rank(_name)": "0/none, or 1/slight when stunned",
    "player.status.cut_rank(_name)": "0/none, or 1/graze when cut",
    "player.skill_ratings.{perception,searching,disarming,digging}.value": "0",
    "player.stats.<stat>.at_racial_max": "false",
    "player.max_exp / max_level": "exp / level; exp_drained / level_drained false",
    "player.speed_display": "value speed-110, color white, riding false",
    "clock": "{day: 1, hour: 0, minute: 0}",
    "health_bar / riding_health_bar": "null",
    "floor.dungeon_name": "empty string",
    "monster level": "null; fast / slow / invulnerable false",
    "grid_map.found_item_names": "names null",
    "character.alignment_label": "empty string (alignment_value keeps the number)",
}

_RATINGS = (
    "very_bad", "bad", "poor", "fair", "good", "very_good",
    "excellent", "superb", "heroic", "legendary",
)
_DIVISORS = {
    "fighting": 12, "shooting": 12, "saving_throw": 7, "stealth": 1,
    "perception": 6, "searching": 6, "disarming": 8, "magic_device": 6,
    "digging": 4,
}
_WEAPON_EXP_RANKS = (4000, 6000, 7000, 8000)
_STUN_RANK_NAMES = ("none", "slight", "stun", "heavy", "unconscious", "knocked_out")
_ITEM_ROW_KEYS = ("inventory", "equipment")


def _rod_timeouts() -> dict[int, int]:
    data = json.loads(_strip_jsonc(BASEITEMS.read_text(encoding="utf-8-sig")))
    return {
        int(entry["itemkind"]["subtype_value"]): int(entry.get("parameter_value", 0))
        for entry in data["baseitems"]
        if int(entry["itemkind"]["type_value"]) == 66
    }


ROD_TIMEOUT = _rod_timeouts()


def classify_skill_rating(x: int, y: int) -> tuple[str, int | None]:
    """classify_skill_rating() (status-first-page.cpp:150-191)."""
    if x < 0:
        return "very_bad", None
    y = max(1, y)
    ratio = x // y
    if ratio <= 1:
        return "bad", None
    table = {2: "poor", 3: "fair", 4: "fair", 5: "good", 6: "very_good", 7: "excellent", 8: "excellent"}
    if ratio in table:
        return table[ratio], None
    if ratio <= 13:
        return "superb", None
    if ratio <= 17:
        return "heroic", None
    return "legendary", ((ratio - 17) * 5) // 2


def _rating_row(key: str, value: int) -> dict:
    rating, legendary = classify_skill_rating(value, _DIVISORS[key])
    row = {"text": f"{value:3d}-{rating}", "color": "white", "rating": rating, "value": value}
    if legendary is not None:
        row["legendary_level"] = legendary
    assert rating in _RATINGS
    return row


def derive_item(item: dict) -> dict:
    item = dict(item)
    fuel = item.pop("fuel", None)
    timeout = item.pop("timeout", None)
    if not item.get("known", False):
        assert fuel is None and timeout is None, item.get("name")
        return item
    tval = int(item.get("tval", 0))
    if tval == 39:
        turns = printed_light_turns(str(item.get("name", "")))
        if turns is not None:
            # The printed life is the raw fuel, doubled for the long-life ego.
            assert fuel is not None and turns in (int(fuel), 2 * int(fuel)), item["name"]
            item["light_turns"] = turns
        else:
            assert item.get("is_artifact") or item.get("sval") == 2, item["name"]
    timeout = int(timeout or 0)
    if tval == 66:
        if timeout <= 0:
            count = 0
        elif int(item.get("count", 1)) <= 1:
            count = 1
        else:
            per_one = ROD_TIMEOUT[int(item["sval"])]
            count = min((timeout + per_one - 1) // per_one, int(item["count"]))
        item["charging"] = count > 0
        item["charging_count"] = count
    else:
        item["charging"] = timeout != 0
    if "weapon_proficiency" in item:
        exp = int(item["weapon_proficiency"])
        item["weapon_proficiency_rank"] = sum(exp >= bound for bound in _WEAPON_EXP_RANKS)
    return item


def _derive_items(rows):
    return [derive_item(item) if isinstance(item, dict) else item for item in rows]


def _to_hit_terms(player: dict, equipment: list, stun_name: str) -> tuple[int, int]:
    stats = player.get("stats", {})
    return displayed_skill_to_hit_terms(
        equipment=[item for item in equipment if isinstance(item, dict)],
        dex_index=int(stats["dex"]["index"]),
        str_index=int(stats["str"]["index"]),
        class_id=int(player.get("class_id", -1)),
        level=int(player.get("level", 1)),
        blessed=False,
        hero=False,
        berserk=False,
        stun_rank_name=stun_name,
        riding=False,
    )


def _skill_ratings(raw: dict, player: dict, equipment: list, stun_name: str) -> dict:
    """raw holds thn/thb/sav/dev/stl/dis/srh/fos/dig (absent -> 0)."""
    to_h_m, bow_terms = _to_hit_terms(player, equipment, stun_name)
    stealth = int(raw.get("stl", 0))
    values = {
        "fighting": int(raw.get("thn", 0)) + 3 * to_h_m,
        "shooting": int(raw.get("thb", 0)) + 3 * bow_terms,
        "saving_throw": int(raw.get("sav", 0)),
        "stealth": stealth if stealth > 0 else -1,
        "perception": int(raw.get("fos", 0)),
        "searching": int(raw.get("srh", 0)),
        "disarming": int(raw.get("dis", 0)),
        "magic_device": int(raw.get("dev", 0)),
        "digging": int(raw.get("dig", 0)),
    }
    return {key: _rating_row(key, values[key]) for key in SKILL_RATING_KEYS}


def _stat_top(stat: dict) -> int:
    """stat_top: the max under the same modifier that turns cur into use."""
    cur, use, top = int(stat["cur"]), int(stat["use"]), int(stat["max"])
    if cur == top:
        return use
    for magnitude in range(0, 60):
        for modifier in (magnitude, -magnitude):
            if modify_stat_value(cur, modifier) == use:
                return modify_stat_value(top, modifier)
    raise AssertionError(f"no stat modifier maps {cur} to {use}")


def derive_player(player: dict, equipment: list) -> dict:
    player = dict(player)
    status = dict(player.get("status", {}))
    stunned = bool(status.get("stunned", False))
    stun_rank = 1 if stunned else 0
    status["stun_rank"] = stun_rank
    status["stun_rank_name"] = _STUN_RANK_NAMES[stun_rank]
    status["cut_rank"] = 1 if status.get("cut", False) else 0
    status["cut_rank_name"] = "graze" if status.get("cut", False) else "none"
    player["status"] = status
    stats = {}
    for name, stat in player.get("stats", {}).items():
        stat = dict(stat)
        stat["top"] = _stat_top(stat)
        stat.pop("cur")
        stat["at_racial_max"] = False
        stats[name] = stat
    skills = player.pop("skills", {})
    raw = {
        "thn": skills.get("melee", 0),
        "thb": skills.get("shooting", skills.get("melee", 0)),
        "sav": skills.get("saving", 0),
        "dev": skills.get("device", 0),
        "stl": skills.get("stealth", 0),
    }
    player["skill_ratings"] = _skill_ratings(
        raw, player, equipment, status["stun_rank_name"]
    )
    player["stats"] = stats
    player["status_bar"] = []
    player["speed_display"] = {
        "value": int(player.get("speed", 110)) - 110,
        "text": "",
        "color": "white",
        "riding": False,
    }
    player["max_exp"] = int(player.get("exp", 0))
    player["exp_drained"] = False
    player["max_level"] = int(player.get("level", 1))
    player["level_drained"] = False
    return player


def _derive_monster(monster: dict) -> dict:
    monster = dict(monster)
    monster.setdefault("level", None)
    for key in ("fast", "slow", "invulnerable"):
        monster.setdefault(key, False)
    return monster


def derive_row(row: dict) -> dict:
    if row.get("protocol_version") != 2:
        raise ValueError(f"not a protocol-2 row: {row.get('protocol_version')!r}")
    row = json.loads(json.dumps(row))
    row["protocol_version"] = 3
    equipment = row.get("equipment", [])
    player_source = row.get("player")
    for key in _ITEM_ROW_KEYS:
        if isinstance(row.get(key), list):
            row[key] = _derive_items(row[key])
    store = row.get("store")
    if isinstance(store, dict) and isinstance(store.get("items"), list):
        store["items"] = _derive_items(store["items"])
    knowledge = row.get("knowledge")
    if isinstance(knowledge, dict) and isinstance(knowledge.get("items"), list):
        knowledge["items"] = _derive_items(knowledge["items"])
    look = row.get("look")
    if isinstance(look, dict):
        for grid in look.get("grids", []):
            if isinstance(grid, dict) and isinstance(grid.get("items"), list):
                grid["items"] = _derive_items(grid["items"])
            if isinstance(grid, dict) and isinstance(grid.get("monster"), dict):
                grid["monster"] = _derive_monster(grid["monster"])
    if isinstance(player_source, dict):
        row["player"] = derive_player(player_source, equipment)
    character = row.get("character")
    if isinstance(character, dict):
        raw = character.pop("skills", {})
        alignment = character.pop("alignment", None)
        character["alignment_label"] = ""
        character["alignment_value"] = alignment
        if isinstance(player_source, dict) and "stats" in player_source:
            character["skill_ratings"] = _skill_ratings(
                raw, player_source, equipment,
                row["player"]["status"]["stun_rank_name"],
            )
    for key in ("visible_monsters", "detected_monsters"):
        if isinstance(row.get(key), list):
            row[key] = [_derive_monster(m) if isinstance(m, dict) else m for m in row[key]]
    grid_map = row.get("grid_map")
    if isinstance(grid_map, dict) and isinstance(grid_map.get("palette"), list):
        for entry in grid_map["palette"]:
            assert entry[1] == 0, "protocol 2 palette slot 1 is the reserved 0"
        if isinstance(grid_map.get("found_items"), list):
            grid_map["found_item_names"] = [
                list(found[:2]) + [None] * int(found[2]) for found in grid_map["found_items"]
            ]
    if "player" in row:
        row["clock"] = {"day": 1, "hour": 0, "minute": 0}
        row["health_bar"] = None
        row["riding_health_bar"] = None
        floor = row.get("floor")
        if isinstance(floor, dict):
            floor["dungeon_name"] = ""
    return row


# ClassSkillDefinitions.jsonc "skills" max_exp for the warrior (class 0):
# MARTIAL_ARTS 8000, TWO_WEAPON 8000, RIDING 5000, SHIELD 8000.
_WARRIOR_SKILL_MAX = {0: 8000, 1: 8000, 2: 5000, 3: 8000}
_SKILL_NAMES = {0: "マーシャルアーツ", 1: "二刀流", 2: "乗馬", 3: "盾"}
_RIDING_RANKS = (500, 2000, 5000, 8000)  # PlayerSkill::riding_skill_rank bounds


def derive_skill_knowledge_row(board: dict) -> dict:
    """The ~f response (knowledge category skill_exp) for a protocol-2 board.

    make_knowledge_json SKILL_EXP (bot-json-output.cpp:2215-2231): one row per
    PlayerSkillKindType with id, name, at_max, rank and, under
    show_actual_value, exp = min(exp, max) and max.  TWO_WEAPON and SHIELD
    come from the recorded player.skills; MARTIAL_ARTS and RIDING are not in
    protocol 2 and use the warrior's start_exp 0 (placeholders).
    """
    if int(board["player"].get("class_id", -1)) != 0:
        raise ValueError("skill maxima are tabulated for the warrior only")
    skills = board["player"]["skills"]
    raw = {0: 0, 1: int(skills["two_weapon"]), 2: 0, 3: int(skills["shield"])}
    rows = []
    for skill_id in range(4):
        exp, top = raw[skill_id], _WARRIOR_SKILL_MAX[skill_id]
        bounds = _RIDING_RANKS if skill_id == 2 else _WEAPON_EXP_RANKS
        rows.append({
            "id": skill_id, "name": _SKILL_NAMES[skill_id], "at_max": exp >= top,
            "rank": sum(exp >= bound for bound in bounds),
            "exp": min(exp, top), "max": top,
        })
    row = derive_row(dict(board, type="knowledge"))
    row["knowledge"] = {"category": "skill_exp", "menu_key": "f", "skills": rows}
    return row


def derive_lines(lines: list[str]) -> list[str]:
    return [json.dumps(derive_row(json.loads(line)), ensure_ascii=False) + "\n" for line in lines]


def main(source: str, output: str) -> None:
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        lines = list(stream)
    derived = derive_lines(lines)
    with gzip.GzipFile(output, "wb", mtime=0) as raw:
        raw.write("".join(derived).encode("utf-8"))
    print(output, hashlib.sha256(Path(output).read_bytes()).hexdigest())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
