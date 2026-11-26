"""The Rogue's Sorcery spells as one more means of what the bot already decides (owner 2026-11-26).

Owner 2026-11-26 (verbatim): 「盗賊は魔法を使える。無視する戦略ならばそれも良いが、多少なり使うと
大きく助けになる。」  The spells are not new tactics: each supported spell stands in for a means a rule
already chooses, under that rule's own conditions.

* Short Teleport (ショート・テレポート) and Teleport (テレポート): the escape read of a Phase Door or a
  Teleportation scroll, when no such scroll is carried (``escape_means``, read by
  policy._escape_scroll; a scroll never fails, so a carried one is read first).
* Detect Monsters, Detect Doors and Traps, Magic Mapping, Detection True, Light Area, Teleport Away
  and Haste Self: rows of the occasion table the Magic-Eater's absorbed powers use (me_powers: the
  floor, rest, fight, threat, sealed and trap occasions and their named triggers), asked through
  me_powers.power_key for this class (``spell_key``).
* The third and fourth books (the supervisor 2026-11-27): Teleport Level for a Teleport Level
  scroll (``teleport_level_means``, policy_combat ``_teleport_level_item``), Word of Recall for a
  Word of Recall scroll (``recall_means``, policy ``_find_recall_scroll``; ``recall_held`` counts
  it as one recall unit, as a Rod of Recall), Clairvoyance for the whole-floor maps
  (``map_spell``, the Magic Mapping row's preferred row), Detect items and Treasure for a mining
  floor's first detection (``detect_objects_key``).  Sense Minds and Banishment stand in for no
  means the bot has (no temporary telepathy, no mass banish), so they are not cast.

Game facts (C:/hengband):
* The Rogue (class 3) reads Sorcery (仙術, realm 2) by INT (lib/edit/ClassMagicDefinitions.jsonc
  ROGUE: spell_type SORCERY, magic_status INT, first_spell_level 5, armour_weight_limit 400,
  has_glove_mp_penalty, has_magic_fail_rate_cap; realm SORCERY aptitude -2, Globe of
  Invulnerability unlearnable).  Each spell's level, mana and difficulty derive from its base
  (lib/edit/SpellDefinitions.jsonc) by spell/magic-aptitude.cpp:40-60 with aptitude_steps
  L 30 / M 15 / D 3 (``derived``).
* The cost shown and paid is mod_need_mana (spell/spell-info.cpp:41-60): the derived mana times
  (2400 + 1400 - exp) / 2400 rounded up, so 19/12 of it while the spell has no proficiency and
  the derived mana from EXPERT (1400, player/player-skill.cpp:34) on (``need_mana``).
* spell_chance (spell/spell-info.cpp:135-230): difficulty - 3 * (level - spell level) - 3 *
  (adj_mag_stat[INT] - 1), + 5 per missing mana point, at least adj_mag_fail[INT] and at least 5
  for this class (has_magic_fail_rate_cap), + the stun's magic penalty (timed-effect/
  player-stun.cpp:135-153), at most 95 (``formula_fail``).
* do_cmd_cast (cmd-action/cmd-spell.cpp:907-1060): blind or with no light on the own grid
  「目が見えない！」, confused refused (as a scroll's read, policy._can_read_scrolls); the book
  question 「どの呪文書を使いますか?」, the spell question 「(呪文:a-h, '*'で一覧, ESCで中断)
  どの呪文を唱えますか?」 (the spell's letter is its place in the book: spell_id % 8); with too
  little mana 「その呪文を唱えるのに十分なマジックポイントがない。」 ends the command when over_exert is
  off (the bot's option set: no 「それでも挑戦しますか?」 is asked); a failure 「呪文をうまく唱えられ
  なかった！」 takes the turn and the mana.
* print_spells (spell/spell-info.cpp:244-380) draws the list under the spell question of the cast,
  the study and the browse (always_show_list), and the emitter writes the same rows as a
  ``spell_list`` record (bot/bot-json-output.cpp output_bot_json_spell_list_snapshot): status
  (unknown = not learned, untried, available, forgotten, illegible), level, mana, fail.  The fail
  shown includes the missing mana of the moment (+5 a point) and the stun (``observe_list`` keeps
  the record with the mana and stun it was shown under; ``success`` takes them back out).

Live capture (2026-11-26, the Golem Rogue template on a private game, INT 15, level 10): the
study and cast questions above, the list rows 「a) モンスター感知 [初] 2 2 9% 未経験」, the
cost 2/5/7/7/8/12/12/15 of the first book at no proficiency, the fail 13% shown at 0 mana for a
9% spell.
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot.class_roles import casts_realm_spells
from hengbot.policy_constants import IDENTIFY_FAIL_LIMIT
from hengbot.model import (
    SV_SCROLL_IDENTIFY, SV_SCROLL_PHASE_DOOR, SV_SCROLL_STAR_IDENTIFY, SV_SCROLL_TELEPORT,
    SV_SCROLL_TELEPORT_LEVEL, SV_SCROLL_WORD_OF_RECALL, TVAL_SCROLL, TVAL_SORCERY_BOOK,
    InventoryItem,
)

REALM_SORCERY = 2           # RealmType::SORCERY (realm/realm-types.h)
BOOK_TVAL = TVAL_SORCERY_BOOK
SPELLS_PER_BOOK = 8         # fake_spell_flags: each Sorcery book holds 8 spells
# The books whose spells this module casts (sval 0: [入門書], 1: [仙人の書], 2: [紋様仙術],
# 3: [力の魔道書]; the supervisor 2026-11-27 added the third and fourth books' high-value spells).
CAST_BOOKS = (0, 1, 2, 3)

# lib/edit/ClassMagicDefinitions.jsonc: aptitude_steps and the Rogue's Sorcery aptitude.
LEARN_LEVEL_PERCENT, MANA_COST_PERCENT, DIFFICULTY_STEP = 30, 15, 3
ROGUE_SORCERY_APTITUDE = -2
PY_MAX_LEVEL = 50
# mod_need_mana (spell/spell-info.cpp:41-60) and SPELL_EXP_EXPERT (player/player-skill.cpp:34).
MANA_CONST, MANA_DIV, SPELL_EXP_EXPERT = 2400, 4, 1400
MAX_FAILURE = 95
CLASS_MIN_FAILURE = 5       # has_magic_fail_rate_cap (spell-info.cpp:168-173)
# player/player-status-table.cpp adj_mag_fail / adj_mag_stat, by stat index (3 .. 18/220+).
ADJ_MAG_FAIL = (99, 99, 99, 99, 99, 50, 30, 20, 15, 12, 11, 10, 9, 8, 7, 6, 6, 5, 5, 5, 4, 4,
                4, 4, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1, 1, 0, 0, 0)
ADJ_MAG_STAT = (0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 5, 6, 7, 8, 9,
                10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20)
STAT_INT = 1                # PlayerState.stat_index order (STR, INT, WIS, DEX, CON, CHR)
# PlayerStun::get_magic_chance_penalty by PlayerStunRank (me_power_success's table).
STUN_MAGIC_PENALTY = (0, 10, 20, 30, 50, 100)


@dataclass(frozen=True)
class Spell:
    """A Sorcery spell's base row (lib/edit/SpellDefinitions.jsonc realm SORCERY)."""
    spell_id: int
    tag: str
    names: tuple[str, str]
    base_level: int
    base_mana: int
    base_difficulty: int

    @property
    def book(self) -> int:
        return self.spell_id // SPELLS_PER_BOOK

    @property
    def letter(self) -> str:
        return chr(ord("a") + self.spell_id % SPELLS_PER_BOOK)


SPELLS = (
    Spell(0, "Detect_Monsters", ("モンスター感知", "Detect Monsters"), 1, 1, 23),
    Spell(1, "Phase_Door", ("ショート・テレポート", "Phase Door"), 1, 2, 24),
    Spell(2, "Detect_Doors_and_Traps", ("罠と扉感知", "Detect Doors and Traps"), 3, 3, 25),
    Spell(3, "Light_Area", ("ライト・エリア", "Light Area"), 3, 3, 30),
    Spell(4, "Confuse_Monster", ("パニック・モンスター", "Confuse Monster"), 4, 4, 30),
    Spell(5, "Teleport", ("テレポート", "Teleport"), 5, 5, 35),
    Spell(6, "Sleep_Monster", ("スリープ・モンスター", "Sleep Monster"), 6, 5, 30),
    Spell(7, "Recharging", ("魔力充填", "Recharging"), 7, 7, 75),
    Spell(8, "Magic_Mapping", ("魔法の地図", "Magic Mapping"), 9, 7, 75),
    Spell(9, "Identify", ("鑑定", "Identify"), 10, 7, 75),
    Spell(10, "Slow_Monster", ("スロウ・モンスター", "Slow Monster"), 11, 7, 75),
    Spell(11, "Mass_Sleep", ("周辺スリープ", "Mass Sleep"), 13, 7, 50),
    Spell(12, "Teleport_Away", ("テレポート・モンスター", "Teleport Away"), 18, 12, 60),
    Spell(13, "Haste_Self", ("スピード", "Haste Self"), 22, 12, 60),
    Spell(14, "Detection_True", ("真・感知", "Detection True"), 28, 20, 70),
    Spell(15, "Identify_True", ("真・鑑定", "Identify True"), 33, 30, 75),
    # [紋様仙術] (BaseitemDefinitions id 336: level 50, cost 25000; SpellDefinitions.jsonc
    # SORCERY book 3).
    Spell(16, "Detect_items_and_Treasure", ("物体と財宝感知", "Detect items and Treasure"), 3, 3, 25),
    Spell(17, "Charm_Monster", ("チャーム・モンスター", "Charm Monster"), 10, 10, 80),
    Spell(18, "Sense_Minds", ("精神感知", "Sense Minds"), 14, 10, 60),
    Spell(19, "Teleport_to_town", ("街移動", "Teleport to town"), 18, 30, 70),
    Spell(20, "Self_Knowledge", ("自己分析", "Self Knowledge"), 20, 18, 85),
    Spell(21, "Teleport_Level", ("テレポート・レベル", "Teleport Level"), 20, 18, 60),
    Spell(22, "Word_of_Recall", ("帰還の呪文", "Word of Recall"), 25, 25, 75),
    Spell(23, "Dimension_Door", ("次元の扉", "Dimension Door"), 40, 40, 80),
    # [力の魔道書] (id 337: level 90, cost 100000; SORCERY book 4).
    Spell(24, "Probing", ("調査", "Probing"), 10, 10, 40),
    Spell(25, "Explosive_Rune", ("爆発のルーン", "Explosive Rune"), 20, 20, 80),
    Spell(26, "Telekinesis", ("念動力", "Telekinesis"), 25, 25, 75),
    Spell(27, "Clairvoyance", ("千里眼", "Clairvoyance"), 30, 40, 80),
    Spell(28, "Charm_Monsters", ("魅了の視線", "Charm Monsters"), 33, 35, 60),
    Spell(29, "Alchemy", ("錬金術", "Alchemy"), 42, 50, 90),
    Spell(30, "Banishment", ("怪物追放", "Banishment"), 43, 40, 55),
    Spell(31, "Globe_of_Invulnerability", ("無傷の球", "Globe of Invulnerability"), 45, 70, 85),
)
BY_ID = {spell.spell_id: spell for spell in SPELLS}

DETECT_MONSTERS, PHASE_DOOR, DETECT_DOORS_TRAPS, LIGHT_AREA = 0, 1, 2, 3
TELEPORT, MAGIC_MAPPING, IDENTIFY = 5, 8, 9
TELEPORT_AWAY, HASTE_SELF, DETECTION_TRUE, IDENTIFY_TRUE = 12, 13, 14, 15
DETECT_OBJECTS, TELEPORT_LEVEL, WORD_OF_RECALL, CLAIRVOYANCE = 16, 21, 22, 27

# The study order: the spells the rules use first (escape, detection, mapping, identification,
# haste, Teleport Away, then the third and fourth books' recall, level escape, whole-floor map and
# treasure detection), then the rest of the four books in book order.
LEARN_PRIORITY = (PHASE_DOOR, DETECT_MONSTERS, TELEPORT, DETECT_DOORS_TRAPS, MAGIC_MAPPING,
                  IDENTIFY, HASTE_SELF, TELEPORT_AWAY, WORD_OF_RECALL, TELEPORT_LEVEL,
                  CLAIRVOYANCE, DETECTION_TRUE, LIGHT_AREA, IDENTIFY_TRUE, DETECT_OBJECTS)
LEARN_ORDER = LEARN_PRIORITY + tuple(spell.spell_id for spell in SPELLS
                                     if spell.spell_id not in LEARN_PRIORITY)

# The spells a escape read stands in for: the scroll's sval -> the spell.
ESCAPE_SPELLS = {SV_SCROLL_TELEPORT: TELEPORT, SV_SCROLL_PHASE_DOOR: PHASE_DOOR}
# Owner 2026-11-16 (Q25, 「TA は実際の成功率が高い方（50%未満は数えない）」): an escape or a
# Teleport Away below this success is not a means.
ESCAPE_MIN_SUCCESS = 50
# me_capability's RELIABLE_MIN_SUCCESS (policy_constants 80): a utility cast (detection, mapping,
# light) and the haste (owner 2026-11-04 「成功率8割以上のときに限定して」 for the absorbed Speed).
RELIABLE_MIN_SUCCESS = 80

POLICY_LISTS = "_realm_spell_lists"
STATUS_LEARNED = frozenset({"available", "untried"})


# -- the game's numbers -----------------------------------------------------------------------

def _round_half_away_from_zero(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(abs(numerator), denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    return quotient if numerator >= 0 else -quotient


def derived(spell: Spell, aptitude: int = ROGUE_SORCERY_APTITUDE) -> tuple[int, int, int]:
    """(level, mana, difficulty) of ``spell`` for a class with ``aptitude`` (magic-aptitude.cpp)."""
    mana = max(1, (spell.base_mana * (100 - MANA_COST_PERCENT * aptitude) + 50) // 100)
    move = _round_half_away_from_zero(
        spell.base_level * (PY_MAX_LEVEL - spell.base_level) * LEARN_LEVEL_PERCENT * aptitude,
        PY_MAX_LEVEL * 100)
    level = min(PY_MAX_LEVEL, max(1, spell.base_level - move))
    difficulty = min(100, max(0, spell.base_difficulty - DIFFICULTY_STEP * aptitude))
    return level, mana, difficulty


def need_mana(mana: int, exp: int = 0) -> int:
    """mod_need_mana for a magic realm without dec_mana: the cost at proficiency ``exp``."""
    need = mana * (MANA_CONST + SPELL_EXP_EXPERT - exp) + (MANA_CONST - 1)
    return max(1, need * MANA_DIV // (MANA_CONST * MANA_DIV))


def _int_index(player) -> int | None:
    index = getattr(player, "stat_index", ()) or ()
    return int(index[STAT_INT]) if len(index) > STAT_INT else None


def min_failure(player) -> int:
    """adj_mag_fail[INT], at least the class cap's 5."""
    index = _int_index(player)
    table = ADJ_MAG_FAIL[max(0, min(index, len(ADJ_MAG_FAIL) - 1))] if index is not None else 0
    return max(CLASS_MIN_FAILURE, table)


def stun_penalty(player) -> int:
    rank = getattr(player, "stun_rank", None)
    if rank is None:
        rank = int(bool(getattr(player, "stunned", False)))
    return STUN_MAGIC_PENALTY[max(0, min(int(rank), len(STUN_MAGIC_PENALTY) - 1))]


def formula_fail(spell: Spell, player, *, mana_short: int = 0) -> int:
    """spell_chance with no proficiency, equipment or alignment term (the list's number is the
    game's own; this is only the reading before a list was shown)."""
    level, _mana, difficulty = derived(spell)
    index = _int_index(player)
    stat = ADJ_MAG_STAT[max(0, min(index, len(ADJ_MAG_STAT) - 1))] if index is not None else 0
    chance = difficulty - 3 * (player.level - level) - 3 * (stat - 1) + 5 * max(0, mana_short)
    chance = max(chance, min_failure(player)) + stun_penalty(player)
    return min(chance, MAX_FAILURE)


# -- what the game showed ---------------------------------------------------------------------

def observe_list(policy, record) -> None:
    """Keep a ``spell_list`` record of the character's Sorcery books (cli ``_dispatch_response_lines``).

    The list shows one book (its spells' ids); the record's ``player`` is the board it was drawn
    under (its mana and stun are in the fails shown)."""
    data = record.get("spell_list") if isinstance(record, dict) else None
    if not isinstance(data, dict) or data.get("realm_id") != REALM_SORCERY:
        return
    rows = {}
    for row in data.get("spells") or ():
        if not isinstance(row, dict) or not isinstance(row.get("spell_id"), int):
            continue
        rows[row["spell_id"]] = {
            "status": str(row.get("status", "")),
            "level": row.get("level"), "mana": row.get("mana"), "fail": row.get("fail"),
        }
    books = {spell_id // SPELLS_PER_BOOK for spell_id in rows}
    if len(books) != 1:
        return
    player = record.get("player") if isinstance(record.get("player"), dict) else {}
    status = player.get("status") if isinstance(player.get("status"), dict) else {}
    lists = dict(getattr(policy, POLICY_LISTS, None) or {})
    lists[books.pop()] = {
        "turn": record.get("turn"),
        "mp": player.get("mp"),
        "level": player.get("level"),
        "stun_rank": status.get("stun_rank"),
        "rows": rows,
    }
    setattr(policy, POLICY_LISTS, lists)


def _row(policy, spell_id: int) -> dict | None:
    listing = (getattr(policy, POLICY_LISTS, None) or {}).get(spell_id // SPELLS_PER_BOOK)
    return None if listing is None else listing["rows"].get(spell_id)


def listing(policy, book: int) -> dict | None:
    return (getattr(policy, POLICY_LISTS, None) or {}).get(book)


def learned(policy, spell_id: int) -> bool:
    row = _row(policy, spell_id)
    return row is not None and row["status"] in STATUS_LEARNED


def cost(policy, spell_id: int) -> int | None:
    """The mana the last list showed (it only falls as the proficiency rises)."""
    row = _row(policy, spell_id)
    mana = None if row is None else row.get("mana")
    return mana if isinstance(mana, int) and mana > 0 else None


def unstunned_failure(policy, player, spell_id: int) -> int | None:
    """The shown fail less the missing mana and the stun it was shown under, else None."""
    row = _row(policy, spell_id)
    if row is None or not isinstance(row.get("fail"), int):
        return None
    listing_ = listing(policy, spell_id // SPELLS_PER_BOOK)
    fail = int(row["fail"])
    if fail >= MAX_FAILURE:
        return MAX_FAILURE
    rank = listing_.get("stun_rank")
    if isinstance(rank, int) and rank > 0:
        fail -= STUN_MAGIC_PENALTY[min(rank, len(STUN_MAGIC_PENALTY) - 1)]
    mana, shown_mp = row.get("mana"), listing_.get("mp")
    floor = min_failure(player)
    if isinstance(mana, int) and isinstance(shown_mp, int) and shown_mp < mana and fail > floor:
        # spell_chance adds the missing mana before the minimum (spell-info.cpp:158-212).
        fail = max(floor, fail - 5 * (mana - shown_mp))
    return max(fail, 0)


def success(policy, snapshot, spell_id: int, *, stunned: bool = True) -> int | None:
    """The cast's success percent on this board (its stun counted unless ``stunned`` is False),
    else None without a shown row; 0 under a worn anti-magic (``anti_magic_worn``: the command is
    refused, as me_power_success's REFUSED_FAILURE), so every means this module answers
    (``known_reliable``, ``castable``, ``recall_held``, me_powers' rows) reads the spell as
    unavailable while it is worn."""
    if anti_magic_worn(snapshot) and _row(policy, spell_id) is not None:
        return 0
    fail = unstunned_failure(policy, snapshot.player, spell_id)
    if fail is None:
        return None
    if stunned:
        fail += stun_penalty(snapshot.player)
    return 100 - min(fail, MAX_FAILURE)


# -- can it be cast now ------------------------------------------------------------------------

def applies(policy, snapshot) -> bool:
    """A class that casts its realm's spells, of the Sorcery realm when the sheet showed one."""
    if not casts_realm_spells(snapshot.player.class_id):
        return False
    own = getattr(policy, "_own_book_tvals", None)
    return own is None or BOOK_TVAL in own


def book_item(snapshot, book: int) -> InventoryItem | None:
    """The carried Sorcery book of ``book`` (sval)."""
    return next((item for item in snapshot.inventory
                 if item.tval == BOOK_TVAL and item.sval == book and item.aware and item.count > 0),
                None)


def cast_blocked(policy, snapshot) -> bool:
    """What refuses the cast command, or a state the bot does not cast in: blindness, no light on
    the own grid and confusion (do_cmd_cast, as policy._can_read_scrolls), paralysis, a shop."""
    player = snapshot.player
    return (snapshot.store is not None or player.paralyzed
            or not policy._can_read_scrolls(snapshot))


def anti_magic_worn(snapshot) -> bool:
    """A worn item's known NO_MAGIC (反魔法): the game refuses the cast command ``m`` before the
    book question (io/input-key-processor.cpp:424-455 「反魔法バリアが魔法を邪魔した！」, no turn
    passes; player-status-flags.cpp has_anti_magic reads the worn items), so no spell is a means
    while it is worn (``success`` 0) and no mana is held for one (``escape_reserve``).  The study
    ``G`` and the browse ``b`` are not refused (the same file's ``G`` and ``b`` cases).  The supervisor 2026-11-27: n1-a
    life-545 wore ☆死天使アズリエルの革製ラージ・シールド {[魔} with its books carried; the loadout
    search leaves NO_MAGIC out for this class (equipment_rules.search_banned_flags)."""
    from hengbot.me_power_success import worn_anti_magic
    return worn_anti_magic(snapshot)


def escape_reserve(policy, snapshot) -> int:
    """The mana held back in the dungeon for an escape cast (Teleport, else Short Teleport, when
    learned with its book carried); a non-escape cast may not spend into it.  None under a worn
    anti-magic (``anti_magic_worn``)."""
    if anti_magic_worn(snapshot):
        return 0
    for spell_id in (TELEPORT, PHASE_DOOR):
        if learned(policy, spell_id) and book_item(snapshot, BY_ID[spell_id].book) is not None:
            return cost(policy, spell_id) or 0
    return 0


def mana_rest_due(policy, snapshot) -> bool:
    """A caster in the dungeon whose mana is below the escape reserve (its escape spell's cost),
    or short of the Word of Recall it goes home with (``recall_rest_due``): the rest rung rests
    (REST_MACRO ``R&``: until HP and mana are full or disturbed) as it does for HP."""
    if not applies(policy, snapshot) or snapshot.in_town:
        return False
    return (snapshot.player.mp < escape_reserve(policy, snapshot)
            or recall_rest_due(policy, snapshot))


# The mana order of the dungeon casts, in one place (owner 2026-11-27 「魔法の地図は探索効率を大幅に
# 向上させるのでうまく使うと良いだろう」, the supervisor's order): the escape reserve (Teleport, else
# Short Teleport: ``escape_reserve``) > Detect Monsters on arrival > Magic Mapping > the other
# utility casts (Detect Doors and Traps, Light Area, Detection True, Identify).  A cast lower in
# ``UTILITY_ORDER`` also keeps the mana of each one above it that has not landed on this floor
# visit (``order_reserve``); the casts at a hostile (Teleport Away, Haste Self) keep only the escape
# reserve.  The occasion rows' priorities (``_rows``) put the same order on one board.
UTILITY_ORDER = (DETECT_MONSTERS, MAGIC_MAPPING)
COMBAT_SPELLS = frozenset({TELEPORT_AWAY, HASTE_SELF})
# The supervisor 2026-11-27 (the third and fourth books): Clairvoyance takes Magic Mapping's place
# in the order (the same map, of the whole floor), so it keeps only what Magic Mapping keeps; the
# floor-leaving casts (Teleport Level, Word of Recall) are escapes: they keep no utility mana and
# may spend the escape reserve (``castable(..., escape=True)``).
ORDER_PLACE = {CLAIRVOYANCE: MAGIC_MAPPING}
LEAVING_SPELLS = frozenset({TELEPORT_LEVEL, WORD_OF_RECALL})


def landed_on_floor(policy, snapshot, spell_id: int) -> bool:
    """A cast of ``spell_id`` landed on this floor visit (me_powers' floor memory of the uses); for
    Magic Mapping also any live map of the player's place (mapped_area: a device, a scroll or an
    earlier cast)."""
    from hengbot import mapped_area, me_powers
    from hengbot.model import game_distance
    memory = getattr(policy, me_powers.MEMORY, None)
    if (memory is not None and memory.floor == snapshot.floor_key
            and any(use.used == ("spell", spell_id) for use in memory.uses)):
        return True
    if spell_id == MAGIC_MAPPING:
        here = snapshot.player.position
        return any(game_distance(here, centre) < radius
                   for centre, radius in mapped_area.floor_discs(policy, snapshot))
    return False


def order_reserve(policy, snapshot, spell_id: int) -> int:
    """The mana of the casts ahead of ``spell_id`` in ``UTILITY_ORDER`` that are learned, carried
    and not landed on this floor visit; 0 for a cast at a hostile, an escape or the first."""
    if (spell_id in COMBAT_SPELLS or spell_id in ESCAPE_SPELLS.values()
            or spell_id in LEAVING_SPELLS):
        return 0
    place = ORDER_PLACE.get(spell_id, spell_id)
    ahead = (UTILITY_ORDER[:UTILITY_ORDER.index(place)] if place in UTILITY_ORDER
             else UTILITY_ORDER)
    return sum(cost(policy, each) or 0 for each in ahead
               if learned(policy, each) and book_item(snapshot, BY_ID[each].book) is not None
               and not landed_on_floor(policy, snapshot, each))


# realm-sorcery.cpp:388-406 Clairvoyance: wiz_lite (spell-kind/spells-floor.cpp: every grid of the
# floor lit and remembered, every object detected) and, without telepathy, set_tim_esp(25 + 1d30).
# Its map is the whole floor: a disc no floor (MAX_WID 198 x MAX_HGT 66) reaches out of.
WHOLE_FLOOR_RADIUS = 255
# The map triggers where the whole floor is worth Clairvoyance's mana (a new floor, the stairs
# unknown: the floor's way on); the others (a *Destruction*'s circle, a sealed pocket, an
# enclosure, the walk out of a map) are local and keep Magic Mapping.  me_powers' trigger names
# and area_mapping's.
WHOLE_FLOOR_TRIGGERS = frozenset({"new-floor", "stairs-needed-and-unknown", "deep-climb",
                                  "finale-descent"})


def map_spell(policy, snapshot, trigger: str = "") -> int | None:
    """The map spell a 周辺感知 of area_mapping's means casts (its ``_carried_key``): Clairvoyance
    for a whole-floor ``trigger`` when it can be cast, else Magic Mapping, each at
    RELIABLE_MIN_SUCCESS under the mana order; else None."""
    if trigger in WHOLE_FLOOR_TRIGGERS and castable(policy, snapshot, CLAIRVOYANCE,
                                                     RELIABLE_MIN_SUCCESS):
        return CLAIRVOYANCE
    if castable(policy, snapshot, MAGIC_MAPPING, RELIABLE_MIN_SUCCESS):
        return MAGIC_MAPPING
    return None


def map_radius(spell_id: int) -> int | None:
    """The disc of a map spell's cast: the whole floor for Clairvoyance, else None (Magic
    Mapping's is me_powers.map_radius: a DARKNESS dungeon's third)."""
    return WHOLE_FLOOR_RADIUS if spell_id == CLAIRVOYANCE else None


def known_reliable(policy, snapshot, spell_id: int, min_success: int, *,
                   stunned: bool = True) -> bool:
    """The standing part of ``castable``: a Sorcery caster that learned the spell, carries its
    book, and casts it at ``min_success`` or better (under this board's stun unless ``stunned``
    is False; 0 under a worn anti-magic, ``success``).  Neither the mana of the moment nor the
    moment's blindness or confusion is read."""
    if not applies(policy, snapshot):
        return False
    spell = BY_ID[spell_id]
    if (not learned(policy, spell_id) or cost(policy, spell_id) is None
            or book_item(snapshot, spell.book) is None):
        return False
    rate = success(policy, snapshot, spell_id, stunned=stunned)
    return rate is not None and rate >= min_success


def castable(policy, snapshot, spell_id: int, min_success: int, *, escape: bool = False) -> bool:
    """Learned, its book carried, the mana (above the escape reserve for a non-escape cast in the
    dungeon), the success at least ``min_success`` under this board's stun, nothing refusing."""
    if cast_blocked(policy, snapshot) or not known_reliable(policy, snapshot, spell_id, min_success):
        return False
    reserve = 0 if escape or snapshot.in_town else (
        escape_reserve(policy, snapshot) + order_reserve(policy, snapshot, spell_id))
    return snapshot.player.mp >= cost(policy, spell_id) + reserve


def cast_key(snapshot, spell_id: int, direction: str = "") -> str:
    """``m`` + the book's slot + the spell's letter (+ a direction): realm_spells_input answers each
    question at its own prompt."""
    spell = BY_ID[spell_id]
    book = book_item(snapshot, spell.book)
    return "m" + book.slot + spell.letter + direction


# -- the escape read's stand-in -----------------------------------------------------------------

@dataclass(frozen=True)
class SpellMeans(InventoryItem):
    """A spell standing where an escape scroll is read (policy._escape_scroll): the scroll's
    tval/sval so the escape rules read it as that scroll, a name no carried stack has.
    policy._read_key casts it (``means_cast_key``); it is never an inventory stack."""
    spell_id: int = -1

    @property
    def is_spell_means(self) -> bool:
        return True


def is_spell_means(item) -> bool:
    return bool(getattr(item, "is_spell_means", False))


def escape_means(policy, snapshot, scroll_sval: int) -> SpellMeans | None:
    """The spell that stands in for an escape scroll of ``scroll_sval`` when none is carried:
    Teleport for Teleportation, Short Teleport for Phase Door, castable at ``ESCAPE_MIN_SUCCESS``
    or better (the mana reserve is the escape's own)."""
    spell_id = ESCAPE_SPELLS.get(scroll_sval)
    if spell_id is None or not castable(policy, snapshot, spell_id, ESCAPE_MIN_SUCCESS, escape=True):
        return None
    return _means(spell_id, scroll_sval)


# realm-sorcery.cpp:313-320 Teleport Level asks input_check 「本当に他の階にテレポートしますか？」
# before teleport_level: the cast key carries its ``y`` (realm_spells_input's confirm stage).
CONFIRM_SUFFIX = "y"


def means_cast_key(snapshot, item: SpellMeans, target: str = "") -> str:
    """The cast of a stand-in spell; ``target`` answers an identification's item question (a pack
    letter, ``-`` for the floor, ``/`` + an equipment letter) or a surface recall's dungeon
    question (its letter), realm_spells_input; Teleport Level's confirmation is its ``y``."""
    if item.spell_id == TELEPORT_LEVEL:
        target = CONFIRM_SUFFIX
    return cast_key(snapshot, item.spell_id) + target


def _means(spell_id: int, scroll_sval: int) -> SpellMeans:
    spell = BY_ID[spell_id]
    return SpellMeans(slot=f"spell:{spell_id}", name=spell.names[0] + "（呪文）", count=1,
                      tval=TVAL_SCROLL, sval=scroll_sval, aware=True, known=True,
                      spell_id=spell_id)


# -- the floor-leaving casts (the third book; the supervisor 2026-11-27) -------------------------
#
# realm-sorcery.cpp:313-335: Teleport Level is teleport_level(player, 0) as the scroll's
# (object-use/read/scroll-read-executor.cpp:149) after its confirmation; Word of Recall is
# recall_player(15 + 1d20) as the scroll's (randint0(21) + 15, :154), so the same questions follow
# (the surface's choose_dungeon, a shallower floor's 「ここは最深到達階より浅い階です。…」).  A scroll
# never fails and a blind or confused character casts nothing: the scrolls stay carried as backup.


def teleport_level_means(policy, snapshot) -> SpellMeans | None:
    """Teleport Level in a Teleport Level scroll's place (policy_combat ``_teleport_level_item``):
    castable at ESCAPE_MIN_SUCCESS with an escape's mana (it may spend the escape reserve)."""
    if not castable(policy, snapshot, TELEPORT_LEVEL, ESCAPE_MIN_SUCCESS, escape=True):
        return None
    return _means(TELEPORT_LEVEL, SV_SCROLL_TELEPORT_LEVEL)


def recall_means(policy, snapshot) -> SpellMeans | None:
    """Word of Recall in a Word of Recall scroll's place (policy ``_find_recall_scroll``):
    castable at RELIABLE_MIN_SUCCESS with an escape's mana (an emergency recall may spend the
    escape reserve; in town any mana)."""
    if not castable(policy, snapshot, WORD_OF_RECALL, RELIABLE_MIN_SUCCESS, escape=True):
        return None
    return _means(WORD_OF_RECALL, SV_SCROLL_WORD_OF_RECALL)


def recall_held(policy, snapshot) -> bool:
    """Word of Recall is a recall means the character holds whatever its mana now (resting gives
    it back): learned, its book carried, at RELIABLE_MIN_SUCCESS by the shown list without this
    board's stun, its cost within the maximum mana.  The departure ledger and the dungeon's
    recall count read it as one unit, as a Rod of Recall (policy ``_recall_spell_unit``).  Not
    under a worn anti-magic (``success`` 0): the scrolls are bought instead."""
    if not applies(policy, snapshot):
        return False
    mana = cost(policy, WORD_OF_RECALL)
    rate = success(policy, snapshot, WORD_OF_RECALL, stunned=False)
    return (learned(policy, WORD_OF_RECALL) and mana is not None
            and book_item(snapshot, BY_ID[WORD_OF_RECALL].book) is not None
            and rate is not None and rate >= RELIABLE_MIN_SUCCESS
            and snapshot.player.max_mp >= mana)


def recall_rest_due(policy, snapshot) -> bool:
    """On the way back to town (policy ``_returning_to_town``) with no recall scroll, Word of
    Recall held but its mana short now: the rest rung rests for it (``mana_rest_due``)."""
    if not getattr(policy, "_returning_to_town", False) or snapshot.player.recalling:
        return False
    if any(item.is_recall_scroll for item in snapshot.inventory):
        return False
    mana = cost(policy, WORD_OF_RECALL)
    return (recall_held(policy, snapshot) and mana is not None
            and snapshot.player.mp < mana)


def detect_objects_key(policy, snapshot) -> str | None:
    """Detect items and Treasure (realm-sorcery.cpp:255-266: detect_objects_normal,
    detect_treasure, detect_objects_gold in DETECT_RAD_DEFAULT 30) where a mining floor's first
    detection reads a Treasure Detection scroll (policy_fundraising): castable at
    RELIABLE_MIN_SUCCESS under the mana order, else None."""
    if not castable(policy, snapshot, DETECT_OBJECTS, RELIABLE_MIN_SUCCESS):
        return None
    return cast_key(snapshot, DETECT_OBJECTS)


# The identification sources a spell stands in for (cmd-spell.cpp sorcery Identify: ident_spell;
# Identify True: identify_fully): its scroll's sval -> the spell.
IDENTIFY_SPELLS = {SV_SCROLL_IDENTIFY: IDENTIFY, SV_SCROLL_STAR_IDENTIFY: IDENTIFY_TRUE}


# Supervisor 2026-11-27 (the owner's 「仙術を選んだのに鑑定の杖をまだ持ってる理由は？」): a failed 鑑定
# costs only its mana and a turn (do_cmd_cast: 「呪文をうまく唱えられなかった！」, the item question is
# never asked), so a safe cast is retried down to IDENTIFY_SPELL_MIN_SUCCESS instead of the staff's
# RELIABLE_MIN_SUCCESS.  IDENTIFY_SPELL_RETRY_LIMIT consecutive failures on one item retire the
# spell for the floor or the town visit (policy_identification), and a carried staff or scroll
# answers instead.  The limit is the town arbiter's identification budget (town_arbiter:
# IDENTIFY_FAIL_LIMIT decisions without a known-item delta): a fourth miss retired the owner
# itself and detoured to the Magic shop before the staff (n1-a life-545 replay, 2026-11-27).
# Three tries land with 1 - 0.58^3 = 80% at the Rogue's 42%, 1 - 0.7^3 = 66% at 30%.
IDENTIFY_SPELL_MIN_SUCCESS = 30
IDENTIFY_SPELL_RETRY_LIMIT = IDENTIFY_FAIL_LIMIT
# Where the retired 鑑定 is kept: the scope (floor key, town visit epoch) it was retired in.
IDENTIFY_SPELL_RETIRED = "_identify_spell_retired"


def identify_reliable(policy, snapshot, *, full: bool = False) -> bool:
    """A standing 鑑定 (真・鑑定 when ``full``) at RELIABLE_MIN_SUCCESS without a stun: learned, its
    book carried, a full mana bar that pays one cast.  At this rate no backup Identify staff is
    carried (policy_supply ``_identify_staff_carry_cap``)."""
    return _identify_standing(policy, snapshot, full, RELIABLE_MIN_SUCCESS)


def identify_usable(policy, snapshot) -> bool:
    """A standing 鑑定 at IDENTIFY_SPELL_MIN_SUCCESS without a stun: the carried Identify staff's
    departure requirement and its purchases read it as they read an absorbed staff (policy_supply
    ``_identify_staff_replaced``; n1-a life-545 2026-11-27, the CL23 Rogue's 鑑定 at 42%)."""
    return _identify_standing(policy, snapshot, False, IDENTIFY_SPELL_MIN_SUCCESS)


def _identify_standing(policy, snapshot, full: bool, min_success: int) -> bool:
    spell_id = IDENTIFY_SPELLS[SV_SCROLL_STAR_IDENTIFY if full else SV_SCROLL_IDENTIFY]
    mana = cost(policy, spell_id)
    return (mana is not None and snapshot.player.max_mp >= mana
            and known_reliable(policy, snapshot, spell_id, min_success, stunned=False))


def _scope(snapshot) -> tuple:
    return (snapshot.floor_key, snapshot.in_town)


def identify_spell_retired(policy, snapshot) -> bool:
    """The safe retried 鑑定 gave up on this floor (or this town visit) after
    IDENTIFY_SPELL_RETRY_LIMIT consecutive failures on one item."""
    retired = getattr(policy, IDENTIFY_SPELL_RETIRED, None)
    return retired is not None and retired == (_scope(snapshot),
                                               getattr(policy, "_town_visit_epoch", None))


def retire_identify_spell(policy, snapshot) -> None:
    setattr(policy, IDENTIFY_SPELL_RETIRED,
            (_scope(snapshot), getattr(policy, "_town_visit_epoch", None)))


def identify_cast_safe(snapshot) -> bool:
    """A board on which a failed 鑑定 only costs its mana and a turn: the town, or a floor with no
    hostile in view and none sensed (the mana above the escape reserve is ``castable``'s)."""
    if snapshot.in_town:
        return True
    return not any(not getattr(monster, "pet", False)
                   for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters))


def identify_retry_means(policy, snapshot) -> SpellMeans | None:
    """鑑定 as the first identification source where its failure is safe: castable at
    IDENTIFY_SPELL_MIN_SUCCESS on a safe board, not retired on this floor or town visit."""
    if not identify_cast_safe(snapshot) or identify_spell_retired(policy, snapshot):
        return None
    if not castable(policy, snapshot, IDENTIFY, IDENTIFY_SPELL_MIN_SUCCESS):
        return None
    return _means(IDENTIFY, SV_SCROLL_IDENTIFY)


def _means(spell_id: int, scroll_sval: int) -> SpellMeans:
    spell = BY_ID[spell_id]
    return SpellMeans(slot=f"spell:{spell_id}", name=spell.names[0] + "（呪文）", count=1,
                      tval=TVAL_SCROLL, sval=scroll_sval, aware=True, known=True,
                      spell_id=spell_id)


def identify_means(policy, snapshot, *, full: bool) -> SpellMeans | None:
    """鑑定 (or 真・鑑定 when ``full``) as an identification source (policy_identification
    ``_find_identification_source``): castable at RELIABLE_MIN_SUCCESS (as the Identify staff's
    STAFF_IDENTIFY_MIN_SUCCESS), in the dungeon above the escape reserve, in town on any mana
    (resting or the inn refills it).  It reads as the scroll it stands in for."""
    scroll_sval = SV_SCROLL_STAR_IDENTIFY if full else SV_SCROLL_IDENTIFY
    spell_id = IDENTIFY_SPELLS[scroll_sval]
    if not castable(policy, snapshot, spell_id, RELIABLE_MIN_SUCCESS):
        return None
    return _means(spell_id, scroll_sval)


# -- the occasion table's rows (me_powers) -------------------------------------------------------

REASON = "realm-spell"
DETECT_RAD = 30                  # DETECT_RAD_DEFAULT / DETECT_RAD_MAP (spell/spells-util.h)
# Each row's least success (the rows of an escape or Teleport Away: ESCAPE_MIN_SUCCESS).
ROW_MIN_SUCCESS = {"teleport-away": ESCAPE_MIN_SUCCESS}


def _rows():
    """The spells as me_powers rows (kind "spell", sval = spell_id), built on first use: me_powers
    imports this module lazily and this module reads me_powers' Power and constants."""
    rows = globals().get("_ROWS")
    if rows is not None:
        return rows
    from hengbot import me_powers
    Power = me_powers.Power

    def names(spell_id):
        return BY_ID[spell_id].names

    rows = (
        # The Magic-Eater's Detect Evil row's triggers, the all-detection preferred (as the rod).
        # Not "quest-remaining-unseen": its trigger serves the Magic-Eater's own rows.
        Power("spell", DETECT_MONSTERS, names(DETECT_MONSTERS), "detect-monsters", DETECT_RAD, 10,
              ("new-floor", "before-rest", "hunt-target-unseen", "deep-explore-redetect"),
              preferred=(("spell", DETECTION_TRUE),)),
        Power("spell", DETECTION_TRUE, names(DETECTION_TRUE), "detect-all", DETECT_RAD, 10,
              ("hunt-target-unseen", "deep-undetected-step")),
        # cmd-spell sorcery Detect Doors and Traps: detect_traps, detect_doors, detect_stairs.
        Power("spell", DETECT_DOORS_TRAPS, names(DETECT_DOORS_TRAPS), "detect-doors-traps",
              DETECT_RAD, 20,
              ("new-floor", "left-detected-trap-area", "trap-cell-unsettled",
               "before-secret-search", "deep-undetected-step"),
              beside_harmless=True),
        # realm-sorcery.cpp:156-165 map_area(DETECT_RAD_MAP 30), the 周辺感知's own effect.  Before
        # the other utility rows (UTILITY_ORDER); "outside-mapped-area" maps again once the player
        # stands outside every live map (owner 2026-11-27 「探索効率を大幅に向上させる」).
        Power("spell", MAGIC_MAPPING, names(MAGIC_MAPPING), me_powers.MAP_AREA, DETECT_RAD, 15,
              ("after-destruction", "new-floor", "stairs-needed-and-unknown", "sealed-pocket",
               "loot-unreachable", "loot-enclosure", "outside-mapped-area"),
              beside_harmless=True, preferred=(("spell", CLAIRVOYANCE),)),
        # Clairvoyance serves the Magic Mapping row's whole-floor triggers (``_serving``,
        # WHOLE_FLOOR_TRIGGERS): it has no trigger of its own.
        Power("spell", CLAIRVOYANCE, names(CLAIRVOYANCE), me_powers.MAP_AREA, WHOLE_FLOOR_RADIUS,
              15, (), beside_harmless=True, darkness_scaled=False),
        Power("spell", LIGHT_AREA, names(LIGHT_AREA), "lite-area", me_powers.LITE_RADIUS, 50,
              ("light-radius-zero", "dark-room", "light-sensitive-adjacent"),
              requires=("not-darkness-dungeon",), darkness_scaled=False),
        Power("spell", TELEPORT_AWAY, names(TELEPORT_AWAY), "teleport-away", 0, 70,
              ("unbeatable-in-range", "sensed-t1-in-line", "quest-opening-target"),
              darkness_scaled=False, aimed=True, against_hostile=True),
        Power("spell", HASTE_SELF, names(HASTE_SELF), "speed", 0, 80,
              ("fight-unhasted", "deep-arrival-unhasted"),
              darkness_scaled=False, against_hostile=True),
    )
    globals()["_ROWS"] = rows
    globals()["BY_KEY"] = {row.ident: row for row in rows}
    return rows


def row_of(ident):
    """The occasion row of a ("spell", spell_id) ident, else None."""
    _rows()
    return globals()["BY_KEY"].get(tuple(ident))


def _row_usable(ctx, row, trigger) -> bool:
    from hengbot import me_powers
    if not all(me_powers.REQUIREMENTS[name](ctx) for name in row.requires):
        return False
    if ctx.memory.failed[(row.ident, trigger, ctx.position)] >= me_powers.FAILURES_PER_PLACE:
        return False
    return castable(ctx.policy, ctx.snapshot, row.sval,
                    ROW_MIN_SUCCESS.get(row.effect, RELIABLE_MIN_SUCCESS))


# The preferred rows that serve only some of a row's triggers (Clairvoyance: the whole floor's).
PREFERRED_TRIGGERS = {("spell", CLAIRVOYANCE): WHOLE_FLOOR_TRIGGERS}


def _serving(ctx, row, trigger):
    preferred = next((row_of(ident) for ident in row.preferred
                      if trigger in PREFERRED_TRIGGERS.get(tuple(ident), (trigger,))
                      and _row_usable(ctx, row_of(ident), trigger)), None)
    if preferred is not None:
        return preferred
    return row if _row_usable(ctx, row, trigger) else None


def spell_key(ctx, *, only: str | None = None) -> str | None:
    """me_powers.power_key for a caster: ``m`` + book + letter (+ direction) of the first due row
    for ``ctx.occasion``, its use remembered in me_powers' floor memory, else None."""
    from hengbot import me_powers
    policy, snapshot = ctx.policy, ctx.snapshot
    if not applies(policy, snapshot):
        return None
    for row in sorted(_rows(), key=lambda each: each.priority):
        if not me_powers._hostiles_allow(ctx, row):
            continue
        for name in row.triggers:
            trigger = me_powers.TRIGGERS[name]
            if ctx.occasion not in trigger.occasions or (only is not None and name != only):
                continue
            used = _serving(ctx, row, name)
            if used is None or not trigger.due(ctx, row):
                continue
            if used.aimed and ctx.aim is None:
                continue
            if name in me_powers.DESTRUCTION_FIRST_TRIGGERS and (
                    destroyed := me_powers._destruction_first(ctx)) is not None:
                return destroyed
            reason = f"{REASON}:{name}:{used.effect}"
            key = cast_key(snapshot, used.sval, ctx.aim if used.aimed else "")
            policy.last_reason = reason
            policy._offer_execution(
                key, producer="detectors", work_id=f"{REASON}:{used.effect}",
                next_step="realm-spell.cast.send", arguments=(used.sval, name),
                expected_effect=used.effect,
            )
            ctx.memory.pending = me_powers.Use(row.ident, used.ident, name, ctx.position,
                                               snapshot.turn, reason, key, ctx.target)
            return key
    return None
