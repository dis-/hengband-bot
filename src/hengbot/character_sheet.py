"""Read the visible equipped character dump; never read hidden game values."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata

from hengbot.warrior_equipment_evaluator import modify_stat_value


class CharacterSheetUnavailable(ValueError):
    """A reason to skip optimization and wait for another periodic observation."""


@dataclass(frozen=True)
class StatRow:
    base: int
    race: int
    profession: int
    personality: int
    modifier: int
    actual: int
    current: int | None
    saturated: bool = False
    current_saturated: bool = False


@dataclass(frozen=True)
class CharacterSheet:
    rows: tuple[StatRow, ...]
    level: int
    max_hp: int
    armor_class: int
    content_hash: str
    language: str
    text: str


def _cells(line: str) -> str:
    return "".join(char + (" " if unicodedata.east_asian_width(char) in "WF" else "")
                   for char in line)


def printed_stat(text: str) -> tuple[int, bool]:
    text = text.strip()
    if text == "18/***":
        return 238, True
    if re.fullmatch(r"18/\d+", text):
        return 18 + int(text[3:]), False
    if re.fullmatch(r"\d+", text) and 3 <= int(text) <= 18:
        return int(text), False
    raise CharacterSheetUnavailable("invalid-visible-stat")


def parse_character_sheet(raw: bytes, *, encoding: str = "cp932") -> CharacterSheet:
    try:
        text = raw.decode(encoding, errors="strict")
    except UnicodeError as exc:
        raise CharacterSheetUnavailable("dump-encoding") from exc
    lines = text.splitlines()
    ja = [i for i, line in enumerate(lines)
          if all(word in line for word in ("基本", "合計", "現在", "abcdefghijkl@"))]
    en = [i for i, line in enumerate(lines)
          if all(word in line for word in ("Base", "Actual", "Current", "abcdefghijkl@"))]
    if len(ja) + len(en) != 1:
        raise CharacterSheetUnavailable("visible-base-missing")
    start, language = (ja[0], "ja") if ja else (en[0], "en")
    aliases = (("腕力", "知能", "賢さ", "器用", "耐久", "魅力") if ja
               else ("STR", "INT", "WIS", "DEX", "CON", "CHR"))
    rows = []
    for index, line in enumerate(lines[start + 1:start + 7]):
        # The game prints stat fields in 6,3,3,3,3,7,7 display cells.
        match = re.search(re.escape(aliases[index]), line, re.IGNORECASE)
        if match is None:
            raise CharacterSheetUnavailable("partial-stat-table")
        colon = line.find(":", match.end())
        if colon < 0:
            raise CharacterSheetUnavailable("partial-stat-table")
        numeric = _cells(line[colon + 1:])
        fields = [numeric[a:b].strip() for a, b in
                  ((0, 6), (6, 9), (9, 12), (12, 15), (15, 18), (18, 25), (25, 32))]
        try:
            base, base_saturated = printed_stat(fields[0])
            actual, saturated = printed_stat(fields[5])
            current, current_saturated = printed_stat(fields[6]) if fields[6] else (None, False)
            adjustments = tuple(int(value) for value in fields[1:5])
        except ValueError as exc:
            raise CharacterSheetUnavailable("partial-stat-table") from exc
        if base_saturated or base > 148:
            raise CharacterSheetUnavailable("invalid-visible-base")
        rows.append(StatRow(base, *adjustments, actual, current, saturated, current_saturated))
    if len(rows) != 6:
        raise CharacterSheetUnavailable("partial-stat-table")
    normalized = unicodedata.normalize("NFKC", text)
    level = re.search(r"(?:レベル|Level)\s*:?\s*(\d+)", normalized)
    hp = re.search(r"(?:HP|Hit points)\s*:?\s*\d+\s*/\s*(\d+)", normalized, re.I)
    ac = re.search(r"(?:AC|Armor|耐久力)\s*:?\s*\[\s*(\d+)\s*,\s*([+-]?\d+)\s*\]", normalized, re.I)
    if not level or not hp or not ac:
        raise CharacterSheetUnavailable("partial-identity-page")
    return CharacterSheet(tuple(rows), int(level[1]), int(hp[1]),
                          int(ac[1]) + int(ac[2]), hashlib.sha256(raw).hexdigest(), language, text)


def _c_quotient(numerator: int, denominator: int) -> int:
    """C integer division, which truncates toward zero."""
    quotient = abs(numerator) // denominator
    return quotient if numerator >= 0 else -quotient


def displayed_modifier(base: int, top: int, adjustment: int) -> int:
    """The Mod column the game prints for one stat row.

    Port of ``display-player-stat-info.cpp`` ``calc_basic_stat`` (residual of
    ``stat_top`` over ``stat_max`` in printed units) minus the printed race,
    class and personality columns.  ``modify_stat_value`` floors at 3, so a
    floor-concealed equipment modifier prints as the residual it left, not as
    the equipment's pval sum.
    """
    if base > 18 and top > 18:
        residual = _c_quotient(top - base, 10)
    elif base <= 18 and top <= 18:
        residual = top - base
    elif base <= 18:
        residual = _c_quotient(top - 18, 10) - base + 18
    else:
        residual = top - _c_quotient(base - 19, 10) - 19
    return residual - adjustment


# ``personality_info[].no`` is 0 for these personalities: the Japanese name line
# prints their title without "の" (display-player-misc-info.cpp
# ``display_player_name``).  Nimble, Combat, Patient, Chargeman.
PERSONALITIES_WITHOUT_NO = frozenset({4, 6, 10, 12})


def name_line_title_prefix(title: str, personality_id: int, language: str) -> str:
    """The personality text the game prints before the character name."""
    if language == "ja":
        return title + ("" if personality_id in PERSONALITIES_WITHOUT_NO else "の")
    return title + " "


def invert_current(row: StatRow, adjustment: int) -> int:
    """Positive adjustments invert uniquely; floors use the minimal candidate."""
    if row.current is None:
        return row.base
    candidates = [value for value in range(3, row.base + 1)
                  if (modify_stat_value(value, adjustment) >= row.current
                      if row.current_saturated else
                      modify_stat_value(value, adjustment) == row.current)]
    if not candidates:
        raise CharacterSheetUnavailable("inconsistent-current-stat")
    return min(candidates)


def temporary_bonuses(effects: frozenset[str]) -> tuple[int, int]:
    """Subtract visible timed bonuses after the game's HP floor and AC sum."""
    known = {"ultimate_resistance", "ult_res", "musou", "tsubureru", "shield",
             "magicdef", "magic_armour", "stone_skin", "blessed", "bless",
             "heroism", "hero", "berserk", "tsuyoshi", "extra_might", "build_up"}
    unknown = effects - known
    if unknown:
        raise CharacterSheetUnavailable("unknown-timed-effect:" + ",".join(sorted(unknown)))
    ac = (100 if effects & {"ultimate_resistance", "ult_res", "musou"} else
          50 if effects & {"tsubureru", "shield", "magicdef", "magic_armour", "stone_skin"} else 0)
    ac += 5 if effects & {"blessed", "bless"} else 0
    ac -= 10 if "berserk" in effects else 0
    hp = (10 if effects & {"heroism", "hero"} else 0) + (30 if "berserk" in effects else 0)
    hp += 50 if "tsuyoshi" in effects else 0
    hp += 15 if "extra_might" in effects else 0
    hp += 60 if "build_up" in effects else 0
    return hp, ac


def derive_equipped_calibration(sheet: CharacterSheet, snapshot, character: dict,
                                *, effects=frozenset(), sequence=None,
                                protocol_version=3, session_id=""):
    from hengbot.equipment_optimizer import (OwnedEquipmentCatalog, current_loadout,
                                            equipment_identity, ABILITY_FLAG)
    from hengbot.protocol import skill_exp_known
    from hengbot.warrior_defense_evaluator import WarriorDefenseInputs, loadout_armor_class
    from hengbot.warrior_loadout_evaluator import constitution_hp_bonus
    from hengbot.warrior_optimization import (CharacterCalibration, character_intrinsic_flags,
                                            PLAYER_ABILITY_FLAGS)

    player = snapshot.player
    if player.class_id != 0:
        raise CharacterSheetUnavailable("unsupported-class")
    if player.mimic_form:
        raise CharacterSheetUnavailable("unsupported-active-form")
    # These titles are the same visible identity page, not underlying form IDs.
    labels = ("種族", "職業", "性格") if sheet.language == "ja" else ("Race", "Class", "Personality")
    for label, key in zip(labels, ("race_title", "class_title", "personality_title")):
        title = character.get(key)
        if not isinstance(title, str):
            raise CharacterSheetUnavailable("identity-mismatch")
        explicit = r"(?m)^\s*" + label + r"\s*:\s*" + re.escape(title) + r"(?:\s|$)"
        # The ordinary dump puts personality in the character-name prefix.
        name_prefix = ((r"(?m)^\s*名前\s*:\s*" if sheet.language == "ja"
                        else r"(?m)^\s*Name\s*:\s*")
                       + re.escape(name_line_title_prefix(
                           title, player.personality_id, sheet.language)))
        if not re.search(explicit, sheet.text) and not (
            key == "personality_title" and re.search(name_prefix, sheet.text)
        ):
            raise CharacterSheetUnavailable("identity-mismatch")
    if sheet.level != player.level or sheet.max_hp != player.max_hp or sheet.armor_class != player.ac:
        raise CharacterSheetUnavailable("snapshot-mismatch")
    if protocol_version >= 3:
        if not isinstance(character.get("stat_modifiers"), list):
            raise CharacterSheetUnavailable("stat-modifiers-missing")
        if {row.get("stat_id") for row in character["stat_modifiers"] if isinstance(row, dict)} != set(range(6)):
            raise CharacterSheetUnavailable("stat-modifiers-partial")
        if not isinstance(character.get("curse_marks"), list):
            raise CharacterSheetUnavailable("curse-marks-missing")
        if character.get("base_ac") is None or character.get("ac_bonus") is None:
            raise CharacterSheetUnavailable("displayed-ac-missing")
        if character["base_ac"] + character["ac_bonus"] != player.ac:
            raise CharacterSheetUnavailable("character-ac-mismatch")
    # Correlate even gear changes that leave stat totals and displayed AC equal.
    heading = re.search(r"\[(?:キャラクタの装備|Character Equipment)\]", sheet.text, re.I)
    if heading is None:
        raise CharacterSheetUnavailable("dump-equipment-missing")
    block = re.split(r"(?m)^\s*\[", sheet.text[heading.end():], maxsplit=1)[0]
    # The game writes the dump with CRLF line ends on Windows; ``$`` stops
    # before ``\n`` only, so ``.+`` kept the ``\r`` and no worn name ever
    # matched (live 2026-10-02: every dump failed dump-equipment-mismatch).
    names = dict(re.findall(r"(?m)^([a-l])\) ([^\r\n]+)\r?$", block))
    slots = ("main_hand", "sub_hand", "bow", "main_ring", "sub_ring", "neck",
             "light", "body", "outer", "head", "arms", "feet")
    for item in snapshot.equipment:
        if item.is_equipment and (
            item.slot not in slots or names.get(chr(ord("a") + slots.index(item.slot))) != item.name
        ):
            raise CharacterSheetUnavailable("dump-equipment-mismatch")
    if character.get("mutations") is None:
        raise CharacterSheetUnavailable("mutations-missing")
    mutations = tuple(sorted(int(value) for value in character["mutations"]))
    if mutations:
        # Mutation names and sustain-overwritten symbols need an explicit rule.
        raise CharacterSheetUnavailable("unsupported-mutation")
    if not skill_exp_known(player, ("shield_skill",)):
        raise CharacterSheetUnavailable("skill-exp-unknown")
    if not isinstance(character.get("characteristics"), list):
        raise CharacterSheetUnavailable("intrinsic-flags-missing")
    if any(not isinstance(row, dict) for row in character["characteristics"]):
        raise CharacterSheetUnavailable("intrinsic-flags-partial")
    if protocol_version >= 3 and not (
        set(PLAYER_ABILITY_FLAGS.values()) | {78}
    ).issubset({row.get("flag_id") for row in character["characteristics"]}):
        raise CharacterSheetUnavailable("intrinsic-flags-partial")
    if protocol_version >= 3:
        marks = {row.get("slot"): row.get("mark") for row in character["curse_marks"] if isinstance(row, dict)}
        if any(marks.get(item.slot) not in ({"+", "*"} if item.is_cursed else {"."})
               for item in snapshot.equipment if item.is_equipment):
            raise CharacterSheetUnavailable("curse-mark-mismatch")
    if any(item.is_equipment and not item.known for item in snapshot.equipment):
        raise CharacterSheetUnavailable("equipment-stat-modifiers-unknown")
    catalog = OwnedEquipmentCatalog()
    catalog.refresh_carried((), snapshot.equipment)
    worn = current_loadout(catalog.items)
    if worn.flags & {134, 141}:
        raise CharacterSheetUnavailable("unsupported-ac-interaction")
    # Known named sets have non-additive AC and require a separate set model.
    if any(any(name in item.name for name in ("クイック", "タイニー", "武蔵", "二天", "アイシング", "つらぬき",
                                              "Quick", "Tiny", "Musashi", "Icing", "Twinkle"))
           for item in snapshot.equipment):
        raise CharacterSheetUnavailable("unsupported-ac-set")
    adjustments = tuple(row.race + row.profession + row.personality for row in sheet.rows)
    equipment_modifiers = tuple(sum(owned.item.pval for _, owned in worn.slots if index in owned.flags)
                                for index in range(6))
    natural = []
    for index, row in enumerate(sheet.rows):
        timed_stat = 4 if "tsuyoshi" in effects and index in (0, 4) else 0
        total = adjustments[index] + equipment_modifiers[index] + timed_stat
        if index in (0, 3, 4) and row.base != player.stat_max[index]:
            raise CharacterSheetUnavailable("visible-base-epoch-mismatch")
        predicted = modify_stat_value(row.base, total)
        # Compare with the column the game prints, floor information loss
        # included, before the minimum-candidate inversion below.
        if index in (0, 3, 4) and row.modifier != displayed_modifier(
            row.base, predicted, adjustments[index]
        ):
            raise CharacterSheetUnavailable("visible-modifier-mismatch")
        matches = predicted >= row.actual if row.saturated else predicted == row.actual
        # Only STR/DEX/CON constrain optimization. Other floor ambiguities
        # cannot reject an otherwise useful Warrior observation.
        if index in (0, 3, 4) and not matches:
            raise CharacterSheetUnavailable("inconsistent-equipped-stat")
        value = invert_current(row, total) if index in (0, 3, 4) else row.base
        natural.append(value)
        effective = modify_stat_value(value, total)
        if index in (0, 3, 4) and (
            effective < 238 if player.stat_use[index] >= 238 else effective != player.stat_use[index]
        ):
            raise CharacterSheetUnavailable("snapshot-stat-mismatch")
    intrinsic = tuple(modify_stat_value(value, adjustment)
                      for value, adjustment in zip(natural, adjustments))
    hp_bonus, ac_bonus = temporary_bonuses(frozenset(effects))
    neutral_hp = player.max_hp - hp_bonus
    if neutral_hp <= player.level + 1:
        raise CharacterSheetUnavailable("hp-floor-ambiguous")
    con = modify_stat_value(natural[4], adjustments[4] + equipment_modifiers[4]
                            + (4 if "tsuyoshi" in effects else 0))
    roll = neutral_hp - constitution_hp_bonus(con, player.level)
    defense = WarriorDefenseInputs(player.level, natural[3], shield_skill=player.shield_skill,
                                   intrinsic_dex=adjustments[3])
    try:
        armor_constant = player.ac - ac_bonus - loadout_armor_class(worn, defense)
    except ValueError as exc:
        raise CharacterSheetUnavailable("unsupported-ac-interaction") from exc
    flags = character_intrinsic_flags(character["characteristics"])
    capabilities = frozenset("immune_nether" for row in character["characteristics"]
                             if row.get("flag_id") == 60 and row.get("immunity"))
    ability_flags = {name: flag for name, flag in PLAYER_ABILITY_FLAGS.items() if name != "hold_exp"}
    ability_flags["see_invisible"] = 78
    abilities = frozenset(name for name, flag in ability_flags.items()
                          if flag in flags)
    pins = tuple(sorted((item.slot, equipment_identity(item)) for item in snapshot.equipment
                        if item.is_equipment and item.is_cursed))
    return CharacterCalibration(
        race_id=player.race_id, class_id=player.class_id, personality_id=player.personality_id,
        level=player.level, stat_cur=tuple(natural), base_stats=intrinsic,
        base_hp=roll, base_ac_bonus=armor_constant, intrinsic_abilities=abilities,
        pinned_identities=pins, observed_turn=snapshot.turn, mutation_signature=mutations,
        intrinsic_tr_flags=flags, schema_version=2, source="equipped-c-screen",
        natural_stats=tuple(natural), intrinsic_adjustments=adjustments, hp_floor=player.level + 1,
        evidence_hash=sheet.content_hash, response_sequence=sequence,
        protocol_version=protocol_version, stat_key_kind="visible-base-current-v2",
        visible_stat_key=player.printed_stat_cur_key, session_id=session_id,
        intrinsic_capabilities=capabilities,
    )
